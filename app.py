"""Flask 主应用 - 全能 AI 助手"""
import json
import logging
import os
from logging.handlers import TimedRotatingFileHandler

from flask import Flask, render_template, request, Response

from agent_engine import run_agent_stream, CONFIG, KNOWLEDGE_DOMAINS, start_watcher

# ── 日志初始化 ────────────────────────────────────────────
_log_cfg = CONFIG.get("logging", {})
_log_level = getattr(logging, _log_cfg.get("level", "INFO").upper(), logging.INFO)
_log_file = _log_cfg.get("file", "logs/app.log")
_log_backup_days = _log_cfg.get("backup_days", 30)
_log_format = "%(asctime)s %(levelname)s [%(name)s] %(message)s"

os.makedirs(os.path.dirname(_log_file), exist_ok=True)

_formatter = logging.Formatter(_log_format)

_console_handler = logging.StreamHandler()
_console_handler.setFormatter(_formatter)

_file_handler = TimedRotatingFileHandler(
    _log_file, when="midnight", backupCount=_log_backup_days, encoding="utf-8"
)
_file_handler.setFormatter(_formatter)

logging.basicConfig(level=_log_level, handlers=[_console_handler, _file_handler])

logger = logging.getLogger(__name__)

app = Flask(__name__)
start_watcher()


def _get_examples() -> list[dict]:
    """从所有知识域收集示例问题，按域分组"""
    groups = []
    for domain in KNOWLEDGE_DOMAINS:
        name = domain.get("name", "")
        examples = domain.get("examples", [])
        if examples:
            groups.append({"name": name, "examples": examples})
    return groups


@app.route("/mds/chat")
def chat_page():
    return render_template("chat.html", example_groups=_get_examples())


@app.route("/mds/api/chat", methods=["POST"])
def chat_api():
    data = request.get_json()
    user_message = data.get("message", "").strip()
    history = data.get("history", [])

    if not user_message:
        return {"error": "消息不能为空"}, 400

    logger.info("收到请求: %s [来源: %s]", user_message[:200], request.remote_addr)

    messages = list(history)
    messages.append({"role": "user", "content": user_message})

    def generate():
        for event in run_agent_stream(messages):
            evt_type = event["event"]
            evt_data = json.dumps(event["data"], ensure_ascii=False)
            yield f"event: {evt_type}\ndata: {evt_data}\n\n"

    return Response(generate(), mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


if __name__ == "__main__":
    server_cfg = CONFIG.get("server", {})
    app.run(
        host=server_cfg.get("host", "0.0.0.0"),
        port=server_cfg.get("port", 5001),
        threaded=True,
    )
