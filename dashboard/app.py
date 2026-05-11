import os
import sqlite3
import asyncio
from flask import Flask, jsonify, render_template
from dotenv import load_dotenv
from telegram import Bot

load_dotenv()

app = Flask(__name__)
app.config["ENV"] = "production"

BOT_TOKEN = os.getenv("BOT_TOKEN")
BOT_ADMIN_ID = int(os.getenv("ADMIN_ID"))
PORT = int(os.getenv("PORT", 5000))

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "bot.db")


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/stats")
def stats():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) as total FROM subscribers")
    total_subs = cursor.fetchone()["total"]
    cursor.execute("SELECT COUNT(*) as total FROM clips")
    total_clips = cursor.fetchone()["total"]
    cursor.execute("SELECT COUNT(*) as total FROM clips WHERE broadcast = 1")
    total_broadcast = cursor.fetchone()["total"]
    conn.close()
    return jsonify({"subscribers": total_subs, "clips": total_clips, "broadcast": total_broadcast})


@app.route("/api/subscribers")
def subscribers():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT chat_id, username, joined_at FROM subscribers ORDER BY joined_at DESC")
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return jsonify(rows)


@app.route("/api/clips")
def clips():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id, file_id, fmt, created_at, broadcast FROM clips ORDER BY id DESC")
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return jsonify(rows)


@app.route("/api/broadcast/<int:clip_id>", methods=["POST"])
def broadcast(clip_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT file_id, fmt FROM clips WHERE id = ?", (clip_id,))
    clip = cursor.fetchone()

    if not clip:
        conn.close()
        return jsonify({"error": "Clip not found"}), 404

    file_id = clip["file_id"]
    fmt = clip["fmt"]

    cursor.execute("SELECT chat_id FROM subscribers")
    subscribers = [r["chat_id"] for r in cursor.fetchall()]
    conn.close()

    if not subscribers:
        return jsonify({"error": "No subscribers"}), 400

    async def do_broadcast():
        bot = Bot(token=BOT_TOKEN)
        success = 0
        failed = 0
        for chat_id in subscribers:
            try:
                if fmt == "mp3":
                    await bot.send_audio(chat_id=chat_id, audio=file_id)
                else:
                    await bot.send_video(chat_id=chat_id, video=file_id)
                success += 1
            except Exception:
                failed += 1
        return success, failed

    success, failed = asyncio.run(do_broadcast())

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("UPDATE clips SET broadcast = 1 WHERE id = ?", (clip_id,))
    conn.commit()
    conn.close()

    return jsonify({"success": success, "failed": failed})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=PORT, debug=False)