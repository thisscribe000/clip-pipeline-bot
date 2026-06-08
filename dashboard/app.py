import os
import re
import sqlite3
import asyncio
import urllib.request
import urllib.parse
import html
import json as pyjson
import xml.etree.ElementTree as ET
from functools import wraps
from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
from telegram import Bot
from dotenv import load_dotenv

load_dotenv()

from models import (
    init_prophecy_tables, get_user_by_email, get_user_by_id, create_user,
    update_user_prefs, get_active_prophecy_clips, get_all_prophecy_clips,
    get_prophecy_clip, create_prophecy_clip, update_prophecy_clip,
    delete_prophecy_clip, get_delivery_log, log_delivery, get_next_undelivered_clip,
    get_opt_in_telegram_users, get_distinct_values,
    create_testimony, get_testimonies, get_testimony,
    approve_testimony, reject_testimony, delete_testimony,
    create_user_prophecy, get_user_prophecies, get_user_prophecy,
    update_user_prophecy, delete_user_prophecy, toggle_user_prophecy_favorite,
    get_user_testimonies, update_user_testimony, user_delete_testimony, reinstate_testimony
)

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", 0))
DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "bot.db")

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", os.urandom(24).hex())
app.config['TEMPLATES_AUTO_RELOAD'] = True

init_prophecy_tables()

ADMIN_EMAILS = {"admin@sharestill.com"}


def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user_id" not in session and "admin_id" not in session:
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated


def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "admin_id" in session and session["admin_id"] == str(ADMIN_ID):
            return f(*args, **kwargs)
        if "user_id" not in session:
            return redirect(url_for("login"))
        user = get_user_by_id(session["user_id"])
        if not user or user["email"] not in ADMIN_EMAILS:
            flash("Admin access required", "error")
            return redirect(url_for("dashboard"))
        return f(*args, **kwargs)
    return decorated


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


@app.route("/")
def landing():
    return render_template("landing.html")


@app.route("/subscribe")
def subscribe():
    return render_template("subscribe.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    error = None
    if request.method == "POST":
        # Admin ID login
        admin_id = request.form.get("admin_id", "").strip()
        if admin_id and admin_id == str(ADMIN_ID):
            session["admin_id"] = admin_id
            session["email"] = "admin@sharestill.com"
            return redirect(url_for("admin_panel"))

        # Email/password login
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "")
        action = request.form.get("action", "login")

        if action == "register":
            existing = get_user_by_email(email)
            if existing:
                flash("Email already registered", "error")
                return redirect(url_for("login"))
            if len(password) < 6:
                flash("Password must be at least 6 characters", "error")
                return redirect(url_for("login"))
            country_code = request.form.get("country_code", "").strip()
            phone_raw = request.form.get("phone", "").strip()
            phone = country_code + phone_raw if phone_raw else ""
            telegram = request.form.get("telegram", "").strip()
            tid = int(telegram) if telegram.isdigit() else None
            pw_hash = generate_password_hash(password)
            user_id = create_user(email, pw_hash, phone=phone, telegram_id=tid)
            session["user_id"] = user_id
            session["email"] = email
            return redirect(url_for("dashboard"))

        user = get_user_by_email(email)
        if not user or not check_password_hash(user["password_hash"], password):
            error = "Invalid email or password"
            return render_template("login.html", error=error)

        session["user_id"] = user["id"]
        session["email"] = user["email"]
        return redirect(url_for("dashboard"))

    return render_template("login.html", error=error)


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/dashboard")
@login_required
def dashboard():
    user = get_user_by_id(session.get("user_id"))
    if not user:
        return redirect(url_for("login"))
    clips = get_active_prophecy_clips()
    logs = get_delivery_log(user_id=user["id"], limit=10)
    testimonies = get_user_testimonies(user["id"], include_deleted=True)
    return render_template("dashboard.html", user=user, clips=clips, logs=logs, testimonies=testimonies)


@app.route("/bank")
@login_required
def prophecy_bank():
    user = get_user_by_id(session.get("user_id"))
    if not user:
        return redirect(url_for("login"))
    prophecies = get_user_prophecies(user["id"])
    return render_template("bank.html", user=user, prophecies=prophecies)


