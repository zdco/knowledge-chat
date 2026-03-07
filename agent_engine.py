"""全能 Agent 引擎：知识域动态加载 + 工具定义 + 执行 + Claude API 流式调用"""
import os
import json
import subprocess
import glob as glob_mod
import urllib.request
import urllib.error

import yaml
import anthropic

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
            domains.append(domain)
    return domains


KNOWLEDGE_DOMAINS = load_knowledge_domains()


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
]

# ── 工具执行 ──────────────────────────────────────────────


def _safe_path(rel: str) -> str:
    """将相对路径转为绝对路径，限制在项目根目录内"""
    abs_path = os.path.normpath(os.path.join(PROJECT_ROOT, rel))
    if not abs_path.startswith(PROJECT_ROOT):
        return PROJECT_ROOT
    return abs_path


def exec_tool(name: str, inp: dict) -> str:
    """执行工具，返回结果字符串"""
    try:
        if name == "search":
            keyword = inp["keyword"]
            path = _safe_path(inp.get("path", ""))
            ctx = str(inp.get("context_lines", 3))
            result = subprocess.run(
                ["grep", "-r", "-n", f"-C{ctx}", "--include=*.jce",
                 "--include=*.h", "--include=*.cpp", "--include=*.md",
                 "--include=*.conf", "--include=*.xml", "--include=*.yaml",
                 "--include=*.yml", "--include=*.txt", "--include=*.sh",
                 keyword, path],
                capture_output=True, text=True, timeout=30,
            )
            output = result.stdout or result.stderr or "无匹配结果"

        elif name == "read_file":
            fpath = _safe_path(inp["path"])
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

        else:
            output = f"未知工具: {name}"

    except Exception as e:
        output = f"工具执行错误: {e}"

    if len(output) > MAX_OUTPUT_LEN:
        output = output[:MAX_OUTPUT_LEN] + f"\n... (截断，共 {len(output)} 字符)"
    return output


# ── Agent 流式调用 ────────────────────────────────────────

def run_agent_stream(messages: list):
    """Agent 循环：流式调用 Claude，自动执行工具，yield SSE 事件"""
    client = anthropic.Anthropic(base_url=BASE_URL, api_key=API_KEY)

    for _ in range(MAX_ITERATIONS):
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

        except Exception as e:
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

    yield {"event": "error", "data": {"message": "达到最大迭代次数"}}
    yield {"event": "done", "data": {}}
