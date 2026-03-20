"""日志分析模块：Session 管理 + git worktree 管理 + 日志预处理"""
import json
import logging
import os
import re
import shutil
import subprocess
import time
import uuid
import zipfile
import tarfile
from datetime import datetime

import yaml

logger = logging.getLogger(__name__)


# ── 服务注册表 ────────────────────────────────────────────

def load_services_config(config_path: str) -> dict:
    """加载 services.yaml，返回 services 字典"""
    if not os.path.isfile(config_path):
        return {}
    with open(config_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return data.get("services") or {}


def get_dependency_tree(services: dict, service_id: str, depth: int = 2) -> list[dict]:
    """获取服务依赖树，返回 [{id, name, description, depth, depends_on}]"""
    result = []
    visited = set()

    def _walk(sid: str, current_depth: int):
        if sid in visited or current_depth > depth:
            return
        visited.add(sid)
        svc = services.get(sid)
        if not svc:
            result.append({"id": sid, "name": sid, "description": "(未注册)", "depth": current_depth, "depends_on": []})
            return
        deps = svc.get("depends_on") or []
        result.append({
            "id": sid,
            "name": svc.get("name", sid),
            "description": svc.get("description", ""),
            "depth": current_depth,
            "depends_on": deps,
        })
        for dep_id in deps:
            _walk(dep_id, current_depth + 1)

    _walk(service_id, 0)
    return result


# ── Session 管理 ──────────────────────────────────────────

class SessionManager:
    """管理分析会话：上传文件、git worktree、生命周期"""

    def __init__(self, session_dir: str, worktree_base: str, session_ttl: int = 86400):
        self.session_dir = session_dir
        self.worktree_base = worktree_base
        self.session_ttl = session_ttl
        os.makedirs(session_dir, exist_ok=True)
        os.makedirs(worktree_base, exist_ok=True)

    def create_session(self, session_id: str = None) -> str:
        """创建 session 目录，返回 session_id"""
        if not session_id:
            session_id = uuid.uuid4().hex[:12]
        session_path = os.path.join(self.session_dir, session_id)
        uploads_path = os.path.join(session_path, "uploads")
        os.makedirs(uploads_path, exist_ok=True)
        meta = {
            "session_id": session_id,
            "created_at": datetime.now().isoformat(),
            "worktrees": {},
        }
        meta_path = os.path.join(session_path, "meta.json")
        if not os.path.exists(meta_path):
            with open(meta_path, "w", encoding="utf-8") as f:
                json.dump(meta, f, ensure_ascii=False, indent=2)
        return session_id

    def get_session_path(self, session_id: str) -> str:
        return os.path.join(self.session_dir, session_id)

    def get_uploads_path(self, session_id: str) -> str:
        return os.path.join(self.session_dir, session_id, "uploads")

    def get_meta(self, session_id: str) -> dict:
        meta_path = os.path.join(self.session_dir, session_id, "meta.json")
        if os.path.isfile(meta_path):
            with open(meta_path, "r", encoding="utf-8") as f:
                return json.load(f)
        return {}

    def save_meta(self, session_id: str, meta: dict):
        meta_path = os.path.join(self.session_dir, session_id, "meta.json")
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False, indent=2)

    def setup_worktree(self, session_id: str, service_id: str, repo: str,
                       version: str = None, sub_path: str = None) -> str:
        """创建 git worktree，返回代码路径"""
        meta = self.get_meta(session_id)
        worktrees = meta.get("worktrees", {})

        # 已存在且版本相同则复用
        if service_id in worktrees:
            existing = worktrees[service_id]
            if existing.get("version") == (version or "HEAD"):
                code_path = existing["path"]
                if sub_path:
                    code_path = os.path.join(code_path, sub_path)
                if os.path.isdir(code_path):
                    return code_path

        wt_path = os.path.join(self.worktree_base, session_id, service_id)

        # 移除旧 worktree
        if os.path.isdir(wt_path):
            try:
                subprocess.run(
                    ["git", "worktree", "remove", "--force", wt_path],
                    cwd=repo, capture_output=True, timeout=30,
                )
            except Exception:
                shutil.rmtree(wt_path, ignore_errors=True)

        os.makedirs(os.path.dirname(wt_path), exist_ok=True)

        ref = version or "HEAD"
        try:
            result = subprocess.run(
                ["git", "worktree", "add", "--detach", wt_path, ref],
                cwd=repo, capture_output=True, text=True, timeout=60,
            )
            if result.returncode != 0:
                raise RuntimeError(f"git worktree add 失败: {result.stderr.strip()}")
        except subprocess.TimeoutExpired:
            raise RuntimeError("git worktree add 超时")

        worktrees[service_id] = {
            "path": wt_path,
            "repo": repo,
            "version": version or "HEAD",
            "created_at": datetime.now().isoformat(),
        }
        meta["worktrees"] = worktrees
        self.save_meta(session_id, meta)

        code_path = wt_path
        if sub_path:
            code_path = os.path.join(code_path, sub_path)
        logger.info("worktree 已创建: %s @ %s → %s", service_id, ref, code_path)
        return code_path

    def get_loaded_worktrees(self, session_id: str) -> dict:
        """返回当前 session 已加载的 worktree 信息"""
        meta = self.get_meta(session_id)
        return meta.get("worktrees", {})

    def cleanup_session(self, session_id: str):
        """清理 session：移除 worktree + 删除上传文件"""
        meta = self.get_meta(session_id)
        for service_id, wt_info in meta.get("worktrees", {}).items():
            wt_path = wt_info.get("path", "")
            repo = wt_info.get("repo", "")
            if wt_path and os.path.isdir(wt_path):
                try:
                    subprocess.run(
                        ["git", "worktree", "remove", "--force", wt_path],
                        cwd=repo, capture_output=True, timeout=30,
                    )
                except Exception:
                    shutil.rmtree(wt_path, ignore_errors=True)
        wt_session_dir = os.path.join(self.worktree_base, session_id)
        if os.path.isdir(wt_session_dir):
            shutil.rmtree(wt_session_dir, ignore_errors=True)
        session_path = self.get_session_path(session_id)
        if os.path.isdir(session_path):
            shutil.rmtree(session_path, ignore_errors=True)
        logger.info("session 已清理: %s", session_id)

    def cleanup_expired(self):
        """清理过期 session"""
        if not os.path.isdir(self.session_dir):
            return
        now = time.time()
        cleaned = 0
        for name in os.listdir(self.session_dir):
            session_path = os.path.join(self.session_dir, name)
            if not os.path.isdir(session_path):
                continue
            meta_path = os.path.join(session_path, "meta.json")
            try:
                if os.path.isfile(meta_path):
                    with open(meta_path, "r", encoding="utf-8") as f:
                        meta = json.load(f)
                    created = datetime.fromisoformat(meta.get("created_at", ""))
                    age = now - created.timestamp()
                else:
                    age = now - os.path.getmtime(session_path)
            except Exception:
                age = now - os.path.getmtime(session_path)
            if age > self.session_ttl:
                self.cleanup_session(name)
                cleaned += 1
        if cleaned:
            logger.info("已清理 %d 个过期 session", cleaned)


