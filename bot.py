import os
import re
import uuid
import asyncio
import sqlite3
import subprocess
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, BotCommand
from telegram.ext import (
    ApplicationBuilder, CommandHandler, CallbackQueryHandler,
    ContextTypes, MessageHandler, filters
)

load_dotenv()

WAITING_FOR_DOWNLOAD = 3
WAITING_FOR_CONVERT = 4
WAITING_FOR_SCHEDULE = 5

PROPHECY_TITLE = 200
PROPHECY_MONTH = 201
PROPHECY_PROGRAM = 202
PROPHECY_CONTENT = 203

TESTIMONY_TITLE = 210
TESTIMONY_CONTENT = 211

processing_lock = asyncio.Lock()

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID"))

# Import Drive functions
from drive import upload_to_drive, download_from_drive


def is_drive_url(url: str) -> bool:
    return "drive.google.com" in url


def detect_platform(url: str) -> str:
    platforms = {
        "youtube.com": "YouTube",
        "youtu.be": "YouTube",
        "instagram.com": "Instagram",
        "tiktok.com": "TikTok",
        "facebook.com": "Facebook",
        "fb.watch": "Facebook",
        "twitter.com": "Twitter/X",
        "x.com": "Twitter/X",
        "vimeo.com": "Vimeo",
        "soundcloud.com": "SoundCloud",
        "drive.google.com": "Google Drive",
    }
    for domain, name in platforms.items():
        if domain in url:
            return name
    return "Unknown Platform"


def fetch_title(url: str) -> str:
    try:
        result = subprocess.run(
            ["yt-dlp", "--get-title", "--no-playlist", url],
            capture_output=True, text=True, timeout=30
        )
        title = result.stdout.strip()
        return title if title else "Untitled Clip"
    except Exception:
        return "Untitled Clip"


def extract_thumbnail(video_path: str, output_path: str, time: str = "00:00:03") -> str | None:
    try:
        subprocess.run([
            "ffmpeg", "-i", video_path,
            "-ss", time,
            "-vframes", "1",
            "-q:v", "2",
            output_path
        ], check=True, capture_output=True)
        return output_path if os.path.exists(output_path) else None
    except Exception:
        return None


def fetch_youtube_thumbnail(url: str, output_path: str) -> str | None:
    try:
        subprocess.run([
            "yt-dlp",
            "--write-thumbnail",
            "--skip-download",
            "--convert-thumbnails", "jpg",
            "-o", output_path,
            url
        ], check=True, capture_output=True)
        jpg_path = output_path + ".jpg"
        return jpg_path if os.path.exists(jpg_path) else None
    except Exception:
        return None


def add_to_queue(chat_id: int, url: str, fmt: str, title: str,
                 job_type: str = "cut", start_time: str = None, end_time: str = None) -> int:
    conn = sqlite3.connect("bot.db")
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO queue (chat_id, url, start_time, end_time, fmt, title, job_type)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (chat_id, url, start_time, end_time, fmt, title, job_type))
    job_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return job_id


def update_queue_status(job_id: int, status: str):
    conn = sqlite3.connect("bot.db")
    cursor = conn.cursor()
    cursor.execute("UPDATE queue SET status = ? WHERE id = ?", (status, job_id))
    conn.commit()
    conn.close()


def get_pending_jobs() -> list:
    conn = sqlite3.connect("bot.db")
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, chat_id, url, start_time, end_time, fmt, title, job_type
        FROM queue WHERE status = 'pending'
        ORDER BY created_at ASC
    """)
    jobs = cursor.fetchall()
    conn.close()
    return jobs


async def download_with_progress_bot(url: str, raw_path: str, status_msg, bot):
    last_reported = -1
    cookies_file = os.getenv("COOKIES_FILE")

    cmd = [
        "yt-dlp",
        "-f", "bestvideo+bestaudio/best",
        "--merge-output-format", "mp4",
        "--newline",
        "-o", raw_path,
    ]

    if cookies_file and os.path.exists(cookies_file) and os.path.getsize(cookies_file) > 0:
        cmd += ["--cookies", cookies_file]

    cmd.append(url)

    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True
    )

    for line in process.stdout:
        match = re.search(r"(\d+\.?\d*)%", line)
        if match:
            percent = float(match.group(1))
            bucket = int(percent // 5) * 5
            if bucket != last_reported and bucket <= 100:
                last_reported = bucket
                filled = bucket // 10
                bar = "█" * filled + "░" * (10 - filled)
                try:
                    await bot.edit_message_text(
                        chat_id=status_msg.chat.id,
                        message_id=status_msg.message_id,
                        text=f"📥 Downloading...\n\n{bar} {bucket}%"
                    )
                except Exception:
                    pass

    process.wait()
    if process.returncode != 0:
        raise Exception("Download failed.")


def get_file_size_mb(path: str) -> float:
    return os.path.getsize(path) / (1024 * 1024)


async def on_startup(app):
    await app.bot.set_my_commands([
        BotCommand("start", "Open the main menu"),
        BotCommand("clips", "Browse or broadcast clips"),
        BotCommand("subscribe", "Subscribe to receive clips"),
        BotCommand("unsubscribe", "Unsubscribe from clips"),
        BotCommand("prophecy", "Browse the prophecy feed"),
        BotCommand("cancel", "Cancel current action"),
    ])
    print("Commands registered.")


def init_db():
    conn = sqlite3.connect("bot.db")
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS subscribers (
            chat_id INTEGER PRIMARY KEY,
            username TEXT,
            joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS clips (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            file_id TEXT,
            title TEXT,
            fmt TEXT,
            thumbnail TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            broadcast INTEGER DEFAULT 0
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS broadcasts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            clip_id INTEGER,
            success INTEGER DEFAULT 0,
            failed INTEGER DEFAULT 0,
            sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS queue (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER,
            url TEXT,
            start_time TEXT,
            end_time TEXT,
            fmt TEXT,
            title TEXT,
            job_type TEXT DEFAULT 'cut',
            status TEXT DEFAULT 'pending',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS scheduled (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            clip_id INTEGER,
            scheduled_time TEXT,
            status TEXT DEFAULT 'pending',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    try:
        cursor.execute("ALTER TABLE clips ADD COLUMN thumbnail TEXT")
    except:
        pass
    conn.commit()
    conn.close()

    # Prophecy tables
    conn = sqlite3.connect("bot.db")
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            telegram_id INTEGER,
            delivery_time TEXT DEFAULT '08:00',
            delivery_frequency TEXT DEFAULT 'daily',
            timezone TEXT DEFAULT 'Africa/Lagos',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS prophecy_clips (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            content_text TEXT,
            audio_file_id TEXT,
            audio_url TEXT,
            video_file_id TEXT,
            video_url TEXT,
            thumbnail TEXT,
            is_active INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS prophecy_delivery_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            clip_id INTEGER,
            delivered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            method TEXT DEFAULT 'telegram',
            FOREIGN KEY (user_id) REFERENCES users(id),
            FOREIGN KEY (clip_id) REFERENCES prophecy_clips(id)
        )
    """)
    conn.commit()
    conn.close()


def admin_menu():
    keyboard = [
        [InlineKeyboardButton("✂️ Cut Clip", callback_data="cut_new")],
        [InlineKeyboardButton("⬇️ Download Full File", callback_data="download_new")],
        [InlineKeyboardButton("🔄 Convert File", callback_data="convert_new")],
        [InlineKeyboardButton("📜 Add Prophecy", callback_data="add_prophecy")],
        [InlineKeyboardButton("📡 Broadcast Clip", callback_data="broadcast_menu")],
        [InlineKeyboardButton("⏰ Schedule Broadcast", callback_data="schedule_menu")],
        [InlineKeyboardButton("👥 View Subscribers", callback_data="view_subs")],
        [InlineKeyboardButton("📋 Clip History", callback_data="clip_history")],
        [InlineKeyboardButton("📖 Help", callback_data="help")],
    ]
    return InlineKeyboardMarkup(keyboard)


