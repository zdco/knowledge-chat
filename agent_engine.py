"""全能 Agent 引擎：知识域动态加载 + 工具定义 + 执行 + Claude API 流式调用"""
import os
import json
import subprocess
import glob as glob_mod
import time
import contextvars
import urllib.request
import urllib.error
import threading
import logging

import yaml
import anthropic
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

# Office 文件扩展名集合
_OFFICE_EXTS = {'.xlsx', '.xls', '.docx', '.pptx'}

# ── 加载配置 ──────────────────────────────────────────────

_DIR = os.path.dirname(__file__)
_CONFIG_PATH = os.path.join(_DIR, "config.yaml")


def _load_config() -> dict:
    with open(_CONFIG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


CONFIG = _load_config()

BASE_URL = os.environ.get("ANTHROPIC_BASE_URL", CONFIG["api"]["base_url"])
API_KEY = os.environ.get("ANTHROPIC_AUTH_TOKEN", CONFIG["api"]["api_key"])
MODEL = os.environ.get("ANTHROPIC_MODEL", CONFIG["api"]["model"])
MAX_TOKENS = CONFIG["api"]["max_tokens"]
MAX_ITERATIONS = CONFIG["api"]["max_iterations"]
MAX_OUTPUT_LEN = CONFIG["tools"]["max_output_length"]
MAX_DISPLAY_LEN = CONFIG["tools"]["max_display_length"]

PROJECT_ROOT = os.path.abspath(os.path.join(_DIR, "..", "..", ".."))

# ── 知识域加载 ────────────────────────────────────────────

_KNOWLEDGE_DIR = os.path.join(_DIR, "knowledge")


def load_knowledge_domains() -> list[dict]:
    """扫描 knowledge/*/domain.yaml，返回知识域列表（跳过 _template）"""
    domains = []
    if not os.path.isdir(_KNOWLEDGE_DIR):
        return domains
    for dname in sorted(os.listdir(_KNOWLEDGE_DIR)):
        if dname.startswith("_") or dname.startswith("."):
            continue
        domain_dir = os.path.join(_KNOWLEDGE_DIR, dname)
        if not os.path.isdir(domain_dir):
            continue
        fpath = os.path.join(domain_dir, "domain.yaml")
        if not os.path.isfile(fpath):
            continue
        with open(fpath, "r", encoding="utf-8") as f:
            domain = yaml.safe_load(f)
        if domain and isinstance(domain, dict):
            # 解析 data_path 为绝对路径，追加到 search_paths
            data_path = domain.get("data_path")
            if data_path:
                abs_data_path = os.path.normpath(os.path.join(domain_dir, data_path))
                domain["_abs_data_path"] = abs_data_path
                # 计算相对于项目根目录的路径，追加到 search_paths
                rel_data_path = os.path.relpath(abs_data_path, PROJECT_ROOT)
                search_paths = domain.get("search_paths", [])
                if rel_data_path not in search_paths:
                    search_paths.append(rel_data_path)
                    domain["search_paths"] = search_paths

            # Confluence zip 自动转换
            confluence_zip = domain.get("confluence_zip")
            if confluence_zip:
                zip_path = os.path.join(domain_dir, confluence_zip)
                wiki_dir = os.path.join(
                    abs_data_path if data_path else domain_dir, "wiki"
                )
                if os.path.isfile(zip_path):
                    try:
                        from confluence_converter import convert_confluence_zip
                        convert_confluence_zip(zip_path, wiki_dir, domain.get("name", dname))
                    except Exception as e:
                        logging.getLogger(__name__).error(
                            "Confluence 转换失败 [%s]: %s", dname, e, exc_info=True
                        )

            domains.append(domain)
    return domains


KNOWLEDGE_DOMAINS = load_knowledge_domains()

_domains_lock = threading.Lock()
logger = logging.getLogger(__name__)
request_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("request_id", default="-")


def reload_domains():
    """重新加载所有知识域并重建 system prompt"""
    global KNOWLEDGE_DOMAINS, SYSTEM_PROMPT
    new_domains = load_knowledge_domains()
    with _domains_lock:
        KNOWLEDGE_DOMAINS.clear()
        KNOWLEDGE_DOMAINS.extend(new_domains)
        SYSTEM_PROMPT = build_system_prompt()
    logger.info("知识域已热加载，当前 %d 个域", len(KNOWLEDGE_DOMAINS))


class _DomainFileHandler(FileSystemEventHandler):
    """监听 knowledge/*/domain.yaml 变化，防抖 1 秒后触发 reload"""

    def __init__(self):
        self._timer: threading.Timer | None = None

    def _schedule_reload(self):
        if self._timer is not None:
            self._timer.cancel()
        self._timer = threading.Timer(1.0, reload_domains)
        self._timer.daemon = True
        self._timer.start()

    def _is_domain_yaml(self, path: str) -> bool:
        return os.path.basename(path) == "domain.yaml"

    def on_created(self, event):
        if not event.is_directory and self._is_domain_yaml(event.src_path):
            self._schedule_reload()

    def on_modified(self, event):
        if not event.is_directory and self._is_domain_yaml(event.src_path):
            self._schedule_reload()

    def on_deleted(self, event):
        if not event.is_directory and self._is_domain_yaml(event.src_path):
            self._schedule_reload()


_observer: Observer | None = None


def start_watcher():
    """启动 watchdog 监听 knowledge/ 目录变化"""
    global _observer
    if _observer is not None:
        return
    if not os.path.isdir(_KNOWLEDGE_DIR):
        return
    _observer = Observer()
    _observer.schedule(_DomainFileHandler(), _KNOWLEDGE_DIR, recursive=True)
    _observer.daemon = True
    _observer.start()
    logger.info("知识域文件监听已启动: %s", _KNOWLEDGE_DIR)


def build_system_prompt() -> str:
    """合并通用指令 + 各知识域 prompt 片段，生成总 system prompt"""
    parts = [
        f"你是全能 AI 助手。你可以使用工具搜索代码、文档和配置来回答各领域的问题。",
        f"",
        f"项目根目录：{PROJECT_ROOT}",
        f"",
        f"回答规范：",
        f"- 用中文回答",
        f"- 引用具体文件和行号",
        f"- 用 Markdown 表格展示参数",
        f"- 给出代码示例时标注语言",
        f"",
        f"知识域管理：",
        f"- 当用户提供文件路径或资料，要求创建/添加知识域时，先用 read_file 读取 {os.path.join(PROJECT_ROOT, 'AI_GUIDE.md')} 获取完整流程",
        f"- 按照指南扫描分析文件、拷贝资料到 knowledge/<域名>/data/、生成 domain.yaml",
        f"- domain.yaml 保存后会自动热加载生效，无需重启服务",
        f"",
        f"学习记忆：",
        f"- 知识域级别笔记目录：knowledge/<域名>/memory/",
        f"- 全局笔记目录：knowledge/_memory/",
        f"- 遇到相关问题时，先用 search 搜索 memory/ 目录查找已有笔记",
        f"- 如果引用了笔记但发现内容已过时，立即用 write_file 更新该笔记",
        f"",
        f"何时记录（按优先级）：",
        f"1. 用户纠正了你的错误 → 记录正确结论，防止再犯",
        f'2. 用户提供了文档中没有的隐性知识（如"这个字段虽然叫 status 但实际存的是时间戳"）',
        f"3. 经过反复搜索仍难以定位、最终通过多线索交叉验证才得出的结论 → 记录最终结果和定位路径，下次直接用",
        f"4. 可复用的查询模板、排查步骤、配置套路",
        f"",
        f"不记录：",
        f"- 单次搜索就能回答的简单问题",
        f"- 临时性数据查询结果（具体数值会变）",
        f"- 源码/文档中已明确记载的内容",
        f"",
        f"写入规则：",
        f"- 在回答用户问题的同一轮回复中，如果判断需要记录，同时调用 write_file 写入笔记（文本回答和工具调用一起返回）",
        f"- 写入前 search memory/ 检查是否已有相关笔记，有则更新同一文件而非新建",
        f"- 笔记归属明确的知识域时写到该域的 memory/，否则写到 knowledge/_memory/",
        f"- 文件名格式：YYYY-MM-DD_NNN.md（如 2026-03-08_001.md）",
        f"- 每条笔记开头标注 [学习笔记]，正文控制在 500 字以内",
        f"",
        f"你具备以下知识域，请根据用户问题自动判断所属领域并搜索对应路径：",
    ]

    for domain in KNOWLEDGE_DOMAINS:
        parts.append("")
        prompt_text = domain.get("prompt", "").strip()
        if prompt_text:
            parts.append(prompt_text)
        # 列出搜索路径供 AI 参考
        search_paths = domain.get("search_paths", [])
        if search_paths:
            parts.append(f"  搜索路径：{', '.join(search_paths)}")
        # 列出数据文件目录
        abs_data_path = domain.get("_abs_data_path")
        if abs_data_path:
            parts.append(f"  数据文件目录：{abs_data_path}")

    # 注入数据库连接信息
    db_sections = []
    for domain in KNOWLEDGE_DOMAINS:
        databases = domain.get("databases")
        if not databases:
            continue
        domain_name = domain.get("name", "未命名")
        for db in databases:
            db_type = db.get("type", "unknown")
            info_parts = [f"  - 名称: {db.get('name', '未命名')}"]
            info_parts.append(f"    类型: {db_type}")
            info_parts.append(f"    host: {db.get('host', '')}")
            info_parts.append(f"    port: {db.get('port', '')}")
            if db.get("service_name"):
                info_parts.append(f"    service_name: {db['service_name']}")
            if db.get("database"):
                info_parts.append(f"    database: {db['database']}")
            info_parts.append(f"    user: {db.get('user', '')}")
            info_parts.append(f"    password: {db.get('password', '')}")
            db_sections.append((domain_name, "\n".join(info_parts), db_type))

    if db_sections:
        parts.append("")
        parts.append("## 可用数据库")
        parts.append("你可以使用 run_python 工具编写 Python 代码连接以下数据库进行查询和分析：")
        for domain_name, info, db_type in db_sections:
            parts.append(f"")
            parts.append(f"【{domain_name}】")
            parts.append(info)
        parts.append("")
        parts.append("数据库驱动使用说明：")
        parts.append("- MySQL: 使用 pymysql 库连接")
        parts.append("- Oracle: 使用 oracledb 库连接（thin 模式，无需 Oracle Client）")
        parts.append("- 推荐使用 pandas 读取查询结果并格式化输出")
        parts.append("- 查询时注意加 LIMIT/ROWNUM 限制返回行数，避免数据量过大")

    return "\n".join(parts)


SYSTEM_PROMPT = build_system_prompt()

# ── 工具定义 ──────────────────────────────────────────────

TOOLS = [
    {
        "name": "search",
        "description": "在项目中搜索关键词，返回匹配行及上下文。支持正则。",
        "input_schema": {
            "type": "object",
            "properties": {
                "keyword": {"type": "string", "description": "搜索关键词或正则表达式"},
                "path": {"type": "string", "description": "搜索路径（相对项目根目录），默认整个项目"},
                "context_lines": {"type": "integer", "description": "上下文行数，默认 3"},
            },
            "required": ["keyword"],
        },
    },
    {
        "name": "read_file",
        "description": "读取文件内容，支持指定行范围。",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "文件路径（相对项目根目录）"},
                "start_line": {"type": "integer", "description": "起始行号（从1开始）"},
                "end_line": {"type": "integer", "description": "结束行号"},
            },
            "required": ["path"],
        },
    },
    {
        "name": "write_file",
        "description": "写入或创建文件（如生成示例代码）。",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "文件路径（相对项目根目录）"},
                "content": {"type": "string", "description": "文件内容"},
            },
            "required": ["path", "content"],
        },
    },
    {
        "name": "list_files",
        "description": "列出目录下的文件和子目录。",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "目录路径（相对项目根目录），默认根目录"},
            },
        },
    },
    {
        "name": "glob",
        "description": "按 glob 模式匹配文件路径，如 '**/*.jce'。",
        "input_schema": {
            "type": "object",
            "properties": {
                "pattern": {"type": "string", "description": "glob 模式"},
                "path": {"type": "string", "description": "起始目录（相对项目根目录），默认根目录"},
            },
            "required": ["pattern"],
        },
    },
    {
        "name": "bash",
        "description": "执行 shell 命令（如 wc、head、diff 等辅助操作）。",
        "input_schema": {
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "要执行的命令"},
            },
            "required": ["command"],
        },
    },
    {
        "name": "web_fetch",
        "description": "抓取网页内容（如在线文档、API 说明）。",
        "input_schema": {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "网页 URL"},
            },
            "required": ["url"],
        },
    },
    {
        "name": "run_python",
        "description": "执行 Python 代码，可用于数据库查询、数据分析、数据处理等。",
        "input_schema": {
            "type": "object",
            "properties": {
                "code": {"type": "string", "description": "要执行的 Python 代码"},
            },
            "required": ["code"],
        },
    },
]

