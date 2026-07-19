import os
import sqlite3
import secrets
import mimetypes
from datetime import datetime
from functools import wraps

import requests
from flask import (
    Flask, request, session, redirect, url_for,
    render_template, jsonify, Response, stream_with_context, abort
)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
STORAGE_CHAT_ID = os.environ.get("STORAGE_CHAT_ID", "")
APP_PASSWORD = os.environ.get("APP_PASSWORD", "changeme")
SECRET_KEY = os.environ.get("SECRET_KEY", secrets.token_hex(32))
DB_PATH = os.environ.get("DB_PATH", "hangar.db")
MAX_UPLOAD_MB = 50  # Telegram Bot API upload ceiling

TG_API = f"https://api.telegram.org/bot{BOT_TOKEN}"
TG_FILE = f"https://api.telegram.org/file/bot{BOT_TOKEN}"

app = Flask(__name__)
app.secret_key = SECRET_KEY
app.config["MAX_CONTENT_LENGTH"] = (MAX_UPLOAD_MB + 2) * 1024 * 1024


# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------
def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with db() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS files (
                id TEXT PRIMARY KEY,
                original_name TEXT NOT NULL,
                size INTEGER,
                mime TEXT,
                folder TEXT DEFAULT '/',
                tg_file_id TEXT NOT NULL,
                tg_message_id INTEGER,
                share_token TEXT UNIQUE NOT NULL,
                uploaded_at TEXT NOT NULL
            )
            """
        )


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------
def login_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not session.get("authed"):
            return redirect(url_for("login", next=request.path))
        return fn(*args, **kwargs)
    return wrapper


@app.route("/login", methods=["GET", "POST"])
def login():
    error = None
    if request.method == "POST":
        if secrets.compare_digest(request.form.get("password", ""), APP_PASSWORD):
            session["authed"] = True
            return redirect(request.args.get("next") or url_for("admin"))
        error = "Wrong password."
    return render_template("login.html", error=error)


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# ---------------------------------------------------------------------------
# Admin dashboard — private, upload & manage (was the old "/")
# ---------------------------------------------------------------------------
@app.route("/admin")
@login_required
def admin():
    return render_template("index.html", max_mb=MAX_UPLOAD_MB)


# ---------------------------------------------------------------------------
# Public library — anyone can browse and download, no login
# ---------------------------------------------------------------------------
@app.route("/")
def library():
    return render_template("library.html")


def category_for(mime):
    if not mime:
        return "other"
    if mime.startswith("image/"):
        return "image"
    if mime.startswith("video/"):
        return "video"
    if mime.startswith("audio/"):
        return "audio"
    if mime in ("application/pdf",) or "document" in mime or "text" in mime:
        return "doc"
    if "zip" in mime or "compressed" in mime or "tar" in mime:
        return "archive"
    return "other"


@app.route("/api/files")
@login_required
def api_files():
    folder = request.args.get("folder")
    q = request.args.get("q", "").strip()
    with db() as conn:
        if q:
            rows = conn.execute(
                "SELECT * FROM files WHERE original_name LIKE ? ORDER BY uploaded_at DESC",
                (f"%{q}%",),
            ).fetchall()
        elif folder:
            rows = conn.execute(
                "SELECT * FROM files WHERE folder=? ORDER BY uploaded_at DESC", (folder,)
            ).fetchall()
        else:
            rows = conn.execute("SELECT * FROM files ORDER BY uploaded_at DESC").fetchall()
        folders = conn.execute(
            "SELECT DISTINCT folder FROM files ORDER BY folder"
        ).fetchall()

    files = []
    total_size = 0
    for r in rows:
        total_size += r["size"] or 0
        files.append({
            "id": r["id"],
            "name": r["original_name"],
            "size": r["size"],
            "mime": r["mime"],
            "category": category_for(r["mime"]),
            "folder": r["folder"],
            "share_token": r["share_token"],
            "uploaded_at": r["uploaded_at"],
        })

    return jsonify({
        "files": files,
        "folders": [f["folder"] for f in folders],
        "count": len(files),
        "total_size": total_size,
    })


@app.route("/api/library/files")
def api_library_files():
    """Public, read-only catalog — no auth, no internal Telegram fields exposed."""
    folder = request.args.get("folder")
    q = request.args.get("q", "").strip()
    with db() as conn:
        if q:
            rows = conn.execute(
                "SELECT * FROM files WHERE original_name LIKE ? ORDER BY original_name ASC",
                (f"%{q}%",),
            ).fetchall()
        elif folder:
            rows = conn.execute(
                "SELECT * FROM files WHERE folder=? ORDER BY original_name ASC", (folder,)
            ).fetchall()
        else:
            rows = conn.execute("SELECT * FROM files ORDER BY original_name ASC").fetchall()

        shelf_rows = conn.execute(
            "SELECT folder, COUNT(*) c FROM files GROUP BY folder ORDER BY folder"
        ).fetchall()

    files = [{
        "id": r["id"],
        "name": r["original_name"],
        "size": r["size"],
        "category": category_for(r["mime"]),
        "folder": r["folder"],
        "uploaded_at": r["uploaded_at"],
    } for r in rows]

    shelves = [{"name": s["folder"], "count": s["c"]} for s in shelf_rows]

    return jsonify({"files": files, "shelves": shelves, "count": len(files)})


@app.route("/library/download/<file_id>")
def library_download(file_id):
    with db() as conn:
        row = conn.execute("SELECT * FROM files WHERE id=?", (file_id,)).fetchone()
    if not row:
        abort(404)
    return _stream_from_telegram(row["tg_file_id"], row["original_name"])


@app.route("/api/upload", methods=["POST"])
@login_required
def api_upload():
    if not BOT_TOKEN or not STORAGE_CHAT_ID:
        return jsonify({"error": "Bot not configured. Set BOT_TOKEN and STORAGE_CHAT_ID."}), 500

    f = request.files.get("file")
    if not f or not f.filename:
        return jsonify({"error": "No file provided."}), 400

    folder = request.form.get("folder", "/").strip() or "/"
    mime = f.mimetype or mimetypes.guess_type(f.filename)[0] or "application/octet-stream"

    # Forward straight to Telegram; it becomes our free storage backend.
    resp = requests.post(
        f"{TG_API}/sendDocument",
        data={"chat_id": STORAGE_CHAT_ID, "caption": f.filename},
        files={"document": (f.filename, f.stream, mime)},
        timeout=120,
    )
    payload = resp.json()
    if not payload.get("ok"):
        return jsonify({"error": payload.get("description", "Telegram upload failed.")}), 502

    doc = payload["result"]["document"]
    file_id = doc["file_id"]
    size = doc.get("file_size")
    message_id = payload["result"]["message_id"]
    file_uuid = secrets.token_hex(8)
    share_token = secrets.token_urlsafe(16)

    with db() as conn:
        conn.execute(
            "INSERT INTO files (id, original_name, size, mime, folder, tg_file_id, "
            "tg_message_id, share_token, uploaded_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (file_uuid, f.filename, size, mime, folder, file_id, message_id,
             share_token, datetime.utcnow().isoformat()),
        )

    return jsonify({"ok": True, "id": file_uuid, "share_token": share_token})


def _stream_from_telegram(tg_file_id, download_name):
    lookup = requests.get(f"{TG_API}/getFile", params={"file_id": tg_file_id}, timeout=30)
    payload = lookup.json()
    if not payload.get("ok"):
        abort(404)
    file_path = payload["result"]["file_path"]

    upstream = requests.get(f"{TG_FILE}/{file_path}", stream=True, timeout=120)
    if upstream.status_code != 200:
        abort(502)

    def generate():
        for chunk in upstream.iter_content(chunk_size=65536):
            if chunk:
                yield chunk

    headers = {"Content-Disposition": f'attachment; filename="{download_name}"'}
    return Response(stream_with_context(generate()), headers=headers,
                     content_type=upstream.headers.get("Content-Type", "application/octet-stream"))


@app.route("/api/download/<file_id>")
@login_required
def api_download(file_id):
    with db() as conn:
        row = conn.execute("SELECT * FROM files WHERE id=?", (file_id,)).fetchone()
    if not row:
        abort(404)
    return _stream_from_telegram(row["tg_file_id"], row["original_name"])


@app.route("/api/files/<file_id>", methods=["DELETE"])
@login_required
def api_delete(file_id):
    with db() as conn:
        row = conn.execute("SELECT * FROM files WHERE id=?", (file_id,)).fetchone()
        if not row:
            return jsonify({"error": "Not found."}), 404
        conn.execute("DELETE FROM files WHERE id=?", (file_id,))

    if row["tg_message_id"]:
        try:
            requests.post(
                f"{TG_API}/deleteMessage",
                data={"chat_id": STORAGE_CHAT_ID, "message_id": row["tg_message_id"]},
                timeout=15,
            )
        except requests.RequestException:
            pass  # index is already cleared either way

    return jsonify({"ok": True})


@app.route("/api/files/<file_id>/rename", methods=["POST"])
@login_required
def api_rename(file_id):
    new_name = (request.json or {}).get("name", "").strip()
    if not new_name:
        return jsonify({"error": "Name required."}), 400
    with db() as conn:
        cur = conn.execute("UPDATE files SET original_name=? WHERE id=?", (new_name, file_id))
    if not cur.rowcount:
        return jsonify({"error": "Not found."}), 404
    return jsonify({"ok": True})


# ---------------------------------------------------------------------------
# Public share links — no login required, this is the whole point of them
# ---------------------------------------------------------------------------
@app.route("/share/<token>")
def share_landing(token):
    with db() as conn:
        row = conn.execute("SELECT * FROM files WHERE share_token=?", (token,)).fetchone()
    if not row:
        return render_template("share.html", found=False), 404
    return render_template(
        "share.html",
        found=True,
        name=row["original_name"],
        size=row["size"],
        category=category_for(row["mime"]),
        token=token,
    )


@app.route("/share/<token>/download")
def share_download(token):
    with db() as conn:
        row = conn.execute("SELECT * FROM files WHERE share_token=?", (token,)).fetchone()
    if not row:
        abort(404)
    return _stream_from_telegram(row["tg_file_id"], row["original_name"])


if __name__ == "__main__":
    init_db()
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
else:
    init_db()
