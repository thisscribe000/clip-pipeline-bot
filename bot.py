import os
import sqlite3
import subprocess
import uuid
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID"))


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
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            broadcast INTEGER DEFAULT 0
        )
    """)
    conn.commit()
    conn.close()


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Bot is alive.")


async def subscribe(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    username = update.effective_user.username or "unknown"

    conn = sqlite3.connect("bot.db")
    cursor = conn.cursor()

    try:
        cursor.execute(
            "INSERT OR IGNORE INTO subscribers (chat_id, username) VALUES (?, ?)",
            (chat_id, username)
        )
        conn.commit()
        if cursor.rowcount > 0:
            await update.message.reply_text(
                "You're subscribed! You'll receive clips when they're sent out."
            )
        else:
            await update.message.reply_text("You're already subscribed.")
    finally:
        conn.close()


async def unsubscribe(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id

    conn = sqlite3.connect("bot.db")
    cursor = conn.cursor()

    try:
        cursor.execute("DELETE FROM subscribers WHERE chat_id = ?", (chat_id,))
        conn.commit()
        if cursor.rowcount > 0:
            await update.message.reply_text("You've been unsubscribed.")
        else:
            await update.message.reply_text("You weren't subscribed.")
    finally:
        conn.close()


async def cut(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("Unauthorized.")
        return

    args = context.args
    if len(args) < 4:
        await update.message.reply_text(
            "Usage: /cut [url] [start HH:MM:SS] [end HH:MM:SS] [mp3 or mp4]"
        )
        return

    url, start, end, fmt = args[0], args[1], args[2], args[3]

    status = await update.message.reply_text("⏳ Starting...")

    try:
        await status.edit_text("📥 Downloading video...")
        os.makedirs("downloads", exist_ok=True)
        unique_id = str(uuid.uuid4())[:8]
        raw_path = f"downloads/raw_{unique_id}.%(ext)s"
        output_path = f"downloads/clip_{unique_id}"

        subprocess.run([
            "yt-dlp",
            "-f", "bestvideo+bestaudio/best",
            "--merge-output-format", "mp4",
            "-o", raw_path,
            url
        ], check=True)

        await status.edit_text("✂️ Cutting clip...")
        raw_file = next(f for f in os.listdir("downloads") if f.startswith(f"raw_{unique_id}"))
        raw_full = f"downloads/{raw_file}"

        if fmt == "mp3":
            final_path = f"{output_path}.mp3"
            subprocess.run([
                "ffmpeg", "-i", raw_full,
                "-ss", start, "-to", end,
                "-q:a", "0", "-map", "a",
                final_path
            ], check=True)
        else:
            final_path = f"{output_path}.mp4"
            subprocess.run([
                "ffmpeg", "-i", raw_full,
                "-ss", start, "-to", end,
                "-c", "copy",
                final_path
            ], check=True)

        os.remove(raw_full)

        await status.edit_text("📤 Uploading to Telegram...")

        with open(final_path, "rb") as f:
            if fmt == "mp3":
                sent = await update.message.reply_audio(f)
                file_id = sent.audio.file_id
            else:
                sent = await update.message.reply_video(f)
                file_id = sent.video.file_id

        conn = sqlite3.connect("bot.db")
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO clips (file_id, fmt) VALUES (?, ?)",
            (file_id, fmt)
        )
        clip_id = cursor.lastrowid
        conn.commit()
        conn.close()

        await status.edit_text(
            f"✅ Done! Clip saved.\n\nTo broadcast to all subscribers:\n/broadcast {clip_id}",
            parse_mode="Markdown"
        )

    except Exception as e:
        await status.edit_text(f"❌ Something went wrong:\n{str(e)}")


async def broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("Unauthorized.")
        return

    if not context.args:
        await update.message.reply_text("Usage: /broadcast [clip_id]")
        return

    clip_id = int(context.args[0])

    conn = sqlite3.connect("bot.db")
    cursor = conn.cursor()
    cursor.execute("SELECT file_id, fmt FROM clips WHERE id = ?", (clip_id,))
    clip = cursor.fetchone()

    if not clip:
        await update.message.reply_text("Clip not found.")
        conn.close()
        return

    file_id, fmt = clip

    cursor.execute("SELECT chat_id FROM subscribers")
    subscribers = cursor.fetchall()

    if not subscribers:
        await update.message.reply_text("No subscribers yet.")
        conn.close()
        return

    status = await update.message.reply_text(f"📡 Broadcasting to {len(subscribers)} subscribers...")

    success = 0
    failed = 0

    for (chat_id,) in subscribers:
        try:
            if fmt == "mp3":
                await context.bot.send_audio(chat_id=chat_id, audio=file_id)
            else:
                await context.bot.send_video(chat_id=chat_id, video=file_id)
            success += 1
        except Exception:
            failed += 1

    cursor.execute("UPDATE clips SET broadcast = 1 WHERE id = ?", (clip_id,))
    conn.commit()
    conn.close()

    await status.edit_text(
        f"✅ Broadcast complete.\n\n✔️ Sent: {success}\n❌ Failed: {failed}"
    )


if __name__ == "__main__":
    init_db()
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("cut", cut))
    app.add_handler(CommandHandler("subscribe", subscribe))
    app.add_handler(CommandHandler("unsubscribe", unsubscribe))
    app.add_handler(CommandHandler("broadcast", broadcast))
    print("Bot running...")
    app.run_polling()