@app.route("/settings", methods=["POST"])
@login_required
def save_settings():
    if "user_id" not in session:
        return redirect(url_for("login"))
    delivery_time = request.form.get("delivery_time", "08:00")
    delivery_frequency = request.form.get("delivery_frequency", "daily")
    timezone = request.form.get("timezone", "Africa/Lagos")
    telegram_id = request.form.get("telegram_id", "").strip()

    user = get_user_by_id(session["user_id"])
    tid = int(telegram_id) if telegram_id.isdigit() else user["telegram_id"]
    update_user_prefs(session["user_id"], delivery_time, delivery_frequency, timezone)
    if tid:
        conn = get_db()
        conn.execute("UPDATE users SET telegram_id = ? WHERE id = ?", (tid, session["user_id"]))
        conn.commit()
        conn.close()

    flash("Settings saved", "success")
    return redirect(url_for("dashboard"))


# ── API Routes ──

@app.route("/api/stats")
def api_stats():
    conn = get_db()
    subs = conn.execute("SELECT COUNT(*) FROM subscribers").fetchone()[0]
    clips = conn.execute("SELECT COUNT(*) FROM clips").fetchone()[0]
    broadcast = conn.execute("SELECT COUNT(*) FROM clips WHERE broadcast=1").fetchone()[0]
    new_week = conn.execute("SELECT COUNT(*) FROM subscribers WHERE joined_at >= datetime('now', '-7 days')").fetchone()[0]
    total_sent = conn.execute("SELECT COALESCE(SUM(success), 0) FROM broadcasts").fetchone()[0]
    total_failed = conn.execute("SELECT COALESCE(SUM(failed), 0) FROM broadcasts").fetchone()[0]
    conn.close()
    return jsonify({
        "subscribers": subs, "clips": clips, "broadcast": broadcast,
        "new_this_week": new_week, "broadcast_sent": total_sent, "broadcast_failed": total_failed
    })


INSTAGRAM_REELS = [
    "https://www.instagram.com/reel/DX5-mnVikh0/",
    "https://www.instagram.com/reel/DX8_QGxoah2/",
    "https://www.instagram.com/reel/DYAWtCbT-a8/",
    "https://www.instagram.com/reel/DYMxO4BMYAN/",
    "https://www.instagram.com/reel/DYemQ85ov6K/",
]


def _decode_instagram_url(value):
    if not value:
        return ""
    try:
        value = pyjson.loads(f'"{value}"')
    except Exception:
        pass
    return html.unescape(value).replace("\\/", "/")


def _extract_instagram_thumbnail(html_text):
    clean_patterns = [
        r'"display_url"\s*:\s*"([^"]+)"',
        r'"thumbnail_src"\s*:\s*"([^"]+)"',
        r'"thumbnail_url"\s*:\s*"([^"]+)"',
        r'"thumbnailUrl"\s*:\s*\[\s*"([^"]+)"',
        r'"thumbnailUrl"\s*:\s*"([^"]+)"',
    ]
    for pattern in clean_patterns:
        match = re.search(pattern, html_text, re.I)
        if match:
            return _decode_instagram_url(match.group(1)), False

    match = re.search(
        r'<meta[^>]+property="og:image"[^>]+content="([^"]+)"',
        html_text,
        re.I,
    )
    if match:
        return _decode_instagram_url(match.group(1)), True
    return "", False


@app.route("/api/reels")
def api_reels():
    results = []
    for url in INSTAGRAM_REELS:
        try:
            req = urllib.request.Request(
                url, headers={"User-Agent": "Mozilla/5.0 (Linux; Android 10; Pixel 4)"}
            )
            with urllib.request.urlopen(req, timeout=15) as resp:
                html_text = resp.read().decode("utf-8", errors="replace")
                thumb, mask_thumb = _extract_instagram_thumbnail(html_text)
                title = ""
                m2 = re.search(
                    r'<meta[^>]+property="og:title"[^>]+content="([^"]+)"', html_text, re.I
                )
                if m2:
                    title = html.unescape(m2.group(1))
                results.append({
                    "thumbnail_url": thumb,
                    "thumbnail_masked": mask_thumb,
                    "url": url,
                    "title": title,
                    "author_name": "pastorenochmoments",
                })
        except Exception:
            results.append({
                "thumbnail_url": "",
                "thumbnail_masked": False,
                "url": url,
                "title": "",
                "author_name": "pastorenochmoments",
            })
    return jsonify(results)