# ── 工具执行 ──────────────────────────────────────────────


def _safe_path(rel: str) -> str:
    """将相对路径转为绝对路径，限制在项目根目录内"""
    abs_path = os.path.normpath(os.path.join(PROJECT_ROOT, rel))
    if not abs_path.startswith(PROJECT_ROOT):
        return PROJECT_ROOT
    return abs_path


def _read_office_file(fpath: str) -> str:
    """根据扩展名解析 Office 文件，返回纯文本内容"""
    ext = os.path.splitext(fpath)[1].lower()

    if ext in ('.xlsx', '.xls'):
        import openpyxl
        wb = openpyxl.load_workbook(fpath, read_only=True, data_only=True)
        parts = []
        for sheet in wb.sheetnames:
            ws = wb[sheet]
            parts.append(f"=== Sheet: {sheet} ===")
            for row in ws.iter_rows(values_only=True):
                parts.append("\t".join(str(c) if c is not None else "" for c in row))
        wb.close()
        return "\n".join(parts)

    if ext == '.docx':
        import docx
        doc = docx.Document(fpath)
        return "\n".join(p.text for p in doc.paragraphs)

    if ext == '.pptx':
        from pptx import Presentation
        prs = Presentation(fpath)
        parts = []
        for i, slide in enumerate(prs.slides, 1):
            texts = []
            for shape in slide.shapes:
                if shape.has_text_frame:
                    texts.append(shape.text_frame.text)
            if texts:
                parts.append(f"=== Slide {i} ===")
                parts.append("\n".join(texts))
        return "\n".join(parts)

    return ""