def user_menu():
    keyboard = [
        [InlineKeyboardButton("🎬 Browse Clips", callback_data="browse_clips")],
        [InlineKeyboardButton("🕊️ Prophecy Feed", callback_data="prophecy_menu")],
        [InlineKeyboardButton("📓 My Prophecy Bank", callback_data="my_bank")],
        [InlineKeyboardButton("🗣 Share Testimony", callback_data="add_testimony")],
        [InlineKeyboardButton("✅ Subscribe", callback_data="subscribe")],
        [InlineKeyboardButton("❌ Unsubscribe", callback_data="unsubscribe")],
        [InlineKeyboardButton("📖 Help", callback_data="help")],
    ]
    return InlineKeyboardMarkup(keyboard)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id == ADMIN_ID:
        await update.message.reply_text(
            "👋 *Admin Dashboard*\n\nWhat would you like to do?",
            parse_mode="Markdown",
            reply_markup=admin_menu()
        )
    else:
        await update.message.reply_text(
            "👋 *Welcome!*\n\nSubscribe to receive clips directly to your chat, or browse available clips.",
            parse_mode="Markdown",
            reply_markup=user_menu()
        )


async def download_with_progress(url: str, raw_path: str, status_msg):
    last_reported = -1
    cookies_file = os.getenv("COOKIES_FILE")

    cmd = [
        "yt-dlp",
        "-f", "bestvideo+bestaudio/best",
        "--merge-output-format", "mp4",
        "--newline",
        "-o", raw_path,
    ]

    if cookies_file and os.path.exists(cookies_file) and os.path.getsize(cookies_file) > 0:
        cmd += ["--cookies", cookies_file]

    cmd.append(url)

    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True
    )

    for line in process.stdout:
        match = re.search(r"(\d+\.?\d*)%", line)
        if match:
            percent = float(match.group(1))
            bucket = int(percent // 5) * 5
            if bucket != last_reported and bucket <= 100:
                last_reported = bucket
                filled = bucket // 10
                bar = "█" * filled + "░" * (10 - filled)
                try:
                    await status_msg.edit_text(f"📥 Downloading...\n\n{bar} {bucket}%")
                except Exception:
                    pass

    process.wait()
    if process.returncode != 0:
        raise Exception("Download failed. If this is a private post, cookies may be required.")


def convert_file(input_path: str, target_fmt: str, unique_id: str) -> str:
    output_path = f"downloads/converted_{unique_id}.{target_fmt}"

    fmt_map = {
        "mp3": ["-q:a", "0", "-map", "a"],
        "wav": ["-vn", "-acodec", "pcm_s16le"],
        "aac": ["-vn", "-acodec", "aac", "-b:a", "192k"],
        "mp4": ["-c:v", "libx264", "-c:a", "aac"],
        "mov": ["-c:v", "libx264", "-c:a", "aac"],
    }

    if target_fmt not in fmt_map:
        raise ValueError(f"Unsupported format: {target_fmt}")

    cmd = ["ffmpeg", "-i", input_path] + fmt_map[target_fmt] + [output_path]
    subprocess.run(cmd, check=True, capture_output=True)
    return output_path


async def handle_convert_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return

    message = update.message

    file = None
    original_name = "file"

    if message.video:
        file = message.video
        original_name = file.file_name or "video.mp4"
    elif message.audio:
        file = message.audio
        original_name = file.file_name or "audio.mp3"
    elif message.document:
        file = message.document
        original_name = file.file_name or "file"
    elif message.voice:
        file = message.voice
        original_name = "voice.ogg"
    else:
        await message.reply_text(
            "Please send a file (video or audio) with your target format in the caption.\n\n"
            "Example: send a video file with caption `mp3`",
            parse_mode="Markdown"
        )
        return

    caption = (message.caption or "").strip().lower()
    supported = ["mp3", "mp4", "wav", "aac", "mov"]

    if caption not in supported:
        await message.reply_text(
            f"Please specify a target format in the file caption.\n\n"
            f"Supported: `mp3` `mp4` `wav` `aac` `mov`",
            parse_mode="Markdown"
        )
        return

    status = await message.reply_text("⏳ Starting conversion...")

    os.makedirs("downloads", exist_ok=True)
    unique_id = str(uuid.uuid4())[:8]
    ext = os.path.splitext(original_name)[1] or ".tmp"
    input_path = f"downloads/input_{unique_id}{ext}"

    try:
        await status.edit_text("📥 Downloading file...")
        tg_file = await context.bot.get_file(file.file_id)
        await tg_file.download_to_drive(input_path)

        await status.edit_text(f"⚙️ Converting to {caption.upper()}...")
        output_path = convert_file(input_path, caption, unique_id)

        file_size = get_file_size_mb(output_path)

        if file_size > 45:
            await status.edit_text("📤 File too large for Telegram — uploading to Drive...")
            filename = os.path.splitext(original_name)[0] + f".{caption}"
            drive_link = upload_to_drive(output_path, filename)
            await status.edit_text(
                f"✅ Converted to {caption.upper()}!\n\n🔗 Download: {drive_link}",
                parse_mode="Markdown"
            )
        else:
            await status.edit_text("📤 Sending converted file...")
            with open(output_path, "rb") as f:
                if caption == "mp3":
                    await message.reply_audio(f, title=os.path.splitext(original_name)[0])
                elif caption in ("mp4", "mov"):
                    await message.reply_video(f)
                else:
                    await message.reply_document(f)

            await status.edit_text(f"✅ Converted to {caption.upper()} successfully!")

        os.remove(input_path)
        os.remove(output_path)

    except Exception as e:
        await status.edit_text(f"❌ Conversion failed:\n{str(e)}")
        if os.path.exists(input_path):
            os.remove(input_path)

    await message.reply_text("Back to menu:", reply_markup=admin_menu())


async def handle_schedule_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return

    text = update.message.text.strip()
    parts = text.split()

    if len(parts) < 2:
        await update.message.reply_text(
            "Format: [clip_id] [YYYY-MM-DD HH:MM]\n\nExample: `1 2025-12-25 09:00`",
            parse_mode="Markdown"
        )
        return

    clip_id = parts[0]
    scheduled_time = " ".join(parts[1:])

    conn = sqlite3.connect("bot.db")
    cursor = conn.cursor()
    cursor.execute("SELECT title FROM clips WHERE id = ?", (clip_id,))
    clip = cursor.fetchone()

    if not clip:
        await update.message.reply_text("Clip not found. Try again or /cancel")
        conn.close()
        return

    cursor.execute(
        "INSERT INTO scheduled (clip_id, scheduled_time) VALUES (?, ?)",
        (clip_id, scheduled_time)
    )
    conn.commit()
    conn.close()

    await update.message.reply_text(
        f"⏰ *{clip[0]}* scheduled for {scheduled_time}",
        parse_mode="Markdown"
    )
    await update.message.reply_text("Back to menu:", reply_markup=admin_menu())
    context.user_data["state"] = None


def build_broadcast_menu():
    conn = sqlite3.connect("bot.db")
    cursor = conn.cursor()
    cursor.execute("SELECT id, title, fmt, broadcast FROM clips ORDER BY id DESC LIMIT 9")
    clips = cursor.fetchall()
    conn.close()

    rows = []
    for c in clips:
        clip_id, title, fmt, broadcast = c[0], c[1], c[2], c[3]
        icon = "✅" if broadcast else "📡"
        label = f"{icon} {title or f'Clip #{clip_id}'} ({fmt.upper()})"
        rows.append([InlineKeyboardButton(label, callback_data=f"bc_{clip_id}")])

    rows.append([InlineKeyboardButton("🔙 Back to Menu", callback_data="back_to_menu")])
    return InlineKeyboardMarkup(rows)


async def process_queue(app):
    while True:
        async with processing_lock:
            jobs = get_pending_jobs()
            for job in jobs:
                job_id, chat_id, url, start_time, end_time, fmt, title, job_type = job
                update_queue_status(job_id, "processing")

                try:
                    await app.bot.send_message(
                        chat_id=chat_id,
                        text=f"⚙️ Processing job #{job_id}: *{title}*",
                        parse_mode="Markdown"
                    )

                    os.makedirs("downloads", exist_ok=True)
                    unique_id = str(uuid.uuid4())[:8]
                    raw_path = f"downloads/raw_{unique_id}.%(ext)s"

                    status_msg = await app.bot.send_message(
                        chat_id=chat_id,
                        text="📥 Downloading..."
                    )

                    if is_drive_url(url):
                        raw_full = download_from_drive(url, f"downloads/raw_{unique_id}")
                    else:
                        await download_with_progress_bot(url, raw_path, status_msg, app.bot)
                        raw_full = next(
                            f"downloads/{f}" for f in os.listdir("downloads")
                            if f.startswith(f"raw_{unique_id}")
                        )

                    await app.bot.edit_message_text(
                        chat_id=chat_id,
                        message_id=status_msg.message_id,
                        text="✂️ Cutting clip..."
                    )

                    output_path = f"downloads/clip_{unique_id}"

                    if job_type == "cut":
                        if fmt == "mp3":
                            final_path = f"{output_path}.mp3"
                            subprocess.run([
                                "ffmpeg", "-i", raw_full,
                                "-ss", start_time, "-to", end_time,
                                "-q:a", "0", "-map", "a",
                                final_path
                            ], check=True, capture_output=True)
                        else:
                            final_path = f"{output_path}.mp4"
                            subprocess.run([
                                "ffmpeg", "-i", raw_full,
                                "-ss", start_time, "-to", end_time,
                                "-c", "copy",
                                final_path
                            ], check=True, capture_output=True)
                    else:
                        if fmt == "mp3":
                            final_path = f"{output_path}.mp3"
                            subprocess.run([
                                "ffmpeg", "-i", raw_full,
                                "-q:a", "0", "-map", "a",
                                final_path
                            ], check=True, capture_output=True)
                        else:
                            final_path = f"{output_path}.mp4"
                            subprocess.run([
                                "ffmpeg", "-i", raw_full,
                                "-c", "copy",
                                final_path
                            ], check=True, capture_output=True)

                    if os.path.exists(raw_full):
                        os.remove(raw_full)

                    thumb_path = f"downloads/thumb_{unique_id}.jpg"
                    if fmt == "mp4":
                        thumbnail = extract_thumbnail(final_path, thumb_path)
                    else:
                        thumbnail = fetch_youtube_thumbnail(url, f"downloads/thumb_{unique_id}")
                        if thumbnail:
                            thumb_path = thumbnail
                        else:
                            thumbnail = None

                    file_size = get_file_size_mb(final_path)

                    if file_size > 45:
                        await app.bot.edit_message_text(
                            chat_id=chat_id,
                            message_id=status_msg.message_id,
                            text="📤 Uploading to Drive..."
                        )
                        drive_link = upload_to_drive(final_path, f"{title}.{fmt}")

                        conn = sqlite3.connect("bot.db")
                        c = conn.cursor()
                        c.execute(
                            "INSERT INTO clips (file_id, fmt, title, thumbnail) VALUES (?, ?, ?, ?)",
                            (drive_link, fmt, title, thumbnail)
                        )
                        clip_id = c.lastrowid
                        conn.commit()
                        conn.close()

                        await app.bot.edit_message_text(
                            chat_id=chat_id,
                            message_id=status_msg.message_id,
                            text=f"✅ *{title}*\n\nSaved to Drive! ID: *{clip_id}*\n\n🔗 {drive_link}",
                            parse_mode="Markdown"
                        )
                    else:
                        await app.bot.edit_message_text(
                            chat_id=chat_id,
                            message_id=status_msg.message_id,
                            text="📤 Uploading to Telegram..."
                        )

                        with open(final_path, "rb") as f:
                            if fmt == "mp3":
                                sent = await app.bot.send_audio(
                                    chat_id=chat_id, audio=f, title=title
                                )
                                file_id = sent.audio.file_id
                            else:
                                sent = await app.bot.send_video(
                                    chat_id=chat_id, video=f
                                )
                                file_id = sent.video.file_id

                        conn = sqlite3.connect("bot.db")
                        c = conn.cursor()
                        c.execute(
                            "INSERT INTO clips (file_id, fmt, title, thumbnail) VALUES (?, ?, ?, ?)",
                            (file_id, fmt, title, thumbnail)
                        )
                        clip_id = c.lastrowid
                        conn.commit()
                        conn.close()

                        await app.bot.edit_message_text(
                            chat_id=chat_id,
                            message_id=status_msg.message_id,
                            text=f"✅ *{title}*\n\nClip saved! ID: *{clip_id}*\n\nGo to menu to broadcast.",
                            parse_mode="Markdown"
                        )

                    if os.path.exists(final_path):
                        os.remove(final_path)

                    update_queue_status(job_id, "done")

                except Exception as e:
                    update_queue_status(job_id, "failed")
                    try:
                        await app.bot.send_message(
                            chat_id=chat_id,
                            text=f"❌ Job #{job_id} failed:\n{str(e)}"
                        )
                    except:
                        pass

        await asyncio.sleep(5)


async def check_scheduled(app):
    from datetime import datetime
    while True:
        now = datetime.now().strftime("%Y-%m-%d %H:%M")

        conn = sqlite3.connect("bot.db")
        cursor = conn.cursor()
        cursor.execute("""
            SELECT s.id, s.clip_id, c.file_id, c.fmt, c.title, c.thumbnail
            FROM scheduled s
            JOIN clips c ON s.clip_id = c.id
            WHERE s.scheduled_time = ? AND s.status = 'pending'
        """, (now,))
        due = cursor.fetchall()

        for row in due:
            sched_id, clip_id, file_id, fmt, title, thumbnail_path = row

            cursor.execute("SELECT chat_id FROM subscribers")
            subscribers = cursor.fetchall()

            success = 0
            failed = 0

            for (chat_id,) in subscribers:
                try:
                    if thumbnail_path and os.path.exists(thumbnail_path):
                        with open(thumbnail_path, "rb") as t:
                            await app.bot.send_photo(
                                chat_id=chat_id,
                                photo=t,
                                caption=f"🎬 *{title}*",
                                parse_mode="Markdown"
                            )
                    if file_id.startswith("https://"):
                        await app.bot.send_message(chat_id=chat_id, text=f"🔗 {file_id}")
                    elif fmt == "mp3":
                        await app.bot.send_audio(chat_id=chat_id, audio=file_id)
                    else:
                        await app.bot.send_video(chat_id=chat_id, video=file_id)
                    success += 1
                except Exception:
                    failed += 1

            cursor.execute("UPDATE scheduled SET status = 'sent' WHERE id = ?", (sched_id,))
            cursor.execute("UPDATE clips SET broadcast = 1 WHERE id = ?", (clip_id,))
            conn.commit()

            await app.bot.send_message(
                chat_id=ADMIN_ID,
                text=f"⏰ Scheduled broadcast complete: *{title}*\n\n✔️ {success} sent\n❌ {failed} failed",
                parse_mode="Markdown"
            )

        conn.close()
        await asyncio.sleep(60)


async def auto_deliver_prophecies(app):
    from datetime import datetime
    while True:
        now = datetime.now()
        current_time = now.strftime("%H:%M")
        today = now.strftime("%Y-%m-%d")

        conn = sqlite3.connect("bot.db")
        cursor = conn.cursor()

        cursor.execute("SELECT id, email, telegram_id, delivery_time, delivery_frequency, timezone FROM users WHERE telegram_id IS NOT NULL")
        users = cursor.fetchall()

        for user in users:
            uid, email, tid, dtime, freq, tz = user
            if not tid or not dtime:
                continue

            if current_time != dtime:
                continue

            if freq == "weekly" and now.weekday() != 0:
                continue

            cursor.execute("""SELECT id, title, audio_file_id, video_file_id, content_text FROM prophecy_clips WHERE is_active = 1 AND id NOT IN (SELECT clip_id FROM prophecy_delivery_log WHERE user_id = ?) ORDER BY created_at ASC LIMIT 1""", (uid,))
            clip = cursor.fetchone()
            if not clip:
                continue

            cid, title, aid, vid, text = clip
            try:
                if aid:
                    await app.bot.send_audio(chat_id=tid, audio=aid, caption=f"🕊️ *{title}*", parse_mode="Markdown")
                elif vid:
                    await app.bot.send_video(chat_id=tid, video=vid, caption=f"🕊️ *{title}*", parse_mode="Markdown")
                elif text:
                    msg = f"🕊️ *{title}*\n\n{text}"
                    await app.bot.send_message(chat_id=tid, text=msg, parse_mode="Markdown")
                else:
                    await app.bot.send_message(chat_id=tid, text=f"🕊️ *{title}*", parse_mode="Markdown")

                cursor.execute("INSERT INTO prophecy_delivery_log (user_id, clip_id, method) VALUES (?, ?, 'telegram')", (uid, cid))
                conn.commit()

                await app.bot.send_message(
                    chat_id=ADMIN_ID,
                    text=f"🕊️ Prophecy delivered: *{title}* → {email}",
                    parse_mode="Markdown"
                )
            except Exception as e:
                print(f"Prophecy delivery failed for {email}: {e}")

        conn.close()
        await asyncio.sleep(60)


async def handle_cut_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return

    text = update.message.text.strip()
    parts = text.split()

    if len(parts) < 4:
        await update.message.reply_text(
            "Format: [url] [start HH:MM:SS] [end HH:MM:SS] [mp3 or mp4]\n\nTry again or /cancel"
        )
        context.user_data["state"] = "cut"
        return

    url, start, end, fmt = parts[0], parts[1], parts[2], parts[3]

    if fmt not in ("mp3", "mp4"):
        await update.message.reply_text("Format must be mp3 or mp4. Try again or /cancel")
        context.user_data["state"] = "cut"
        return

    if '"' in text:
        clip_title = text.split('"')[1]
    else:
        clip_title = fetch_title(url)

    job_id = add_to_queue(
        chat_id=update.effective_chat.id,
        url=url,
        fmt=fmt,
        title=clip_title,
        job_type="cut",
        start_time=start,
        end_time=end
    )

    pending = len(get_pending_jobs())

    await update.message.reply_text(
        f"✅ Added to queue! Job #{job_id}: *{clip_title}*\n\n📋 Position in queue: {pending}",
        parse_mode="Markdown"
    )

    await update.message.reply_text("Back to menu:", reply_markup=admin_menu())
    context.user_data["state"] = None


async def handle_download_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return

    text = update.message.text.strip()
    parts = text.split()

    if len(parts) < 2:
        await update.message.reply_text(
            "Format: [url] [mp3 or mp4]\nTry again or /cancel"
        )
        return

    url, fmt = parts[0], parts[1]

    if fmt not in ("mp3", "mp4"):
        await update.message.reply_text("Format must be mp3 or mp4. Try again or /cancel")
        return

    if '"' in text:
        clip_title = text.split('"')[1]
    else:
        clip_title = fetch_title(url)

    job_id = add_to_queue(
        chat_id=update.effective_chat.id,
        url=url,
        fmt=fmt,
        title=clip_title,
        job_type="download"
    )

    pending = len(get_pending_jobs())

    await update.message.reply_text(
        f"✅ Added to queue! Job #{job_id}: *{clip_title}*\n\n📋 Position in queue: {pending}",
        parse_mode="Markdown"
    )

    await update.message.reply_text("Back to menu:", reply_markup=admin_menu())
    context.user_data["state"] = None


def build_broadcast_menu():
    conn = sqlite3.connect("bot.db")
    cursor = conn.cursor()
    cursor.execute("SELECT id, title, fmt, broadcast FROM clips ORDER BY id DESC LIMIT 9")
    clips = cursor.fetchall()
    conn.close()

    rows = []
    for c in clips:
        clip_id, title, fmt, broadcast = c[0], c[1], c[2], c[3]
        icon = "✅" if broadcast else "📡"
        label = f"{icon} {title or f'Clip #{clip_id}'} ({fmt.upper()})"
        rows.append([InlineKeyboardButton(label, callback_data=f"bc_{clip_id}")])

    rows.append([InlineKeyboardButton("🔙 Back to Menu", callback_data="back_to_menu")])
    return InlineKeyboardMarkup(rows)


def build_user_clips_menu():
    conn = sqlite3.connect("bot.db")
    cursor = conn.cursor()
    cursor.execute("SELECT id, title, fmt FROM clips ORDER BY id DESC LIMIT 9")
    clips = cursor.fetchall()
    conn.close()

    if not clips:
        return None

    rows = []
    for c in clips:
        clip_id, title, fmt = c[0], c[1], c[2]
        label = f"🎬 {title or f'Clip #{clip_id}'} ({fmt.upper()})"
        rows.append([InlineKeyboardButton(label, callback_data=f"get_{clip_id}")])

    rows.append([InlineKeyboardButton("🔙 Back to Menu", callback_data="back_to_menu")])
    return InlineKeyboardMarkup(rows)


async def do_broadcast_clip(clip_id, context):
    conn = sqlite3.connect("bot.db")
    cursor = conn.cursor()
    cursor.execute("SELECT file_id, fmt, title, thumbnail FROM clips WHERE id = ?", (clip_id,))
    clip = cursor.fetchone()

    if not clip:
        conn.close()
        return "❌ Clip not found."

    file_id, fmt, clip_title, thumbnail_path = clip

    cursor.execute("SELECT chat_id FROM subscribers")
    subscribers = cursor.fetchall()
    conn.close()

    if not subscribers:
        return "❌ No subscribers yet."

    status_text = f"📡 Broadcasting to {len(subscribers)} subscribers..."
    status_msg = await context.bot.send_message(
        chat_id=ADMIN_ID, text=status_text
    )

    success = 0
    failed = 0

    for (chat_id,) in subscribers:
        try:
            if thumbnail_path and os.path.exists(thumbnail_path):
                with open(thumbnail_path, "rb") as t:
                    await context.bot.send_photo(
                        chat_id=chat_id,
                        photo=t,
                        caption=f"🎬 *{clip_title}*",
                        parse_mode="Markdown"
                    )
            elif file_id.startswith("https://"):
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=f"🎬 *{clip_title}*\n\n🔗 {file_id}"
                )
            elif fmt == "mp3":
                await context.bot.send_audio(chat_id=chat_id, audio=file_id)
            else:
                await context.bot.send_video(chat_id=chat_id, video=file_id)
            success += 1
        except Exception:
            failed += 1

    conn = sqlite3.connect("bot.db")
    cursor = conn.cursor()
    cursor.execute("UPDATE clips SET broadcast = 1 WHERE id = ?", (clip_id,))
    cursor.execute("INSERT INTO broadcasts (clip_id, success, failed) VALUES (?, ?, ?)", (clip_id, success, failed))
    conn.commit()
    conn.close()

    msg = f"✅ *Broadcast complete.*\n\n✔️ Sent: {success}\n❌ Failed: {failed}"
    await status_msg.edit_text(msg, parse_mode="Markdown", reply_markup=admin_menu())
    return msg


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    is_admin = update.effective_user.id == ADMIN_ID

    if is_admin:
        text = """
📖 *ShareStill — Admin Guide*

━━━━━━━━━━━━━━━
✂️ *CUT A CLIP*
━━━━━━━━━━━━━━━
Tap *Cut Clip* from the menu and send:
`[url] [start HH:MM:SS] [end HH:MM:SS] [mp3 or mp4]`
`[url] [start] [end] [format] "Custom Name"`

Example:
`https://youtube.com/watch?v=xxx 00:10:30 00:15:00 mp3 "Sunday Highlight"`

━━━━━━━━━━━━━━━
⬇️ *DOWNLOAD FULL FILE*
━━━━━━━━━━━━━━━
Tap *Download Full File* from the menu and send:
`[url] [mp3 or mp4]`
`[url] [format] "Custom Name"`

Example:
`https://youtube.com/watch?v=xxx mp4 "Full Sunday Service"`

━━━━━━━━━━━━━━━
📡 *BROADCAST*
━━━━━━━━━━━━━━━
Tap *Broadcast Clip* from the menu.
Select a clip ID from the list to send to all subscribers.

━━━━━━━━━━━━━━━
👥 *SUBSCRIBERS*
━━━━━━━━━━━━━━━
Tap *View Subscribers* to see total count and recent joins.

━━━━━━━━━━━━━━━
🌐 *SUPPORTED PLATFORMS*
━━━━━━━━━━━━━━━
- YouTube
- Google Drive
- Instagram _(public posts)_
- TikTok _(public posts)_
- Facebook
- Twitter/X
- Vimeo
- SoundCloud
- 1000+ other sites via yt-dlp

━━━━━━━━━━━━━━━
📁 *FILE HANDLING*
━━━━━━━━━━━━━━━
- Under 45MB → sent directly on Telegram
- Over 45MB → uploaded to Google Drive, link sent to subscribers

━━━━━━━━━━━━━━━
🖼 *THUMBNAILS*
━━━━━━━━━━━━━━━
Thumbnails are generated automatically and sent to subscribers before each clip.

━━━━━━━━━━━━━━━
🔄 *CONVERT FILE*
━━━━━━━━━━━━━━━
Tap *Convert File* from the menu.
Send any audio or video file with the target format as the caption.

Supported formats: mp3, mp4, wav, aac, mov

Example: send an MP4 file with caption `mp3`
Files over 45MB are uploaded to Google Drive automatically.

━━━━━━━━━━━━━━━
⌨️ *COMMANDS*
━━━━━━━━━━━━━━━
/start — Open menu
/help — This guide
/cancel — Cancel current action
"""
    else:
        text = """
📖 *ShareStill — User Guide*

━━━━━━━━━━━━━━━
✅ *SUBSCRIBE*
━━━━━━━━━━━━━━━
Tap *Subscribe* from the menu to start receiving clips automatically.

━━━━━━━━━━━━━━━
❌ *UNSUBSCRIBE*
━━━━━━━━━━━━━━━
Tap *Unsubscribe* at any time to stop receiving clips.

━━━━━━━━━━━━━━━
📬 *WHAT YOU RECEIVE*
━━━━━━━━━━━━━━━
When a new clip is broadcast you will receive:
- A thumbnail preview
- The audio or video clip
- Or a download link for larger files

━━━━━━━━━━━━━━━
⌨️ *COMMANDS*
━━━━━━━━━━━━━━━
/start — Open menu
/help — This guide
"""

    await update.message.reply_text(text, parse_mode="Markdown")


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["state"] = None
    if update.effective_user.id == ADMIN_ID:
        await update.message.reply_text("Cancelled.", reply_markup=admin_menu())
    else:
        await update.message.reply_text("Cancelled.", reply_markup=user_menu())