RSS_FEED_URL = "https://anchor.fm/s/ee10d30/podcast/rss"


@app.route("/api/rss")
def api_rss():
    try:
        req = urllib.request.Request(RSS_FEED_URL, headers={"User-Agent": "Mozilla/5.0"})
        resp = urllib.request.urlopen(req, timeout=10)
        tree = ET.parse(resp)
        root = tree.getroot()
        channel = root.find("channel")
        items = []
        for item in channel.findall("item")[:8]:
            ns = {"itunes": "http://www.itunes.com/dtds/podcast-1.0.dtd"}
            title_el = item.find("title")
            link_el = item.find("link")
            enc_el = item.find("enclosure")
            dur_el = item.find("itunes:duration", ns)
            pub_el = item.find("pubDate")
            img_el = item.find("itunes:image", ns)
            items.append({
                "title": title_el.text.strip() if title_el is not None and title_el.text else "Untitled",
                "link": link_el.text.strip() if link_el is not None and link_el.text else "",
                "audio_url": enc_el.get("url") if enc_el is not None else "",
                "duration": dur_el.text.strip() if dur_el is not None and dur_el.text else "",
                "pub_date": pub_el.text.strip() if pub_el is not None and pub_el.text else "",
                "image": img_el.get("href") if img_el is not None else "",
            })
        return jsonify(items)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/prophecies/recent")
def api_prophecies_recent():
    conn = get_db()
    clips = conn.execute(
        "SELECT id, title, content_text, audio_file_id, audio_url, month, program, series, speaker, tags, is_featured, created_at FROM prophecy_clips WHERE is_active = 1 ORDER BY is_featured DESC, created_at DESC LIMIT 10"
    ).fetchall()
    conn.close()
    return jsonify([dict(c) for c in clips])


@app.route("/api/subscribers")
def api_subscribers():
    if "admin_id" not in session and "user_id" not in session:
        return jsonify({"error": "Unauthorized"}), 401
    conn = get_db()
    rows = [dict(r) for r in conn.execute("SELECT chat_id, username, joined_at FROM subscribers ORDER BY joined_at DESC")]
    conn.close()
    return jsonify(rows)


@app.route("/api/subscribers/<int:chat_id>", methods=["DELETE"])
def remove_subscriber(chat_id):
    if "admin_id" not in session and session.get("email") not in ADMIN_EMAILS:
        return jsonify({"error": "Unauthorized"}), 401
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM subscribers WHERE chat_id = ?", (chat_id,))
    conn.commit()
    removed = cursor.rowcount > 0
    conn.close()
    return jsonify({"removed": removed})


@app.route("/api/clips")
def api_clips():
    if "admin_id" not in session and session.get("email") not in ADMIN_EMAILS:
        return jsonify({"error": "Unauthorized"}), 401
    conn = get_db()
    rows = [dict(r) for r in conn.execute("SELECT id, file_id, fmt, title, created_at, broadcast FROM clips ORDER BY id DESC")]
    conn.close()
    return jsonify(rows)


