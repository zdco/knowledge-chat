"""Flask 主应用 - 全能 AI 助手"""
import base64
import hashlib
import json
import logging
import os
import uuid
from datetime import datetime
from logging.handlers import TimedRotatingFileHandler

from flask import Flask, render_template, request, Response, send_from_directory, jsonify

from agent_engine import run_agent_stream, CONFIG, KNOWLEDGE_DOMAINS, start_watcher, request_id_var, \
    BASE_URL, MODEL, API_FORMAT, ORACLE_CLIENT_PATH, init_text_cache, APP_MODE, _session_manager

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

_req_id_filter = _RequestIdFilter()

_console_handler = logging.StreamHandler()
_console_handler.setFormatter(_formatter)
_console_handler.addFilter(_req_id_filter)

_file_handler = TimedRotatingFileHandler(
    _log_file, when="midnight", backupCount=_log_backup_days, encoding="utf-8"
)
_file_handler.setFormatter(_formatter)
_file_handler.addFilter(_req_id_filter)

logging.basicConfig(level=_log_level, handlers=[_console_handler, _file_handler])

logger = logging.getLogger(__name__)

app = Flask(__name__)
init_text_cache()
start_watcher()

SITE_TITLE = CONFIG.get("server", {}).get("title", "全能 AI 助手")

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


@app.route("/kchat/chat")
def chat_page():
    return render_template("chat.html", example_groups=_get_examples(), title=SITE_TITLE,
                           app_mode=APP_MODE)


@app.route("/kchat/api/chat", methods=["POST"])
def chat_api():
    data = request.get_json()
    user_message = data.get("message", "").strip()
    history = data.get("history", [])
    session_id = data.get("session_id")
    images = data.get("images", [])  # [{data: base64, media_type: "image/png"}]

    if not user_message and not images:
        return {"error": "消息不能为空"}, 400

    # log-analyzer 模式：确保 session 存在
    if APP_MODE == "log-analyzer" and _session_manager:
        if not session_id:
            session_id = _session_manager.create_session()
        else:
            _session_manager.create_session(session_id)

    req_id = uuid.uuid4().hex[:8]
    request_id_var.set(req_id)
    client_ip = request.headers.get("X-Forwarded-For", request.headers.get("X-Real-IP", request.remote_addr))
    logger.info("收到请求: %s [来源: %s] [session: %s]", user_message[:200], client_ip, session_id or "-")

    messages = list(history)

    # 构建用户消息（支持多模态图片）
    if images:
        content_parts = []
        for img in images:
            content_parts.append({
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": img.get("media_type", "image/png"),
                    "data": img["data"],
                }
            })
        if user_message:
            content_parts.append({"type": "text", "text": user_message})
        else:
            content_parts.append({"type": "text", "text": "请分析这张图片中的内容"})
        messages.append({"role": "user", "content": content_parts})
    else:
        messages.append({"role": "user", "content": user_message})

    def generate():
        # 先发送 session_id 给前端
        if session_id:
            yield f"event: session\ndata: {json.dumps({'session_id': session_id}, ensure_ascii=False)}\n\n"
        for event in run_agent_stream(messages, session_id=session_id):
            evt_type = event["event"]
            evt_data = json.dumps(event["data"], ensure_ascii=False)
            yield f"event: {evt_type}\ndata: {evt_data}\n\n"

    return Response(generate(), mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


# ── 文件上传（log-analyzer 模式）────────────────────────────

if APP_MODE == "log-analyzer":
    from log_analyzer import process_upload, is_allowed_file, is_image_file, extract_log_summary

    _max_upload_size = CONFIG.get("analyzer", {}).get("max_upload_size", 104857600)

    @app.route("/kchat/api/upload", methods=["POST"])
    def upload_api():
        """上传文件（日志、压缩包、截图）"""
        session_id = request.form.get("session_id")
        if not session_id or not _session_manager:
            return jsonify({"error": "缺少 session_id"}), 400

        _session_manager.create_session(session_id)
        uploads_dir = _session_manager.get_uploads_path(session_id)

        files = request.files.getlist("files")
        if not files:
            return jsonify({"error": "未选择文件"}), 400

        results = []
        for f in files:
            if not f.filename:
                continue
            if not is_allowed_file(f.filename):
                results.append({"name": f.filename, "error": "不支持的文件格式"})
                continue

            # 检查文件大小
            f.seek(0, 2)
            size = f.tell()
            f.seek(0)
            if size > _max_upload_size:
                results.append({"name": f.filename, "error": f"文件过大（{size // 1048576}MB），最大 {_max_upload_size // 1048576}MB"})
                continue

            # 保存文件
            safe_name = f.filename.replace("/", "_").replace("\\", "_")
            save_path = os.path.join(uploads_dir, safe_name)
            f.save(save_path)

            if is_image_file(f.filename):
                # 图片：返回 base64 供前端作为多模态消息发送
                with open(save_path, "rb") as img_f:
                    b64 = base64.b64encode(img_f.read()).decode("ascii")
                content_type = f.content_type or "image/png"
                results.append({
                    "name": f.filename,
                    "type": "image",
                    "path": safe_name,
                    "media_type": content_type,
                    "data": b64,
                })
            else:
                # 日志/压缩包：解压并预处理
                extracted = process_upload(save_path, uploads_dir)
                file_infos = []
                for fp in extracted:
                    rel = os.path.relpath(fp, uploads_dir)
                    summary = ""
                    if fp.endswith(('.log', '.txt')):
                        summary = extract_log_summary(fp, max_errors=10)
                    file_infos.append({"path": rel, "summary": summary})
                results.append({
                    "name": f.filename,
                    "type": "log",
                    "files": file_infos,
                })

        return jsonify({"session_id": session_id, "uploads": results})


@app.route("/kchat/wiki/<domain>/<path:filepath>")
def serve_wiki_file(domain, filepath):
    """提供 wiki 图片等静态文件访问"""
    wiki_dir = os.path.join(os.path.dirname(__file__), "knowledge", domain, "data", "wiki")
    return send_from_directory(wiki_dir, filepath)


@app.route("/kchat/api/share", methods=["POST"])
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

    return {"share_id": share_id, "share_url": f"/kchat/share/{share_id}"}


@app.route("/kchat/share/<share_id>")
def share_page(share_id):
    """查看分享的对话"""
    if not share_id.isalnum() or len(share_id) != 8:
        return "无效的分享链接", 404

    share_path = os.path.join(SHARES_DIR, f"{share_id}.json")
    if not os.path.exists(share_path):
        return "分享不存在或已过期", 404

    with open(share_path, "r", encoding="utf-8") as f:
        share = json.load(f)

    return render_template("share.html", share=share, title=SITE_TITLE)


if __name__ == "__main__":
    import socket
    server_cfg = CONFIG.get("server", {})
    host = server_cfg.get("host", "0.0.0.0")
    port = server_cfg.get("port", 5001)
    print(f"模式: {APP_MODE}")
    print(f"模型: {MODEL}")
    print(f"地址: {BASE_URL}")
    print(f"格式: {API_FORMAT}")
    print(f"Oracle: {ORACLE_CLIENT_PATH or '未配置'}")
    print(f"访问: http://localhost:{port}/kchat/chat")
    if host == "0.0.0.0":
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            local_ip = s.getsockname()[0]
            s.close()
            print(f"局域网: http://{local_ip}:{port}/kchat/chat")
        except Exception:
            pass
    app.run(host=host, port=port, threaded=True)
