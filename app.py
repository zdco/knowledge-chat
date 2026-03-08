"""Flask 主应用 - 全能 AI 助手"""
import hashlib
import json
import logging
import os
import uuid
from datetime import datetime
from logging.handlers import TimedRotatingFileHandler

from flask import Flask, render_template, request, Response, send_from_directory

from agent_engine import run_agent_stream, CONFIG, KNOWLEDGE_DOMAINS, start_watcher, request_id_var

# ── 日志初始化 ────────────────────────────────────────────
_log_cfg = CONFIG.get("logging", {})
_log_level = getattr(logging, _log_cfg.get("level", "INFO").upper(), logging.INFO)
_log_file = _log_cfg.get("file", "logs/app.log")
_log_backup_days = _log_cfg.get("backup_days", 30)
_log_format = "%(asctime)s %(levelname)s [%(name)s] [%(request_id)s] %(message)s"

os.makedirs(os.path.dirname(_log_file), exist_ok=True)


class _RequestIdFilter(logging.Filter):
    def filter(self, record):
        record.request_id = request_id_var.get("-")
        return True


_formatter = logging.Formatter(_log_format)

_console_handler = logging.StreamHandler()
_console_handler.setFormatter(_formatter)

_file_handler = TimedRotatingFileHandler(
    _log_file, when="midnight", backupCount=_log_backup_days, encoding="utf-8"
)
_file_handler.setFormatter(_formatter)

logging.basicConfig(level=_log_level, handlers=[_console_handler, _file_handler])
logging.getLogger().addFilter(_RequestIdFilter())

logger = logging.getLogger(__name__)

app = Flask(__name__)
start_watcher()

SHARES_DIR = os.path.join(os.path.dirname(__file__), "shares")
os.makedirs(SHARES_DIR, exist_ok=True)


def _get_examples() -> list[dict]:
    """从所有知识域收集示例问题，按域分组"""
    groups = []
    for domain in KNOWLEDGE_DOMAINS:
        name = domain.get("name", "")
        examples = domain.get("examples", [])
        if examples:
            groups.append({"name": name, "examples": examples})
    return groups


@app.route("/chat")
def chat_page():
    return render_template("chat.html", example_groups=_get_examples())


@app.route("/api/chat", methods=["POST"])
def chat_api():
    data = request.get_json()
    user_message = data.get("message", "").strip()
    history = data.get("history", [])

    if not user_message:
        return {"error": "消息不能为空"}, 400

    req_id = uuid.uuid4().hex[:8]
    request_id_var.set(req_id)
    client_ip = request.headers.get("X-Forwarded-For", request.headers.get("X-Real-IP", request.remote_addr))
    logger.info("收到请求: %s [来源: %s]", user_message[:200], client_ip)

    messages = list(history)
    messages.append({"role": "user", "content": user_message})

    def generate():
        for event in run_agent_stream(messages):
            evt_type = event["event"]
            evt_data = json.dumps(event["data"], ensure_ascii=False)
            yield f"event: {evt_type}\ndata: {evt_data}\n\n"

    return Response(generate(), mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.route("/wiki/<domain>/<path:filepath>")
def serve_wiki_file(domain, filepath):
    """提供 wiki 图片等静态文件访问"""
    wiki_dir = os.path.join(os.path.dirname(__file__), "knowledge", domain, "data", "wiki")
    return send_from_directory(wiki_dir, filepath)


@app.route("/api/share", methods=["POST"])
def share_api():
    """创建分享链接"""
    data = request.get_json()
    title = (data.get("title") or "").strip()
    messages = data.get("messages")
    dom = (data.get("dom") or "").strip()

    if not messages or not dom:
        return {"error": "对话内容为空"}, 400

    content_hash = hashlib.sha256(dom.encode("utf-8")).hexdigest()[:8]
    share_id = content_hash
    share_path = os.path.join(SHARES_DIR, f"{share_id}.json")

    if not os.path.exists(share_path):
        share_data = {
            "id": share_id,
            "title": title or "分享的对话",
            "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "messages": messages,
            "dom": dom,
        }
        with open(share_path, "w", encoding="utf-8") as f:
            json.dump(share_data, f, ensure_ascii=False, indent=2)

    return {"share_id": share_id, "share_url": f"/share/{share_id}"}


@app.route("/share/<share_id>")
def share_page(share_id):
    """查看分享的对话"""
    if not share_id.isalnum() or len(share_id) != 8:
        return "无效的分享链接", 404

    share_path = os.path.join(SHARES_DIR, f"{share_id}.json")
    if not os.path.exists(share_path):
        return "分享不存在或已过期", 404

    with open(share_path, "r", encoding="utf-8") as f:
        share = json.load(f)

    return render_template("share.html", share=share)


if __name__ == "__main__":
    server_cfg = CONFIG.get("server", {})
    app.run(
        host=server_cfg.get("host", "0.0.0.0"),
        port=server_cfg.get("port", 5001),
        threaded=True,
    )