@app.route("/api/broadcast/<int:clip_id>", methods=["POST"])
def api_broadcast(clip_id):
    if "admin_id" not in session and session.get("email") not in ADMIN_EMAILS:
        return jsonify({"error": "Unauthorized"}), 401
    conn = get_db()
    clip = conn.execute("SELECT file_id, fmt, title FROM clips WHERE id=?", (clip_id,)).fetchone()
    if not clip:
        conn.close()
        return jsonify({"error": "Clip not found"}), 404
    data = request.get_json(silent=True) or {}
    selected = data.get("chat_ids")
    all_subs = [dict(r) for r in conn.execute("SELECT chat_id, username FROM subscribers")]
    if selected is not None:
        subs = [s["chat_id"] for s in all_subs if s["chat_id"] in selected]
    else:
        subs = [s["chat_id"] for s in all_subs]
    conn.close()
    if not subs:
        return jsonify({"error": "No subscribers"}), 400

    async def do():
        bot = Bot(token=BOT_TOKEN)
        s, f = 0, 0
        for cid in subs:
            try:
                if clip["fmt"] == "mp3":
                    await bot.send_audio(chat_id=cid, audio=clip["file_id"], caption=f"🎬 {clip['title'] or 'Clip'}")
                else:
                    await bot.send_video(chat_id=cid, video=clip["file_id"], caption=f"🎬 {clip['title'] or 'Clip'}")
                s += 1
            except Exception:
                f += 1
        return s, f

    success, failed = asyncio.run(do())
    conn = get_db()
    conn.execute("UPDATE clips SET broadcast=1 WHERE id=?", (clip_id,))
    conn.execute("INSERT INTO broadcasts (clip_id, success, failed) VALUES (?, ?, ?)", (clip_id, success, failed))
    conn.commit()
    conn.close()
    return jsonify({"success": success, "failed": failed, "total": len(subs)})


@app.route("/api/send-prophecy/<int:clip_id>", methods=["POST"])
def api_send_prophecy(clip_id):
    if "admin_id" not in session and session.get("email") not in ADMIN_EMAILS:
        return jsonify({"error": "Unauthorized"}), 401
    clip = get_prophecy_clip(clip_id)
    if not clip:
        return jsonify({"error": "Clip not found"}), 404
    conn = get_db()
    data = request.get_json(silent=True) or {}
    selected = data.get("chat_ids")
    all_subs = [dict(r) for r in conn.execute("SELECT chat_id, username FROM subscribers")]
    if selected is not None:
        subs = [s["chat_id"] for s in all_subs if s["chat_id"] in selected]
    else:
        subs = [s["chat_id"] for s in all_subs]
    conn.close()
    if not subs:
        return jsonify({"error": "No subscribers"}), 400

    async def do():
        bot = Bot(token=BOT_TOKEN)
        s, f = 0, 0
        for cid in subs:
            try:
                if clip["audio_file_id"]:
                    await bot.send_audio(chat_id=cid, audio=clip["audio_file_id"], caption=f"🎬 {clip['title']}")
                elif clip["video_file_id"]:
                    await bot.send_video(chat_id=cid, video=clip["video_file_id"], caption=f"🎬 {clip['title']}")
                elif clip["content_text"]:
                    text = f"🎬 *{clip['title']}*\n\n{clip['content_text']}"
                    await bot.send_message(chat_id=cid, text=text, parse_mode="Markdown")
                else:
                    await bot.send_message(chat_id=cid, text=f"🎬 *{clip['title']}*", parse_mode="Markdown")
                s += 1
            except Exception:
                f += 1
        return s, f

    success, failed = asyncio.run(do())
    return jsonify({"success": success, "failed": failed, "total": len(subs)})


# ── Testimony Endpoints ──

@app.route("/api/testimonies", methods=["GET", "POST"])
def api_testimonies():
    if request.method == "GET":
        rows = get_testimonies(status="approved", is_public=1, limit=100)
        return jsonify([dict(r) for r in rows])

    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "Invalid JSON"}), 400
    tid = create_testimony(
        user_id=data.get("user_id"),
        user_name=data.get("user_name", ""),
        title=data.get("title", ""),
        content=data.get("content", ""),
        media_file_id=data.get("media_file_id", ""),
        media_type=data.get("media_type", ""),
        source=data.get("source", "web"),
    )
    return jsonify({"id": tid}), 201


@app.route("/api/admin/testimonies")
def api_admin_testimonies():
    if "admin_id" not in session:
        return jsonify({"error": "Unauthorized"}), 401
    status = request.args.get("status")
    rows = get_testimonies(status=status)
    return jsonify([dict(r) for r in rows])