async def handle_subscribe(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    username = update.effective_user.username or "unknown"

    conn = sqlite3.connect("bot.db")
    cursor = conn.cursor()
    cursor.execute("SELECT chat_id FROM subscribers WHERE chat_id = ?", (chat_id,))
    existing = cursor.fetchone()
    if existing:
        conn.close()
        await update.message.reply_text(
            "✅ *You're already subscribed!*",
            parse_mode="Markdown",
            reply_markup=user_menu()
        )
        return
    cursor.execute(
        "INSERT INTO subscribers (chat_id, username) VALUES (?, ?)",
        (chat_id, username)
    )
    conn.commit()
    conn.close()

    try:
        await context.bot.send_message(
            chat_id=ADMIN_ID,
            text=f"🔔 *New Subscriber!*\n\n👤 @{username} just joined.",
            parse_mode="Markdown"
        )
    except Exception:
        pass

    await update.message.reply_text(
        "✅ *You're subscribed!*\n\nYou'll receive clips when they're sent out.",
        parse_mode="Markdown",
        reply_markup=user_menu()
    )


async def handle_unsubscribe(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    conn = sqlite3.connect("bot.db")
    cursor = conn.cursor()
    cursor.execute("DELETE FROM subscribers WHERE chat_id = ?", (chat_id,))
    conn.commit()
    removed = cursor.rowcount > 0
    conn.close()

    if removed:
        await update.message.reply_text(
            "❌ *You've been unsubscribed.*\n\nYou can subscribe again anytime.",
            parse_mode="Markdown",
            reply_markup=user_menu()
        )
    else:
        await update.message.reply_text(
            "You weren't subscribed.",
            reply_markup=user_menu()
        )


async def handle_clips(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id == ADMIN_ID:
        await update.message.reply_text(
            "📡 *Select a clip to broadcast:*",
            parse_mode="Markdown",
            reply_markup=build_broadcast_menu()
        )
    else:
        keyboard = build_user_clips_menu()
        if keyboard:
            await update.message.reply_text(
                "🎬 *Available Clips*\n\nTap a clip to get it sent to your chat:",
                parse_mode="Markdown",
                reply_markup=keyboard
            )
        else:
            await update.message.reply_text(
                "📭 *No clips available yet.*\n\nCheck back later!",
                parse_mode="Markdown",
                reply_markup=user_menu()
            )


async def handle_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return

    conn = sqlite3.connect("bot.db")
    cursor = conn.cursor()

    cursor.execute("SELECT COUNT(*) FROM subscribers")
    total_subs = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM clips")
    total_clips = cursor.fetchall()[0][0]

    cursor.execute("SELECT COUNT(*) FROM clips WHERE broadcast = 1")
    clips_broadcast = cursor.fetchone()[0]

    cursor.execute("SELECT SUM(success) FROM broadcasts")
    total_sent = cursor.fetchone()[0] or 0

    cursor.execute("SELECT SUM(failed) FROM broadcasts")
    total_failed = cursor.fetchone()[0] or 0

    cursor.execute("SELECT COUNT(*) FROM subscribers WHERE joined_at >= datetime('now', '-7 days')")
    new_this_week = cursor.fetchone()[0]

    conn.close()

    msg = f"""📊 *Analytics Dashboard*

👥 *Subscribers:* {total_subs}
   └ New this week: +{new_this_week}

🎬 *Clips:* {total_clips} total, {clips_broadcast} broadcast

📤 *Broadcasts:*
   └ Sent: {total_sent}
   └ Failed: {total_failed}

💡 Share the bot to grow your audience!"""

    await update.message.reply_text(msg, parse_mode="Markdown", reply_markup=admin_menu())


async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "cut_new":
        await query.message.reply_text(
            "Send the clip details:\n\n"
            "`[url] [start HH:MM:SS] [end HH:MM:SS] [mp3 or mp4]`\n\n"
            "Or with custom name:\n`[url] [start] [end] [format] \"Custom Name\"`\n\n"
            "Example:\n`https://youtube.com/watch?v=xxx 00:10:30 00:15:00 mp3 \"Amazing Sermon\"`",
            parse_mode="Markdown",
            reply_markup=admin_menu()
        )
        context.user_data["state"] = "cut"

    elif data == "download_new":
        await query.message.reply_text(
            "Send the download details:\n\n"
            "`[url] [mp3 or mp4]`\n\n"
            "With custom name:\n"
            "`[url] [mp3 or mp4] \"Custom Name\"`\n\n"
            "Works with YouTube, Instagram, TikTok, Facebook, Vimeo, SoundCloud, Google Drive and more.",
            parse_mode="Markdown"
        )
        context.user_data["state"] = WAITING_FOR_DOWNLOAD

    elif data == "convert_new":
        await query.message.reply_text(
            "Send your file with the target format as the caption.\n\n"
            "Supported formats: `mp3` `mp4` `wav` `aac` `mov`\n\n"
            "Example: send a video file with caption `mp3`",
            parse_mode="Markdown"
        )
        context.user_data["state"] = WAITING_FOR_CONVERT

    elif data == "broadcast_menu":
        await query.message.reply_text(
            "📡 *Select a clip to broadcast:*",
            parse_mode="Markdown",
            reply_markup=build_broadcast_menu()
        )

    elif data == "back_to_menu":
        if query.from_user.id == ADMIN_ID:
            await query.message.edit_text(
                "👋 *Admin Dashboard*\n\nWhat would you like to do?",
                parse_mode="Markdown",
                reply_markup=admin_menu()
            )
        else:
            await query.message.edit_text(
                "👋 *Welcome!*\n\nSubscribe to receive clips directly to your chat, or browse available clips.",
                parse_mode="Markdown",
                reply_markup=user_menu()
            )

    elif data == "schedule_menu":
        conn = sqlite3.connect("bot.db")
        cursor = conn.cursor()
        cursor.execute("SELECT id, fmt, title FROM clips WHERE broadcast = 0 ORDER BY id DESC LIMIT 10")
        clips = cursor.fetchall()
        conn.close()

        if not clips:
            await query.message.reply_text("No unbroadcast clips available.")
            return

        lines = ["*Unbroadcast Clips:*\n"]
        for c in clips:
            lines.append(f"ID {c[0]} — {c[1].upper()} — {c[2] or 'Untitled'}")

        lines.append("\nSend clip ID and scheduled time:\n`[clip_id] [YYYY-MM-DD HH:MM]`")
        await query.message.reply_text("\n".join(lines), parse_mode="Markdown")
        context.user_data["state"] = WAITING_FOR_SCHEDULE

    elif data == "prophecy_menu":
        conn = sqlite3.connect("bot.db")
        cursor = conn.cursor()
        cursor.execute("SELECT id, title, content_text, audio_file_id, video_file_id, created_at FROM prophecy_clips WHERE is_active = 1 ORDER BY created_at DESC LIMIT 10")
        clips = cursor.fetchall()
        conn.close()

        if not clips:
            msg = "🕊️ *Prophecy Feed*\n\nNo prophecies available yet. Check back soon!"
        else:
            lines = ["🕊️ *Prophecy Feed*\n"]
            for c in clips:
                cid, title, text, aid, vid, ts = c
                icon = "📜" if text else ("🎙️" if aid else "🎞️")
                date = ts[:10] if ts else ""
                lines.append(f"{icon} *{title}*")
                if text:
                    preview = text[:120] + ("..." if len(text) > 120 else "")
                    lines.append(f"   {preview}")
                lines.append(f"   _{date}_\n")
            msg = "\n".join(lines)

        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 Back", callback_data="back_to_menu")]
        ])
        await query.message.edit_text(msg, parse_mode="Markdown", reply_markup=keyboard)

    elif data.startswith("bc_"):
        clip_id = int(data.split("_")[1])

        conn = sqlite3.connect("bot.db")
        cursor = conn.cursor()
        cursor.execute("SELECT file_id, fmt, title, thumbnail FROM clips WHERE id = ?", (clip_id,))
        clip = cursor.fetchone()

        cursor.execute("SELECT COUNT(*) FROM subscribers")
        sub_count = cursor.fetchone()[0]
        conn.close()

        if not clip:
            await query.message.reply_text("Clip not found.")
            return

        file_id, fmt, title, thumbnail_path = clip

        preview_text = (
            f"📋 *Broadcast Preview*\n\n"
            f"🎬 *{title or 'Untitled'}*\n"
            f"📁 Format: {fmt.upper()}\n"
            f"👥 Will be sent to: {sub_count} subscribers\n\n"
            f"Confirm broadcast?"
        )

        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("✅ Confirm", callback_data=f"confirm_broadcast_{clip_id}"),
                InlineKeyboardButton("❌ Cancel", callback_data="cancel_broadcast")
            ]
        ])

        if thumbnail_path and os.path.exists(thumbnail_path):
            with open(thumbnail_path, "rb") as t:
                await query.message.reply_photo(
                    photo=t,
                    caption=preview_text,
                    parse_mode="Markdown",
                    reply_markup=keyboard
                )
        else:
            await query.message.reply_text(
                preview_text,
                parse_mode="Markdown",
                reply_markup=keyboard
            )

    elif data.startswith("confirm_broadcast_"):
        clip_id = int(data.split("_")[-1])

        conn = sqlite3.connect("bot.db")
        cursor = conn.cursor()
        cursor.execute("SELECT file_id, fmt, title, thumbnail FROM clips WHERE id = ?", (clip_id,))
        clip = cursor.fetchone()
        cursor.execute("SELECT chat_id FROM subscribers")
        subscribers = cursor.fetchall()
        conn.close()

        if not clip:
            await query.message.reply_text("Clip not found.")
            return

        file_id, fmt, clip_title, thumbnail_path = clip

        status = await query.message.reply_text(
            f"📡 Broadcasting *{clip_title}* to {len(subscribers)} subscribers...",
            parse_mode="Markdown"
        )

        success = 0
        failed = 0

        for (chat_id,) in subscribers:
            try:
                if thumbnail_path and os.path.exists(thumbnail_path):
                    with open(thumbnail_path, "rb") as t:
                        await context.bot.send_photo(
                            chat_id=chat_id,
                            photo=t,
                            caption=f"🎬 *{clip_title}*",
                            parse_mode="Markdown"
                        )

                if file_id.startswith("https://"):
                    await context.bot.send_message(chat_id=chat_id, text=f"🔗 Download: {file_id}")
                elif fmt == "mp3":
                    await context.bot.send_audio(chat_id=chat_id, audio=file_id)
                else:
                    await context.bot.send_video(chat_id=chat_id, video=file_id)
                success += 1
            except Exception:
                failed += 1

        conn = sqlite3.connect("bot.db")
        cursor = conn.cursor()
        cursor.execute("UPDATE clips SET broadcast = 1 WHERE id = ?", (clip_id,))
        conn.commit()
        conn.close()

        await status.edit_text(f"✅ Broadcast complete.\n\n✔️ Sent: {success}\n❌ Failed: {failed}")
        await query.message.reply_text("Back to menu:", reply_markup=admin_menu())

    elif data == "cancel_broadcast":
        await query.message.reply_text("Broadcast cancelled.", reply_markup=admin_menu())

    elif data.startswith("get_"):
        clip_id = int(data.split("_")[1])
        await query.message.edit_text(f"🎬 Sending clip #{clip_id} to you...")

        conn = sqlite3.connect("bot.db")
        cursor = conn.cursor()
        cursor.execute("SELECT file_id, fmt, title FROM clips WHERE id = ?", (clip_id,))
        clip = cursor.fetchone()
        conn.close()

        if not clip:
            await query.message.edit_text("❌ Clip not found.")
            return

        file_id, fmt, title = clip

        try:
            # Check if it's a Drive link
            if file_id.startswith("https://"):
                await context.bot.send_message(
                    chat_id=query.message.chat_id,
                    text=f"🎬 Here's your clip:\n{file_id}"
                )
            elif fmt == "mp3":
                await context.bot.send_audio(chat_id=query.message.chat_id, audio=file_id, title=title)
            else:
                await context.bot.send_video(chat_id=query.message.chat_id, video=file_id, title=title)
            await query.message.edit_text(
                f"✅ *Here's your clip!*\n\n📌 {title or f'Clip #{clip_id}'}",
                parse_mode="Markdown",
                reply_markup=user_menu()
            )
        except Exception:
            await query.message.edit_text(
                "❌ Couldn't send clip. Try again later.",
                reply_markup=user_menu()
            )

    elif data == "view_subs":
        try:
            conn = sqlite3.connect("bot.db")
            cursor = conn.cursor()
            cursor.execute("SELECT chat_id, username, joined_at FROM subscribers ORDER BY joined_at DESC LIMIT 20")
            subscribers = cursor.fetchall()
            conn.close()

            if not subscribers:
                await query.message.edit_text(
                    "👥 *No subscribers yet.*\n\nShare the bot with your audience!",
                    parse_mode="Markdown",
                    reply_markup=admin_menu()
                )
                return

            lines = [f"👥 *Subscribers: {len(subscribers)}*\n"]
            for s in subscribers:
                username = s[1] or "unknown"
                lines.append(f"• @{username} — {s[2][:10]}")

            await query.message.edit_text("\n".join(lines), parse_mode="Markdown", reply_markup=admin_menu())
        except Exception as e:
            await query.message.edit_text(f"❌ Error: {str(e)}", reply_markup=admin_menu())

    elif data == "send_message":
        await query.message.reply_text(
            "📝 *Send a Message to All Subscribers*\n\n"
            "Type your message below and it will be sent to all subscribers.\n\n"
            "Use /cancel to go back.",
            parse_mode="Markdown",
            reply_markup=admin_menu()
        )
        context.user_data["state"] = "broadcast_msg"

    elif data == "analytics":
        conn = sqlite3.connect("bot.db")
        cursor = conn.cursor()

        cursor.execute("SELECT COUNT(*) FROM subscribers")
        total_subs = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM clips")
        total_clips = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM clips WHERE broadcast = 1")
        clips_broadcast = cursor.fetchone()[0]

        cursor.execute("SELECT SUM(success) FROM broadcasts")
        total_sent = cursor.fetchone()[0] or 0

        cursor.execute("SELECT SUM(failed) FROM broadcasts")
        total_failed = cursor.fetchone()[0] or 0

        cursor.execute("SELECT COUNT(*) FROM subscribers WHERE joined_at >= datetime('now', '-7 days')")
        new_this_week = cursor.fetchone()[0]

        conn.close()

        msg = f"""📊 *Analytics*

👥 *Subscribers:* {total_subs}
   └ +{new_this_week} this week

🎬 *Clips:* {total_clips} ({clips_broadcast} sent)

📤 *Delivery:* {total_sent} ✓ | {total_failed} ✗"""

        await query.message.edit_text(msg, parse_mode="Markdown", reply_markup=admin_menu())

    elif data == "clip_history":
        conn = sqlite3.connect("bot.db")
        cursor = conn.cursor()
        cursor.execute("SELECT id, title, fmt, created_at, broadcast FROM clips ORDER BY id DESC LIMIT 10")
        clips = cursor.fetchall()
        conn.close()

        if not clips:
            await query.message.edit_text(
                "📋 *No clips yet.*",
                parse_mode="Markdown",
                reply_markup=admin_menu()
            )
            return

        lines = ["*📋 Clip History:*\n"]
        for c in clips:
            status = "✅" if c[4] else "⏳"
            lines.append(f"{status} #{c[0]} — {c[1][:20] or 'Untitled'} — {c[2].upper()} — {c[3][:10]}")

        await query.message.edit_text("\n".join(lines), parse_mode="Markdown", reply_markup=admin_menu())

    elif data == "browse_clips":
        keyboard = build_user_clips_menu()
        if keyboard:
            await query.message.edit_text(
                "🎬 *Available Clips*\n\nTap a clip to get it sent to your chat:",
                parse_mode="Markdown",
                reply_markup=keyboard
            )
        else:
            await query.message.edit_text(
                "📭 *No clips available yet.*\n\nCheck back later!",
                parse_mode="Markdown",
                reply_markup=user_menu()
            )

    elif data == "subscribe":
        chat_id = query.from_user.id
        username = query.from_user.username or "unknown"
        conn = sqlite3.connect("bot.db")
        cursor = conn.cursor()
        cursor.execute("SELECT chat_id FROM subscribers WHERE chat_id = ?", (chat_id,))
        existing = cursor.fetchone()
        if existing:
            conn.close()
            await query.message.edit_text(
                "✅ *You're already subscribed!*",
                parse_mode="Markdown",
                reply_markup=user_menu()
            )
            return
        cursor.execute(
            "INSERT INTO subscribers (chat_id, username) VALUES (?, ?)",
            (chat_id, username)
        )
        conn.commit()
        conn.close()

        try:
            await context.bot.send_message(
                chat_id=ADMIN_ID,
                text=f"🔔 *New Subscriber!*\n\n👤 @{username} just joined.",
                parse_mode="Markdown"
            )
        except Exception:
            pass

        await query.message.edit_text(
            "✅ *You're subscribed!*\n\nYou'll receive clips when they're sent out.",
            parse_mode="Markdown",
            reply_markup=user_menu()
        )

    elif data == "unsubscribe":
        chat_id = query.from_user.id
        conn = sqlite3.connect("bot.db")
        cursor = conn.cursor()
        cursor.execute("DELETE FROM subscribers WHERE chat_id = ?", (chat_id,))
        conn.commit()
        removed = cursor.rowcount > 0
        conn.close()

        if removed:
            await query.message.edit_text(
                "❌ *You've been unsubscribed.*",
                parse_mode="Markdown",
                reply_markup=user_menu()
            )
        else:
            await query.message.edit_text(
                "You weren't subscribed.",
                reply_markup=user_menu()
            )

    elif data == "help":
        await help_command(update, context)

    elif data == "about":
        await query.message.edit_text(
            "🎬 *Clip Pipeline Bot*\n\n"
            "Get short audio and video clips delivered straight to your chat.\n\n"
            "📌 *Subscribe* to receive clips automatically when they're released\n"
            "📌 *Browse Clips* to get any available clip sent to you now\n"
            "📌 *Unsubscribe* anytime\n\n"
            "Built with ❤️ for seamless clip delivery.",
            parse_mode="Markdown",
            reply_markup=user_menu()
        )

    elif data == "add_prophecy":
        context.user_data["prophecy_data"] = {}
        context.user_data["state"] = PROPHECY_TITLE
        await query.message.reply_text(
            "📜 *Add Prophecy — Step 1/4*\n\n"
            "Send the *title* of this prophecy.\n\n"
            "Example: `The Season of Breakthrough`",
            parse_mode="Markdown"
        )

    elif data == "add_testimony":
        context.user_data["testimony_data"] = {}
        context.user_data["state"] = TESTIMONY_TITLE
        await query.message.reply_text(
            "🗣 *Share Testimony — Step 1/2*\n\n"
            "Give your testimony a *title*.\n\n"
            "Example: `Healed from Chronic Pain`",
            parse_mode="Markdown"
        )

    elif data == "my_bank":
        uid = query.from_user.id
        conn = sqlite3.connect("bot.db")
        rows = conn.execute(
            "SELECT * FROM user_prophecies WHERE user_id = ? ORDER BY created_at DESC LIMIT 10",
            (uid,)
        ).fetchall()
        conn.close()
        if not rows:
            await query.message.reply_text(
                "📓 *Your Prophecy Bank is empty.*\n\n"
                "Save prophecies on the web dashboard, or send a prophecy to me and I'll add it here soon!",
                parse_mode="Markdown",
                reply_markup=user_menu()
            )
            return
        lines = ["📓 *My Prophecy Bank (Last 10)*\n"]
        for r in rows:
            star = "⭐ " if r[8] else ""  # is_favorite
            title = r[2] or "Untitled"
            date = (r[10] or "")[:10] if len(r) > 10 else ""
            lines.append(f"\n{star}*{title}*")
            if date:
                lines[-1] += f" — {date}"
            if r[3]:  # content_text
                preview = r[3][:80]
                lines.append(f"  `{preview}{'...' if len(r[3]) > 80 else ''}`")
            elif r[4]:  # audio_file_id
                lines.append(f"  🎙️ Audio")
            elif r[6]:  # video_file_id
                lines.append(f"  🎞️ Video")
        lines.append("\nManage your bank at sharestill.paperlinkos.site/bank")
        await query.message.reply_text(
            "\n".join(lines),
            parse_mode="Markdown",
            reply_markup=user_menu()
        )


