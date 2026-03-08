"""Flask 主应用 - 全能 AI 助手"""
import json
from flask import Flask, render_template, request, Response

from agent_engine import run_agent_stream, CONFIG, KNOWLEDGE_DOMAINS, start_watcher

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