@app.route("/api/admin/testimonies/<int:tid>/approve", methods=["POST"])
def api_admin_approve_testimony(tid):
    if "admin_id" not in session:
        return jsonify({"error": "Unauthorized"}), 401
    testimony = get_testimony(tid)
    if not testimony:
        return jsonify({"error": "Not found"}), 404
    approve_testimony(tid, approved_by=session.get("admin_id"))
    return jsonify({"success": True})


@app.route("/api/admin/testimonies/<int:tid>/reject", methods=["POST"])
def api_admin_reject_testimony(tid):
    if "admin_id" not in session:
        return jsonify({"error": "Unauthorized"}), 401
    testimony = get_testimony(tid)
    if not testimony:
        return jsonify({"error": "Not found"}), 404
    reject_testimony(tid)
    return jsonify({"success": True})


@app.route("/api/admin/testimonies/<int:tid>/delete", methods=["POST"])
def api_admin_delete_testimony(tid):
    if "admin_id" not in session:
        return jsonify({"error": "Unauthorized"}), 401
    testimony = get_testimony(tid)
    if not testimony:
        return jsonify({"error": "Not found"}), 404
    delete_testimony(tid)
    return jsonify({"success": True})


# ── User Prophecy Bank API ──

@app.route("/api/user/prophecies", methods=["GET", "POST"])
@login_required
def api_user_prophecies():
    uid = session.get("user_id")
    if not uid:
        return jsonify({"error": "Unauthorized"}), 401
    if request.method == "GET":
        rows = get_user_prophecies(uid)
        return jsonify([dict(r) for r in rows])
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "Invalid JSON"}), 400
    title = data.get("title", "")
    content = data.get("content", "")
    tags = data.get("tags", "")
    pid = create_user_prophecy(uid, title=title, content_text=content, file_type="text", tags=tags)
    return jsonify({"id": pid}), 201


@app.route("/api/user/prophecies/<int:pid>", methods=["GET", "PUT", "DELETE"])
@login_required
def api_user_prophecy(pid):
    uid = session.get("user_id")
    if not uid:
        return jsonify({"error": "Unauthorized"}), 401
    prophecy = get_user_prophecy(pid)
    if not prophecy or prophecy["user_id"] != uid:
        return jsonify({"error": "Not found"}), 404
    if request.method == "GET":
        return jsonify(dict(prophecy))
    if request.method == "DELETE":
        delete_user_prophecy(pid)
        return jsonify({"success": True})
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "Invalid JSON"}), 400
    update_user_prophecy(pid, uid,
        title=data.get("title"),
        content_text=data.get("content"),
        tags=data.get("tags")
    )
    return jsonify({"success": True})


@app.route("/api/user/prophecies/<int:pid>/favorite", methods=["POST"])
@login_required
def api_toggle_favorite(pid):
    uid = session.get("user_id")
    if not uid:
        return jsonify({"error": "Unauthorized"}), 401
    prophecy = get_user_prophecy(pid)
    if not prophecy or prophecy["user_id"] != uid:
        return jsonify({"error": "Not found"}), 404
    toggle_user_prophecy_favorite(pid)
    return jsonify({"success": True})


# ── User Testimony CRUD ──

@app.route("/api/user/testimonies", methods=["GET", "POST"])
@login_required
def api_user_testimonies():
    uid = session.get("user_id")
    if not uid:
        return jsonify({"error": "Unauthorized"}), 401
    if request.method == "GET":
        rows = get_user_testimonies(uid, include_deleted=True)
        return jsonify([dict(r) for r in rows])
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "Invalid JSON"}), 400
    user = get_user_by_id(uid)
    tid = create_testimony(
        user_id=uid,
        user_name=data.get("user_name", user["email"].split("@")[0] if user else ""),
        title=data.get("title", ""),
        content=data.get("content", ""),
        category=data.get("category", ""),
        source="web",
    )
    return jsonify({"id": tid}), 201