def exec_tool(name: str, inp: dict) -> str:
    """执行工具，返回结果字符串"""
    logger.info("执行工具: %s, 参数: %s", name, json.dumps(inp, ensure_ascii=False)[:500])
    t0 = time.time()
    try:
        if name == "search":
            keyword = inp["keyword"]
            path = _safe_path(inp.get("path", ""))
            ctx = str(inp.get("context_lines", 3))
            result = subprocess.run(
                ["grep", "-r", "-n", f"-C{ctx}", "--exclude-dir=logs",
                 "--include=*.jce",
                 "--include=*.h", "--include=*.cpp", "--include=*.md",
                 "--include=*.conf", "--include=*.xml", "--include=*.yaml",
                 "--include=*.yml", "--include=*.txt", "--include=*.sh",
                 keyword, path],
                capture_output=True, text=True, timeout=30,
            )
            output = result.stdout or result.stderr or "无匹配结果"

            # 搜索 Office 文件
            import re
            office_matches = []
            for ext in _OFFICE_EXTS:
                for fpath in glob_mod.glob(os.path.join(path, "**", f"*{ext}"), recursive=True):
                    try:
                        text = _read_office_file(fpath)
                        rel_path = os.path.relpath(fpath, PROJECT_ROOT)
                        for line_no, line in enumerate(text.splitlines(), 1):
                            if re.search(keyword, line, re.IGNORECASE):
                                office_matches.append(f"{rel_path}:{line_no}: {line}")
                    except Exception:
                        continue
            if office_matches:
                if output == "无匹配结果":
                    output = "\n".join(office_matches)
                else:
                    output += "\n" + "\n".join(office_matches)

        elif name == "read_file":
            fpath = _safe_path(inp["path"])
            ext = os.path.splitext(fpath)[1].lower()
            if ext in _OFFICE_EXTS:
                output = _read_office_file(fpath) or "(空文件)"
            else:
                with open(fpath, "r", encoding="utf-8", errors="replace") as f:
                    lines = f.readlines()
                start = max(1, inp.get("start_line", 1))
                end = inp.get("end_line", len(lines))
                selected = lines[start - 1:end]
                output = "".join(f"{start + i}: {l}" for i, l in enumerate(selected))

        elif name == "write_file":
            fpath = _safe_path(inp["path"])
            os.makedirs(os.path.dirname(fpath), exist_ok=True)
            with open(fpath, "w", encoding="utf-8") as f:
                f.write(inp["content"])
            output = f"已写入 {fpath}"

        elif name == "list_files":
            dpath = _safe_path(inp.get("path", ""))
            entries = sorted(os.listdir(dpath))
            output = "\n".join(entries) if entries else "空目录"

        elif name == "glob":
            base = _safe_path(inp.get("path", ""))
            pattern = inp["pattern"]
            matches = sorted(glob_mod.glob(os.path.join(base, pattern), recursive=True))
            rel = [os.path.relpath(m, PROJECT_ROOT) for m in matches]
            output = "\n".join(rel) if rel else "无匹配文件"

        elif name == "bash":
            result = subprocess.run(
                inp["command"], shell=True, capture_output=True, text=True,
                timeout=30, cwd=PROJECT_ROOT,
            )
            output = (result.stdout + result.stderr).strip() or "(无输出)"

        elif name == "web_fetch":
            req = urllib.request.Request(inp["url"], headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=15) as resp:
                output = resp.read().decode("utf-8", errors="replace")

        elif name == "run_python":
            import tempfile
            code = inp["code"]
            with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False, encoding="utf-8") as f:
                f.write(code)
                tmp_path = f.name
            try:
                timeout = CONFIG["tools"].get("python_timeout", 300)
                result = subprocess.run(
                    ["python3", tmp_path],
                    capture_output=True, text=True,
                    timeout=timeout, cwd=PROJECT_ROOT,
                )
                output = (result.stdout + result.stderr).strip() or "(无输出)"
            except subprocess.TimeoutExpired:
                output = f"执行超时（{timeout}秒），代码已终止"
            finally:
                os.unlink(tmp_path)

        else:
            output = f"未知工具: {name}"

    except Exception as e:
        logger.error("工具执行错误: %s, %s", name, e, exc_info=True)
        output = f"工具执行错误: {e}"

    elapsed = time.time() - t0
    if len(output) > MAX_OUTPUT_LEN:
        output = output[:MAX_OUTPUT_LEN] + f"\n... (截断，共 {len(output)} 字符)"
    logger.info("工具完成: %s, 耗时: %.2fs, 结果长度: %d", name, elapsed, len(output))
    return output


