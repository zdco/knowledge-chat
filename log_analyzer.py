"""日志分析模块：Session 管理 + git worktree 管理 + 日志预处理"""
import hashlib
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

# tarfile.extractall filter 参数兼容（Python 3.11.4+ 支持）
import inspect as _inspect
_TAR_EXTRACT_KWARGS = {"filter": "data"} if "filter" in _inspect.signature(tarfile.TarFile.extractall).parameters else {}

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
    """加载 services.yaml，返回 {services: dict, businesses: dict}"""
    if not os.path.isfile(config_path):
        return {}
    with open(config_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return data.get("services") or {}


def load_businesses_config(config_path: str) -> dict:
    """加载 services.yaml 中的 businesses 业务线分组"""
    if not os.path.isfile(config_path):
        return {}
    with open(config_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return data.get("businesses") or {}


def scan_service_deps(code_path: str, all_services: dict) -> str:
    """扫描服务代码目录，发现依赖关系线索。

    扫描策略：
    1. 配置文件（.yaml/.yml/.xml/.conf/.properties/.ini/.json）中的服务名、host、port
    2. RPC/接口定义文件（.proto/.thrift/.jce）中的 service 定义和 import
    3. 构建文件（CMakeLists.txt/pom.xml/build.gradle/package.json/go.mod）中的模块依赖
    4. 代码中的 #include、import 引用路径
    5. 与已注册服务列表交叉匹配
    """
    import glob as _glob

    if not os.path.isdir(code_path):
        return f"目录不存在: {code_path}"

    # 构建服务关键词集合：ID、name、aliases
    service_keywords = {}  # keyword_lower -> (service_id, match_type)
    for sid, svc in all_services.items():
        service_keywords[sid.lower()] = (sid, "ID")
        name = svc.get("name", "")
        if name:
            service_keywords[name.lower()] = (sid, "名称")
        for alias in (svc.get("aliases") or []):
            service_keywords[alias.lower()] = (sid, "别名")

    findings = []  # [(category, file_rel, detail, matched_services)]

    def _rel(path):
        return os.path.relpath(path, code_path)

    def _search_file_for_services(filepath, category):
        """在文件内容中搜索已注册服务的关键词"""
        try:
            with open(filepath, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()
        except Exception:
            return
        content_lower = content.lower()
        matched = {}
        for kw, (sid, match_type) in service_keywords.items():
            # 至少 3 个字符才匹配，避免误命中
            if len(kw) < 3:
                continue
            if kw in content_lower:
                if sid not in matched:
                    matched[sid] = match_type
        if matched:
            matches_desc = ", ".join(f"{sid}({mt})" for sid, mt in matched.items())
            findings.append((category, _rel(filepath), matches_desc, set(matched.keys())))

    # 1. 扫描配置文件
    config_patterns = ['**/*.yaml', '**/*.yml', '**/*.xml', '**/*.conf',
                       '**/*.properties', '**/*.ini', '**/*.json']
    config_files = set()
    for pat in config_patterns:
        for fp in _glob.glob(os.path.join(code_path, pat), recursive=True):
            # 跳过 node_modules、.git 等
            if '/.git/' in fp or '/node_modules/' in fp or '/.text_cache/' in fp:
                continue
            config_files.add(fp)
    for fp in config_files:
        _search_file_for_services(fp, "配置文件")

    # 2. 扫描 RPC/接口定义文件
    rpc_patterns = ['**/*.proto', '**/*.thrift', '**/*.jce']
    rpc_files = set()
    for pat in rpc_patterns:
        for fp in _glob.glob(os.path.join(code_path, pat), recursive=True):
            if '/.git/' in fp:
                continue
            rpc_files.add(fp)
    for fp in rpc_files:
        _search_file_for_services(fp, "RPC/接口定义")

    # 同时提取 proto/thrift/jce 中的 service 定义
    _svc_def_re = re.compile(r'(?:service|interface)\s+(\w+)', re.IGNORECASE)
    for fp in rpc_files:
        try:
            with open(fp, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()
            for m in _svc_def_re.finditer(content):
                findings.append(("RPC服务定义", _rel(fp), f"service {m.group(1)}", set()))
        except Exception:
            pass

    # 3. 扫描构建文件
    build_filenames = ['CMakeLists.txt', 'pom.xml', 'build.gradle', 'build.gradle.kts',
                       'package.json', 'go.mod', 'Makefile', 'BUILD', 'WORKSPACE']
    for root, dirs, files in os.walk(code_path):
        dirs[:] = [d for d in dirs if d not in ('.git', 'node_modules', '.text_cache')]
        for fname in files:
            if fname in build_filenames:
                fp = os.path.join(root, fname)
                _search_file_for_services(fp, "构建文件")

    # 4. 扫描代码中的 include/import（只看前 50 行，提高效率）
    code_patterns = ['**/*.cpp', '**/*.h', '**/*.hpp', '**/*.cc',
                     '**/*.java', '**/*.go', '**/*.py', '**/*.cs']
    _include_re = re.compile(r'(?:#include|import|using|require)\s+[<"\'](.*?)[>"\']')
    code_files = set()
    for pat in code_patterns:
        for fp in _glob.glob(os.path.join(code_path, pat), recursive=True):
            if '/.git/' in fp or '/node_modules/' in fp:
                continue
            code_files.add(fp)
    for fp in code_files:
        try:
            with open(fp, "r", encoding="utf-8", errors="replace") as f:
                head_lines = []
                for i, line in enumerate(f):
                    if i >= 50:
                        break
                    head_lines.append(line)
            head_content = "".join(head_lines).lower()
            matched = {}
            for kw, (sid, match_type) in service_keywords.items():
                if len(kw) < 3:
                    continue
                if kw in head_content:
                    if sid not in matched:
                        matched[sid] = match_type
            if matched:
                matches_desc = ", ".join(f"{sid}({mt})" for sid, mt in matched.items())
                findings.append(("代码引用", _rel(fp), matches_desc, set(matched.keys())))
        except Exception:
            pass

    # 汇总结果
    if not findings:
        return "未发现与已注册服务相关的依赖线索。可以尝试手动搜索配置文件中的 host/port 或服务名。"

    # 按匹配到的服务聚合
    dep_services = {}  # sid -> [(category, file, detail)]
    other_findings = []  # 没有匹配到具体服务的发现（如 RPC 定义）
    for category, file_rel, detail, matched_sids in findings:
        if matched_sids:
            for sid in matched_sids:
                dep_services.setdefault(sid, []).append((category, file_rel, detail))
        else:
            other_findings.append((category, file_rel, detail))

    lines = []
    if dep_services:
        lines.append(f"发现 {len(dep_services)} 个可能的依赖服务：")
        lines.append("")
        for sid, refs in dep_services.items():
            svc = all_services.get(sid, {})
            svc_name = svc.get("name", sid)
            lines.append(f"  ▸ {svc_name} ({sid})")
            # 去重，最多显示 5 条
            seen = set()
            count = 0
            for category, file_rel, detail in refs:
                key = (category, file_rel)
                if key in seen:
                    continue
                seen.add(key)
                lines.append(f"    [{category}] {file_rel}")
                count += 1
                if count >= 5:
                    remaining = len(refs) - count
                    if remaining > 0:
                        lines.append(f"    ... 还有 {remaining} 处引用")
                    break
            lines.append("")

    if other_findings:
        lines.append("其他发现：")
        for category, file_rel, detail in other_findings[:20]:
            lines.append(f"  [{category}] {file_rel}: {detail}")

    return "\n".join(lines)


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
        # 禁止 git 弹出交互式认证提示，遇到需要认证时直接报错
        git_env = {**os.environ, "GIT_TERMINAL_PROMPT": "0"}

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
                    env=git_env,
                )
                return local_repo

            # 首次 clone（含 submodule）
            os.makedirs(os.path.dirname(local_repo), exist_ok=True)
            logger.info("克隆仓库: %s → %s", repo, local_repo)
            result = subprocess.run(
                ["git", "clone", "--no-checkout", repo, local_repo],
                capture_output=True, text=True, timeout=300,
                env=git_env,
            )
            if result.returncode != 0:
                # HTTP 认证失败时自动转 SSH 重试
                ssh_url = self._http_to_ssh(repo)
                if ssh_url:
                    logger.info("HTTP clone 失败，尝试 SSH: %s", ssh_url)
                    # 清理失败的目录
                    if os.path.exists(local_repo):
                        shutil.rmtree(local_repo, ignore_errors=True)
                    result = subprocess.run(
                        ["git", "clone", "--no-checkout", ssh_url, local_repo],
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

    @staticmethod
    def _http_to_ssh(url: str) -> str | None:
        """将 HTTP(S) git URL 转为 SSH 格式。

        http(s)://gitlab.example.com/group/project.git
        → git@gitlab.example.com:group/project.git
        """
        m = re.match(r'https?://([^/]+)/(.+)', url)
        if not m:
            return None
        host = m.group(1)
        path = m.group(2)
        return f"git@{host}:{path}"

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
                wt_path = existing["path"]
                if os.path.isdir(wt_path):
                    return wt_path

        # 用仓库名+版本哈希作为 worktree 目录名，同一仓库同一版本共享
        repo_id = actual_repo.rstrip("/").rsplit("/", 1)[-1].replace(".git", "")
        version_hash = hashlib.md5(cache_key.encode()).hexdigest()[:8]
        wt_dir_name = f"{repo_id}_{version_hash}"
        wt_path = os.path.join(self.worktree_base, session_id, wt_dir_name)

        # 检查是否已有其他服务创建了同一个 worktree（同仓库同版本共享）
        if os.path.isdir(wt_path):
            # 已存在，直接复用，只更新 meta
            worktrees[service_id] = {
                "path": wt_path,
                "sub_path": actual_sub_path,
                "repo": actual_repo,
                "version": effective_version,
                "client": client,
                "source_type": "shared",
                "_cache_key": cache_key,
                "created_at": datetime.now().isoformat(),
            }
            meta["worktrees"] = worktrees
            self.save_meta(session_id, meta)
            logger.info("复用已有 worktree: %s → %s (主目录: %s)", service_id, wt_path, actual_sub_path or "/")
            return wt_path

        # 清理该服务之前的 worktree（如果换了仓库或版本）
        if service_id in worktrees:
            old_info = worktrees[service_id]
            old_path = old_info.get("path", "")
            if old_path and old_path != wt_path and os.path.isdir(old_path):
                # 检查是否有其他服务还在用这个 worktree
                other_using = any(
                    sid != service_id and info.get("path") == old_path
                    for sid, info in worktrees.items()
                )
                if not other_using:
                    old_repo = old_info.get("repo", "")
                    if old_repo and self._is_git_repo(old_repo):
                        try:
                            subprocess.run(
                                ["git", "worktree", "remove", "--force", old_path],
                                cwd=old_repo, capture_output=True, timeout=30,
                            )
                        except Exception:
                            pass
                    shutil.rmtree(old_path, ignore_errors=True)

        os.makedirs(os.path.dirname(wt_path), exist_ok=True)

        # 确保 repo 在本地
        local_repo = self._ensure_local_repo(actual_repo)

        if self._is_git_repo(local_repo):
            # git 仓库：用 worktree
            ref = effective_version
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
                tf.extractall(wt_path, **_TAR_EXTRACT_KWARGS)
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

    def get_allowed_paths(self, session_id: str) -> list[str]:
        """返回当前 session 允许访问的路径列表（uploads + 已加载的 worktree）"""
        paths = [self.get_uploads_path(session_id)]
        for wt_info in self.get_loaded_worktrees(session_id).values():
            wt_path = wt_info.get("path", "")
            if wt_path:
                paths.append(wt_path)
        return paths

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

    def touch_session(self, session_id: str):
        """更新 session 最后活跃时间"""
        meta = self.get_meta(session_id)
        if meta:
            meta["last_active"] = datetime.now().isoformat()
            self.save_meta(session_id, meta)

    def cleanup_expired(self):
        """清理过期 session（按最后活跃时间判断）"""
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
                    # 优先用 last_active，没有则用 created_at
                    ts_str = meta.get("last_active") or meta.get("created_at", "")
                    age = now - datetime.fromisoformat(ts_str).timestamp()
                else:
                    age = now - os.path.getmtime(session_path)
            except Exception:
                age = now - os.path.getmtime(session_path)
            if age > self.session_ttl:
                self.cleanup_session(name)
                cleaned += 1
        if cleaned:
            logger.info("已清理 %d 个过期 session", cleaned)

    def start_cleanup_timer(self, interval: int = 3600):
        """启动定时清理线程，默认每小时执行一次"""
        import threading

        def _loop():
            while True:
                time.sleep(interval)
                try:
                    self.cleanup_expired()
                except Exception as e:
                    logger.error("定时清理 session 失败: %s", e)

        t = threading.Thread(target=_loop, daemon=True)
        t.start()
        logger.info("session 定时清理已启动，间隔 %d 秒", interval)


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
                tf.extractall(extract_dir, **_TAR_EXTRACT_KWARGS)
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
