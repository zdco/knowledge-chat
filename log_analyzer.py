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


# ── Git URL 解析 ──────────────────────────────────────────

# 匹配 GitLab/GitHub 的 /tree/branch/path 或 /-/tree/branch/path 格式
# 仓库路径支持任意层级（GitLab 支持嵌套 group）
_TREE_URL_RE = re.compile(
    r'^(https?://[^/]+/.+?)(?:/-)?/tree/([^/]+)(?:/(.+?))?/?$'
)


def parse_repo_url(url: str) -> tuple[str, str | None, str | None]:
    """解析 git 仓库 URL，自动提取分支和子路径。

    支持格式：
      http://gitlab.example.com/group/project/tree/dev/some/path
      http://gitlab.example.com/group/project/-/tree/dev/some/path
      http://gitlab.example.com/group/project.git
      git@gitlab.example.com:group/project.git

    Returns:
        (repo_url, branch, sub_path)
        branch 和 sub_path 可能为 None
    """
    if not url:
        return url, None, None

    m = _TREE_URL_RE.match(url.strip())
    if m:
        repo_url = m.group(1) + ".git"
        branch = m.group(2)
        sub_path = m.group(3) or None
        return repo_url, branch, sub_path

    # 普通 URL 或本地路径，原样返回
    return url, None, None


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

    def _ensure_local_repo(self, repo: str) -> str:
        """确保 repo 在本地可用。远程 URL 自动 clone 到 repos_dir，本地路径直接返回。"""
        # 判断是否为远程 URL
        if repo.startswith(("http://", "https://", "git@", "ssh://")):
            # 从 URL 提取仓库名
            repo_name = repo.rstrip("/").rsplit("/", 1)[-1]
            if repo_name.endswith(".git"):
                repo_name = repo_name[:-4]
            local_repo = os.path.join(self.worktree_base, "_repos", repo_name)

            if os.path.isdir(os.path.join(local_repo, ".git")):
                # 已 clone，fetch 更新
                logger.info("更新仓库: %s", repo_name)
                subprocess.run(
                    ["git", "fetch", "--all", "--tags"],
                    cwd=local_repo, capture_output=True, timeout=120,
                )
                return local_repo

            # 首次 clone（含 submodule）
            os.makedirs(os.path.dirname(local_repo), exist_ok=True)
            logger.info("克隆仓库: %s → %s", repo, local_repo)
            result = subprocess.run(
                ["git", "clone", "--no-checkout", repo, local_repo],
                capture_output=True, text=True, timeout=300,
            )
            if result.returncode != 0:
                raise RuntimeError(f"git clone 失败: {result.stderr.strip()}")
            # 初始化 submodule 配置（不 checkout，只注册）
            subprocess.run(
                ["git", "submodule", "init"],
                cwd=local_repo, capture_output=True, timeout=60,
            )
            return local_repo

        # 本地路径
        if not os.path.isdir(repo):
            raise RuntimeError(f"仓库路径不存在: {repo}")
        return repo

    def _is_git_repo(self, path: str) -> bool:
        """判断路径是否为 git 仓库"""
        return os.path.isdir(os.path.join(path, ".git"))

    def setup_code(self, session_id: str, service_id: str, repo: str,
                   version: str = None, sub_path: str = None,
                   client: str = None, client_repos: dict = None) -> str:
        """加载服务代码到 session，支持 git worktree / 普通目录复制。返回代码路径。

        Args:
            repo: 默认仓库路径（本地路径或远程 URL）
            version: 版本（branch/tag/commit hash），由用户在对话中提供，默认 HEAD
            sub_path: 默认 monorepo 子路径
            client: 客户名（可选），用于查找客户专属仓库
            client_repos: 客户仓库映射，如：
                {"客户A": {"repo": "git@old-gitlab:xxx.git"}}
                {"客户B": {"repo": "/data/code/xxx", "sub_path": "src"}}
                {"客户C": "git@another:xxx.git"}  # 简写，只有 repo
        """
        meta = self.get_meta(session_id)
        worktrees = meta.get("worktrees", {})

        # 根据客户名查找对应仓库
        actual_repo = repo
        actual_sub_path = sub_path
        if client and client_repos and client in client_repos:
            cr = client_repos[client]
            if isinstance(cr, dict):
                actual_repo = cr.get("repo", repo)
                actual_sub_path = cr.get("sub_path", sub_path)
            else:
                # 简写：值就是 repo 地址
                actual_repo = cr

        # 解析 URL 中的分支和子路径（如 gitlab /tree/dev/some/path）
        parsed_repo, parsed_branch, parsed_sub_path = parse_repo_url(actual_repo)
        actual_repo = parsed_repo
        if parsed_branch and not version:
            version = parsed_branch
        if parsed_sub_path and not actual_sub_path:
            actual_sub_path = parsed_sub_path

        effective_version = version or "HEAD"
        cache_key = f"{actual_repo}@{effective_version}"

        # 已存在且版本相同则复用
        if service_id in worktrees:
            existing = worktrees[service_id]
            if existing.get("_cache_key") == cache_key:
                code_path = existing["path"]
                if actual_sub_path:
                    code_path = os.path.join(code_path, actual_sub_path)
                if os.path.isdir(code_path):
                    return code_path

        wt_path = os.path.join(self.worktree_base, session_id, service_id)

        # 清理旧目录
        if os.path.isdir(wt_path):
            # 尝试 git worktree remove
            old_info = worktrees.get(service_id, {})
            old_repo = old_info.get("repo", "")
            if old_repo and self._is_git_repo(old_repo):
                try:
                    subprocess.run(
                        ["git", "worktree", "remove", "--force", wt_path],
                        cwd=old_repo, capture_output=True, timeout=30,
                    )
                except Exception:
                    pass
            shutil.rmtree(wt_path, ignore_errors=True)

        os.makedirs(os.path.dirname(wt_path), exist_ok=True)

        # 确保 repo 在本地
        local_repo = self._ensure_local_repo(actual_repo)

        if self._is_git_repo(local_repo):
            # git 仓库：用 worktree
            ref = resolved_version or "HEAD"
            try:
                result = subprocess.run(
                    ["git", "worktree", "add", "--detach", wt_path, ref],
                    cwd=local_repo, capture_output=True, text=True, timeout=60,
                )
                if result.returncode != 0:
                    raise RuntimeError(f"git worktree add 失败: {result.stderr.strip()}")
            except subprocess.TimeoutExpired:
                raise RuntimeError("git worktree add 超时")
            # 初始化并拉取 submodule（如果有）
            subprocess.run(
                ["git", "submodule", "update", "--init", "--recursive"],
                cwd=wt_path, capture_output=True, timeout=300,
            )
            source_type = "worktree"
        else:
            # 非 git 目录：直接复制（或 symlink）
            shutil.copytree(local_repo, wt_path, dirs_exist_ok=True,
                            ignore=shutil.ignore_patterns('.git', '__pycache__', 'node_modules'))
            source_type = "copy"

        worktrees[service_id] = {
            "path": wt_path,
            "sub_path": actual_sub_path,
            "repo": local_repo,
            "version": effective_version,
            "client": client,
            "source_type": source_type,
            "_cache_key": cache_key,
            "created_at": datetime.now().isoformat(),
        }
        meta["worktrees"] = worktrees
        self.save_meta(session_id, meta)

        # 返回仓库根路径（不拼接 sub_path），让 AI 能搜索整个仓库
        # sub_path 作为提示信息，告诉 AI 主代码在哪个子目录
        logger.info("代码已加载: %s @ %s → %s (主目录: %s) (%s)",
                     service_id, effective_version, wt_path, actual_sub_path or "/", source_type)
        return wt_path

    def setup_from_upload(self, session_id: str, service_id: str, archive_path: str,
                          sub_path: str = None) -> str:
        """从上传的代码压缩包加载服务代码。返回代码路径。"""
        meta = self.get_meta(session_id)
        worktrees = meta.get("worktrees", {})

        wt_path = os.path.join(self.worktree_base, session_id, service_id)
        if os.path.isdir(wt_path):
            shutil.rmtree(wt_path, ignore_errors=True)
        os.makedirs(wt_path, exist_ok=True)

        # 解压
        name_lower = archive_path.lower()
        if name_lower.endswith('.zip'):
            with zipfile.ZipFile(archive_path, 'r') as zf:
                zf.extractall(wt_path)
        elif name_lower.endswith(('.tar.gz', '.tgz', '.tar')):
            with tarfile.open(archive_path, 'r:*') as tf:
                tf.extractall(wt_path, filter='data')
        else:
            raise RuntimeError(f"不支持的压缩格式: {archive_path}")

        # 如果解压后只有一个顶层目录，进入该目录
        entries = os.listdir(wt_path)
        if len(entries) == 1 and os.path.isdir(os.path.join(wt_path, entries[0])):
            actual_path = os.path.join(wt_path, entries[0])
        else:
            actual_path = wt_path

        worktrees[service_id] = {
            "path": actual_path,
            "repo": archive_path,
            "version": "uploaded",
            "source_type": "upload",
            "created_at": datetime.now().isoformat(),
        }
        meta["worktrees"] = worktrees
        self.save_meta(session_id, meta)

        code_path = actual_path
        if sub_path:
            code_path = os.path.join(code_path, sub_path)
        logger.info("代码已从压缩包加载: %s → %s", service_id, code_path)
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