# ── Agent 流式调用 ────────────────────────────────────────

def run_agent_stream(messages: list):
    """Agent 循环：流式调用 Claude，自动执行工具，yield SSE 事件"""
    client = anthropic.Anthropic(base_url=BASE_URL, api_key=API_KEY)

    for iteration in range(MAX_ITERATIONS):
        logger.info("调用 Claude API, 第 %d 轮", iteration + 1)
        try:
            with client.messages.stream(
                model=MODEL,
                max_tokens=MAX_TOKENS,
                system=SYSTEM_PROMPT,
                messages=messages,
                tools=TOOLS,
            ) as stream:
                # 流式输出文本
                for event in stream:
                    if event.type == "content_block_delta":
                        delta = event.delta
                        if hasattr(delta, "text"):
                            yield {"event": "text_delta", "data": {"delta": delta.text}}

                final_message = stream.get_final_message()

            logger.info("API 返回, usage: %s", final_message.usage)

        except Exception as e:
            logger.error("API 调用失败: %s", e, exc_info=True)
            yield {"event": "error", "data": {"message": str(e)}}
            yield {"event": "done", "data": {}}
            return

        messages.append({"role": "assistant", "content": final_message.content})

        tool_blocks = [b for b in final_message.content if b.type == "tool_use"]

        if not tool_blocks:
            yield {"event": "done", "data": {}}
            return

        tool_results = []
        for tb in tool_blocks:
            yield {"event": "tool_start", "data": {"tool": tb.name, "input": tb.input}}

            result = exec_tool(tb.name, tb.input)

            yield {"event": "tool_result", "data": {"tool": tb.name, "output": result[:MAX_DISPLAY_LEN]}}

            tool_results.append({
                "type": "tool_result",
                "tool_use_id": tb.id,
                "content": result,
            })

        messages.append({"role": "user", "content": tool_results})

    logger.warning("达到最大迭代次数 %d", MAX_ITERATIONS)
    yield {"event": "error", "data": {"message": "达到最大迭代次数"}}
    yield {"event": "done", "data": {}}