@app.route("/api/user/testimonies/<int:tid>", methods=["GET", "PUT", "DELETE"])
@login_required
def api_user_testimony(tid):
    uid = session.get("user_id")
    if not uid:
        return jsonify({"error": "Unauthorized"}), 401
    t = get_testimony(tid)
    if not t or t["user_id"] != uid:
        return jsonify({"error": "Not found"}), 404
    if request.method == "GET":
        return jsonify(dict(t))
    if request.method == "DELETE":
        user_delete_testimony(tid, uid)
        return jsonify({"success": True, "action": "deleted"})
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "Invalid JSON"}), 400
    update_user_testimony(tid, uid, data.get("title", ""), data.get("content", ""), data.get("category", ""))
    return jsonify({"success": True, "action": "updated"})


@app.route("/api/admin/testimonies/<int:tid>/reinstate", methods=["POST"])
@login_required
@admin_required
def api_admin_reinstate_testimony(tid):
    ok = reinstate_testimony(tid)
    if not ok:
        return jsonify({"error": "Not found"}), 404
    return jsonify({"success": True})


# ── Admin Routes ──

@app.route("/admin")
@login_required
@admin_required
def admin_panel():
    clips = get_all_prophecy_clips()
    logs = get_delivery_log(limit=50)
    conn = get_db()
    subs = [dict(r) for r in conn.execute("SELECT * FROM subscribers ORDER BY joined_at DESC LIMIT 30")]
    telegram_clips = [dict(r) for r in conn.execute("SELECT id, file_id, fmt, title, created_at, broadcast FROM clips ORDER BY id DESC")]
    stats = {
        "subscribers": conn.execute("SELECT COUNT(*) FROM subscribers").fetchone()[0],
        "clips": conn.execute("SELECT COUNT(*) FROM clips").fetchone()[0],
        "broadcast": conn.execute("SELECT COUNT(*) FROM clips WHERE broadcast=1").fetchone()[0],
    }
    conn.close()
    users = get_opt_in_telegram_users()
    programs = get_distinct_values("program")
    return render_template("admin.html", clips=clips, logs=logs, subscribers=subs, users=users, telegram_clips=telegram_clips, stats=stats, programs=programs)


@app.route("/admin/clip/create", methods=["POST"])
@login_required
@admin_required
def admin_create_clip():
    title = request.form.get("title", "").strip()
    content_text = request.form.get("content_text", "").strip()
    if not title:
        flash("Title is required", "error")
        return redirect(url_for("admin_panel"))
    create_prophecy_clip(
        title=title, content_text=content_text,
        month=request.form.get("month", "").strip(),
        program=request.form.get("program", "").strip(),
        series=request.form.get("series", "").strip(),
        speaker=request.form.get("speaker", "").strip(),
        service_date=request.form.get("service_date", "").strip(),
        tags=request.form.get("tags", "").strip(),
        source="web",
        is_featured=1 if request.form.get("is_featured") else 0,
    )
    flash("Clip created", "success")
    return redirect(url_for("admin_panel"))


@app.route("/admin/clip/toggle", methods=["POST"])
@login_required
@admin_required
def admin_toggle_clip():
    clip_id = request.form.get("clip_id")
    is_active = request.form.get("is_active", "0")
    clip = get_prophecy_clip(clip_id)
    if clip:
        update_prophecy_clip(
            clip_id, clip["title"], clip["content_text"], int(is_active),
            month=clip["month"], program=clip["program"],
            series=clip["series"], speaker=clip["speaker"],
            service_date=clip["service_date"], tags=clip["tags"],
            is_featured=clip["is_featured"],
            audio_file_id=clip["audio_file_id"], audio_url=clip["audio_url"],
            video_file_id=clip["video_file_id"], video_url=clip["video_url"],
        )
    return redirect(url_for("admin_panel"))


@app.route("/admin/clip/delete", methods=["POST"])
@login_required
@admin_required
def admin_delete_clip():
    clip_id = request.form.get("clip_id")
    delete_prophecy_clip(clip_id)
    flash("Clip deleted", "success")
    return redirect(url_for("admin_panel"))


if __name__ == "__main__":
    PORT = int(os.getenv("PORT", 5000))
    app.run(host="0.0.0.0", port=PORT, debug=False)