async def message_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    state = context.user_data.get("state")

    if state == PROPHECY_TITLE:
        text = (update.message.text or "").strip()
        if not text:
            await update.message.reply_text("Please send a title (text only).")
            return
        context.user_data["prophecy_data"]["title"] = text
        context.user_data["state"] = PROPHECY_MONTH
        await update.message.reply_text(
            "📜 *Step 2/4 — Month*\n\n"
            "Which month does this prophecy relate to?\n"
            "Example: `January 2026`\n\n"
            "Or send `-` to skip.",
            parse_mode="Markdown"
        )

    elif state == PROPHECY_MONTH:
        text = (update.message.text or "").strip()
        data = context.user_data["prophecy_data"]
        data["month"] = "" if text == "-" else text
        context.user_data["state"] = PROPHECY_PROGRAM
        await update.message.reply_text(
            "📜 *Step 3/4 — Program*\n\n"
            "Which program or series?\n"
            "Example: `Thy Kingdom Come`\n\n"
            "Or send `-` to skip.",
            parse_mode="Markdown"
        )

    elif state == PROPHECY_PROGRAM:
        text = (update.message.text or "").strip()
        data = context.user_data["prophecy_data"]
        data["program"] = "" if text == "-" else text
        context.user_data["state"] = PROPHECY_CONTENT
        await update.message.reply_text(
            "📜 *Step 4/4 — Content*\n\n"
            "Send an *audio file, video file, voice note*, or type the *prophecy text*.\n\n"
            "I'll save it with the details you provided.",
            parse_mode="Markdown"
        )

    elif state == PROPHECY_CONTENT:
        context.user_data["state"] = None
        msg = update.message
        data = context.user_data.get("prophecy_data") or {}
        audio_file_id = ""
        video_file_id = ""
        content_text = ""

        if msg.audio:
            audio_file_id = msg.audio.file_id
        elif msg.voice:
            audio_file_id = msg.voice.file_id
        elif msg.video:
            video_file_id = msg.video.file_id
        elif msg.document:
            mime = (msg.document.mime_type or "").lower()
            if "audio" in mime:
                audio_file_id = msg.document.file_id
            elif "video" in mime:
                video_file_id = msg.document.file_id
            else:
                await msg.reply_text("Unsupported file type. Send audio, video, or text.")
                return
        elif msg.text:
            content_text = msg.text.strip()
        elif msg.caption:
            content_text = msg.caption.strip()
        else:
            await msg.reply_text("Please send audio, video, or type the prophecy text.")
            return

        conn = sqlite3.connect("bot.db")
        conn.execute(
            """INSERT INTO prophecy_clips
               (title, content_text, audio_file_id, video_file_id, month, program, source, is_active)
               VALUES (?, ?, ?, ?, ?, ?, 'telegram', 1)""",
            (data.get("title", "Untitled"), content_text,
             audio_file_id, video_file_id,
             data.get("month", ""), data.get("program", ""))
        )
        conn.commit()
        conn.close()

        await msg.reply_text(
            "✅ *Prophecy saved!*\n\n"
            f"📌 *{data.get('title', 'Untitled')}*\n"
            f"{'📅 ' + data['month'] if data.get('month') else ''}"
            f"{' · 📖 ' + data['program'] if data.get('program') else ''}\n\n"
            "You can manage it on the web dashboard.",
            parse_mode="Markdown",
            reply_markup=admin_menu()
        )
        context.user_data["prophecy_data"] = {}

    elif state == TESTIMONY_TITLE:
        text = (update.message.text or "").strip()
        if not text:
            await update.message.reply_text("Please send a title (text only).")
            return
        context.user_data["testimony_data"]["title"] = text
        context.user_data["state"] = TESTIMONY_CONTENT
        await update.message.reply_text(
            "🗣 *Step 2/2 — Your Testimony*\n\n"
            "Now share what God has done! Send a *text message* with your testimony.\n\n"
            "Example: `I was healed of... and I want to give God all the glory!`",
            parse_mode="Markdown"
        )

    elif state == TESTIMONY_CONTENT:
        context.user_data["state"] = None
        msg = update.message
        data = context.user_data.get("testimony_data") or {}
        content = (msg.text or "").strip()
        if not content:
            await update.message.reply_text("Please send your testimony as text.")
            return

        conn = sqlite3.connect("bot.db")
        c = conn.cursor()
        c.execute(
            """INSERT INTO testimonies (user_id, user_name, title, content, source)
               VALUES (?, ?, ?, ?, 'telegram')""",
            (update.effective_user.id,
             update.effective_user.full_name or update.effective_user.username or "",
             data.get("title", ""), content)
        )
        conn.commit()
        conn.close()

        await update.message.reply_text(
            "✅ *Testimony submitted!*\n\n"
            f"🗣 *{data.get('title', 'Untitled')}*\n\n"
            "It will be reviewed and may be featured on the public page.\n"
            "Thank you for sharing! 🙏",
            parse_mode="Markdown",
            reply_markup=user_menu()
        )
        context.user_data["testimony_data"] = {}

    elif state == "cut":
        context.user_data["state"] = None
        await handle_cut_input(update, context)
    elif state == WAITING_FOR_DOWNLOAD:
        context.user_data["state"] = None
        await handle_download_input(update, context)
    elif state == WAITING_FOR_CONVERT:
        context.user_data["state"] = None
        await handle_convert_file(update, context)
    elif state == WAITING_FOR_SCHEDULE:
        context.user_data["state"] = None
        await handle_schedule_input(update, context)
    elif state == "broadcast_msg":
        if update.effective_user.id != ADMIN_ID:
            return
        context.user_data["state"] = None
        message_text = update.message.text

        conn = sqlite3.connect("bot.db")
        cursor = conn.cursor()
        cursor.execute("SELECT chat_id FROM subscribers")
        subscribers = cursor.fetchall()
        conn.close()

        if not subscribers:
            await update.message.reply_text(
                "❌ *No subscribers yet.*",
                parse_mode="Markdown",
                reply_markup=admin_menu()
            )
            return

        status_msg = await update.message.reply_text(
            f"📤 Sending to {len(subscribers)} subscribers..."
        )

        success = 0
        failed = 0
        for (chat_id,) in subscribers:
            try:
                await context.bot.send_message(chat_id=chat_id, text=message_text, parse_mode="Markdown")
                success += 1
            except Exception:
                failed += 1

        await status_msg.edit_text(
            f"✅ *Message sent!*\n\n✔️ Delivered: {success}\n❌ Failed: {failed}",
            parse_mode="Markdown",
            reply_markup=admin_menu()
        )
    else:
        if update.effective_user.id == ADMIN_ID:
            await update.message.reply_text(
                "Use the menu below:",
                reply_markup=admin_menu()
            )
        else:
            await update.message.reply_text(
                "Use the menu below:",
                reply_markup=user_menu()
            )


