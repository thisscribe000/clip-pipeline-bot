import os
import sqlite3
import asyncio
from flask import Flask, jsonify, render_template, request, redirect, session, url_for
from dotenv import load_dotenv
from telegram import Bot

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", os.urandom(24))
app.config["ENV"] = "production"

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID"))
PORT = int(os.getenv("PORT", 5000))

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "bot.db")


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


@app.route("/")
def index():
    if "admin_id" in session:
        if session["admin_id"] == str(ADMIN_ID):
            return render_template("index.html")
        else:
            return render_template("forbidden.html")
    return render_template("login.html")


@app.route("/subscribe")
def subscribe():
    return render_template("subscribe.html")


@app.route("/login", methods=["POST"])
def login():
    admin_id = request.form.get("admin_id", "").strip()
    if admin_id == str(ADMIN_ID):
        session["admin_id"] = admin_id
        return redirect(url_for("index"))
    else:
        return render_template("login.html", error="Invalid Admin ID. Access denied.")


@app.route("/logout")
def logout():
    session.pop("admin_id", None)
    return redirect(url_for("index"))


@app.route("/api/stats")
def stats():
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("SELECT COUNT(*) as total FROM subscribers")
    total_subs = cursor.fetchone()["total"]

    cursor.execute("SELECT COUNT(*) FROM subscribers WHERE joined_at >= datetime('now', '-7 days')")
    new_this_week = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) as total FROM clips")
    total_clips = cursor.fetchone()["total"]

    cursor.execute("SELECT COUNT(*) as total FROM clips WHERE broadcast = 1")
    clips_broadcast = cursor.fetchone()["total"]

    cursor.execute("SELECT COALESCE(SUM(success), 0) FROM broadcasts")
    total_sent = cursor.fetchone()[0]

    cursor.execute("SELECT COALESCE(SUM(failed), 0) FROM broadcasts")
    total_failed = cursor.fetchone()[0]

    conn.close()

    return jsonify({
        "subscribers": total_subs,
        "new_this_week": new_this_week,
        "clips": total_clips,
        "clips_broadcast": clips_broadcast,
        "broadcast_sent": total_sent,
        "broadcast_failed": total_failed,
    })


@app.route("/api/subscribers")
def subscribers():
    if "admin_id" not in session or session["admin_id"] != str(ADMIN_ID):
        return jsonify({"error": "Unauthorized"}), 401

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT chat_id, username, joined_at FROM subscribers ORDER BY joined_at DESC")
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return jsonify(rows)


@app.route("/api/subscribers/<int:chat_id>", methods=["DELETE"])
def remove_subscriber(chat_id):
    if "admin_id" not in session or session["admin_id"] != str(ADMIN_ID):
        return jsonify({"error": "Unauthorized"}), 401

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM subscribers WHERE chat_id = ?", (chat_id,))
    conn.commit()
    removed = cursor.rowcount > 0
    conn.close()
    return jsonify({"removed": removed})


@app.route("/api/clips")
def clips():
    if "admin_id" not in session or session["admin_id"] != str(ADMIN_ID):
        return jsonify({"error": "Unauthorized"}), 401

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id, file_id, title, fmt, created_at, broadcast FROM clips ORDER BY id DESC")
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return jsonify(rows)


@app.route("/api/broadcast/<int:clip_id>", methods=["POST"])
def broadcast(clip_id):
    if "admin_id" not in session or session["admin_id"] != str(ADMIN_ID):
        return jsonify({"error": "Unauthorized"}), 401

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT file_id, fmt, title FROM clips WHERE id = ?", (clip_id,))
    clip = cursor.fetchone()

    if not clip:
        conn.close()
        return jsonify({"error": "Clip not found"}), 404

    file_id = clip["file_id"]
    fmt = clip["fmt"]
    title = clip["title"]

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
                    await bot.send_audio(chat_id=chat_id, audio=file_id, title=title)
                else:
                    await bot.send_video(chat_id=chat_id, video=file_id, title=title)
                success += 1
            except Exception:
                failed += 1
        return success, failed

    success, failed = asyncio.run(do_broadcast())

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("UPDATE clips SET broadcast = 1 WHERE id = ?", (clip_id,))
    cursor.execute("INSERT INTO broadcasts (clip_id, success, failed) VALUES (?, ?, ?)", (clip_id, success, failed))
    conn.commit()
    conn.close()

    return jsonify({"success": success, "failed": failed, "total": len(subscribers)})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=PORT, debug=False)