# ── 文件上传处理 ──────────────────────────────────────────

# 允许上传的文件扩展名
ALLOWED_EXTENSIONS = {'.log', '.txt', '.zip', '.tar', '.gz', '.tgz', '.png', '.jpg', '.jpeg'}
# 图片扩展名
IMAGE_EXTENSIONS = {'.png', '.jpg', '.jpeg'}


def is_allowed_file(filename: str) -> bool:
    name_lower = filename.lower()
    for ext in ALLOWED_EXTENSIONS:
        if name_lower.endswith(ext):
            return True
    # .tar.gz
    if name_lower.endswith('.tar.gz'):
        return True
    return False


def is_image_file(filename: str) -> bool:
    return os.path.splitext(filename.lower())[1] in IMAGE_EXTENSIONS


def process_upload(filepath: str, uploads_dir: str) -> list[str]:
    """处理上传文件：压缩包自动解压，返回最终文件路径列表"""
    results = []
    name_lower = filepath.lower()

    if name_lower.endswith('.zip'):
        try:
            extract_dir = filepath + "_extracted"
            os.makedirs(extract_dir, exist_ok=True)
            with zipfile.ZipFile(filepath, 'r') as zf:
                zf.extractall(extract_dir)
            for root, dirs, files in os.walk(extract_dir):
                for f in files:
                    results.append(os.path.join(root, f))
            logger.info("zip 解压完成: %s → %d 个文件", filepath, len(results))
        except Exception as e:
            logger.error("zip 解压失败: %s", e)
            results.append(filepath)

    elif name_lower.endswith('.tar.gz') or name_lower.endswith('.tgz') or name_lower.endswith('.tar'):
        try:
            extract_dir = filepath + "_extracted"
            os.makedirs(extract_dir, exist_ok=True)
            with tarfile.open(filepath, 'r:*') as tf:
                tf.extractall(extract_dir, filter='data')
            for root, dirs, files in os.walk(extract_dir):
                for f in files:
                    results.append(os.path.join(root, f))
            logger.info("tar 解压完成: %s → %d 个文件", filepath, len(results))
        except Exception as e:
            logger.error("tar 解压失败: %s", e)
            results.append(filepath)
    else:
        results.append(filepath)

    return results