async def prophecy_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    conn = sqlite3.connect("bot.db")
    cursor = conn.cursor()

    cursor.execute("SELECT id, telegram_id FROM users WHERE telegram_id = ?", (chat_id,))
    user = cursor.fetchone()

    if not user:
        cursor.execute("SELECT id, title FROM prophecy_clips WHERE is_active = 1 ORDER BY created_at DESC LIMIT 10")
        clips = cursor.fetchall()
        conn.close()

        if not clips:
            await update.message.reply_text(
                "🕊️ *Prophecy Feed*\n\nNo prophecies available yet.\n\n"
                "Create an account on the dashboard to receive auto-delivery: "
                "https://sharestill.paperlinkos.site/login",
                parse_mode="Markdown"
            )
            return

        lines = ["🕊️ *Prophecy Feed*\n"]
        for c in clips:
            lines.append(f"• *{c[1]}*")
        lines.append("\nCreate an account at https://sharestill.paperlinkos.site/login to get daily delivery!")
        await update.message.reply_text("\n".join(lines), parse_mode="Markdown")
        return

    uid = user[0]
    await update.message.reply_text(
        "🕊️ *Prophecy Settings*\n\n"
        "You're opted in for prophecy delivery!\n\n"
        "Manage your preferences on the dashboard:\n"
        "https://sharestill.paperlinkos.site/dashboard\n\n"
        "Use /prophecy to see this menu again.",
        parse_mode="Markdown"
    )
    conn.close()


if __name__ == "__main__":
    init_db()
    app = (
        ApplicationBuilder()
        .token(BOT_TOKEN)
        .post_init(on_startup)
        .build()
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("cancel", cancel))
    app.add_handler(CommandHandler("subscribe", handle_subscribe))
    app.add_handler(CommandHandler("unsubscribe", handle_unsubscribe))
    app.add_handler(CommandHandler("clips", handle_clips))
    app.add_handler(CommandHandler("stats", handle_stats))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("prophecy", prophecy_command))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_router))
    app.add_handler(MessageHandler(
        (filters.VIDEO | filters.AUDIO | filters.Document.ALL | filters.VOICE) & ~filters.COMMAND,
        message_router
    ))

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.create_task(process_queue(app))
    loop.create_task(check_scheduled(app))
    loop.create_task(auto_deliver_prophecies(app))

    print("Bot running...")
    app.run_polling()