# ── 日志预处理 ────────────────────────────────────────────

def extract_log_summary(filepath: str, max_errors: int = 50) -> str:
    """提取日志文件摘要：统计行数、ERROR/WARN 数量、前 N 条错误"""
    if not os.path.isfile(filepath):
        return f"文件不存在: {filepath}"

    total_lines = 0
    error_lines = []
    warn_lines = []

    try:
        with open(filepath, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                total_lines += 1
                upper = line.upper()
                if "ERROR" in upper or "FATAL" in upper:
                    error_lines.append((total_lines, line.rstrip()))
                elif "WARN" in upper:
                    warn_lines.append((total_lines, line.rstrip()))
    except Exception as e:
        return f"读取日志失败: {e}"

    parts = [f"日志文件共 {total_lines} 行"]
    if error_lines:
        parts.append(f"发现 {len(error_lines)} 条 ERROR/FATAL：")
        for lineno, text in error_lines[:max_errors]:
            parts.append(f"  L{lineno}: {text[:200]}")
        if len(error_lines) > max_errors:
            parts.append(f"  ... 还有 {len(error_lines) - max_errors} 条")
    if warn_lines:
        parts.append(f"发现 {len(warn_lines)} 条 WARN")
    if not error_lines and not warn_lines:
        parts.append("未发现 ERROR 或 WARN 级别日志")

    return "\n".join(parts)


def read_log_filtered(filepath: str, level: str = None, keyword: str = None,
                      time_start: str = None, time_end: str = None,
                      context_lines: int = 3, tail: int = None) -> str:
    """按条件过滤读取日志文件"""
    if not os.path.isfile(filepath):
        return f"文件不存在: {filepath}"

    try:
        with open(filepath, "r", encoding="utf-8", errors="replace") as f:
            all_lines = f.readlines()
    except Exception as e:
        return f"读取日志失败: {e}"

    if tail and tail > 0:
        all_lines = all_lines[-tail:]

    # 时间戳正则（常见格式）
    time_re = re.compile(r'(\d{4}[-/]\d{2}[-/]\d{2}[\sT]\d{2}:\d{2}:\d{2})')

    matched_indices = []
    for i, line in enumerate(all_lines):
        # 级别过滤
        if level:
            if level.upper() not in line.upper():
                continue
        # 关键词过滤
        if keyword:
            try:
                if not re.search(keyword, line, re.IGNORECASE):
                    continue
            except re.error:
                if keyword.lower() not in line.lower():
                    continue
        # 时间过滤
        if time_start or time_end:
            m = time_re.search(line)
            if m:
                ts = m.group(1).replace('/', '-')
                if time_start and ts < time_start:
                    continue
                if time_end and ts > time_end:
                    continue
            else:
                continue  # 无时间戳的行跳过时间过滤
        matched_indices.append(i)

    if not matched_indices:
        return "无匹配结果"

    # 收集匹配行及上下文
    output_indices = set()
    for idx in matched_indices:
        for j in range(max(0, idx - context_lines), min(len(all_lines), idx + context_lines + 1)):
            output_indices.add(j)

    result_lines = []
    prev_idx = -2
    for idx in sorted(output_indices):
        if idx > prev_idx + 1:
            result_lines.append("---")
        marker = ">>>" if idx in matched_indices else "   "
        result_lines.append(f"{marker} L{idx + 1}: {all_lines[idx].rstrip()}")
        prev_idx = idx

    total = len(matched_indices)
    header = f"共匹配 {total} 行"
    if total > 200:
        header += f"（仅显示前 200 条）"
        # 截断
        truncated_indices = matched_indices[:200]
        output_indices = set()
        for idx in truncated_indices:
            for j in range(max(0, idx - context_lines), min(len(all_lines), idx + context_lines + 1)):
                output_indices.add(j)
        result_lines = []
        prev_idx = -2
        for idx in sorted(output_indices):
            if idx > prev_idx + 1:
                result_lines.append("---")
            marker = ">>>" if idx in set(truncated_indices) else "   "
            result_lines.append(f"{marker} L{idx + 1}: {all_lines[idx].rstrip()}")
            prev_idx = idx

    return header + "\n" + "\n".join(result_lines)
