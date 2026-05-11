import os
import re
import uuid
import sqlite3
import subprocess
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, BotCommand, MenuButtonCommands
from telegram.ext import (
    ApplicationBuilder, CommandHandler, CallbackQueryHandler,
    ContextTypes, MessageHandler, filters, ConversationHandler
)

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID"))

WAITING_FOR_CUT = 1
WAITING_FOR_BROADCAST_ID = 2


async def on_startup(app):
    commands = [
        BotCommand("start", "Open the main menu"),
        BotCommand("subscribe", "Subscribe to receive clips"),
        BotCommand("unsubscribe", "Unsubscribe from clips"),
        BotCommand("cancel", "Cancel current action"),
    ]
    await app.bot.set_my_commands(commands)
    await app.bot.set_chat_menu_button(menu_button=MenuButtonCommands())
    print("Commands and menu button registered.")


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


def admin_menu():
    keyboard = [
        [InlineKeyboardButton("✂️ Cut New Clip", callback_data="cut_new")],
        [InlineKeyboardButton("📡 Broadcast Clip", callback_data="broadcast_menu")],
        [InlineKeyboardButton("👥 View Subscribers", callback_data="view_subs")],
        [InlineKeyboardButton("📋 Clip History", callback_data="clip_history")],
    ]
    return InlineKeyboardMarkup(keyboard)


def user_menu():
    keyboard = [
        [InlineKeyboardButton("✅ Subscribe", callback_data="subscribe")],
        [InlineKeyboardButton("❌ Unsubscribe", callback_data="unsubscribe")],
        [InlineKeyboardButton("ℹ️ About", callback_data="about")],
    ]
    return InlineKeyboardMarkup(keyboard)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id == ADMIN_ID:
        await update.message.reply_text(
            "👋 Welcome Admin. What would you like to do?",
            reply_markup=admin_menu()
        )
    else:
        await update.message.reply_text(
            "👋 Welcome! Subscribe to receive clips.",
            reply_markup=user_menu()
        )


async def download_with_progress(url: str, raw_path: str, status_msg, context):
    last_reported = -1

    process = subprocess.Popen(
        [
            "yt-dlp",
            "-f", "bestvideo+bestaudio/best",
            "--merge-output-format", "mp4",
            "--newline",
            "-o", raw_path,
            url
        ],
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
                    await status_msg.edit_text(
                        f"📥 Downloading...\n\n{bar} {bucket}%"
                    )
                except Exception:
                    pass

    process.wait()
    if process.returncode != 0:
        raise Exception("yt-dlp failed during download.")


async def handle_cut_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return ConversationHandler.END

    text = update.message.text.strip()
    parts = text.split()

    if len(parts) < 4:
        await update.message.reply_text(
            "Format: [url] [start HH:MM:SS] [end HH:MM:SS] [mp3 or mp4]\n\nTry again or /cancel"
        )
        return WAITING_FOR_CUT

    url, start, end, fmt = parts[0], parts[1], parts[2], parts[3]

    if fmt not in ("mp3", "mp4"):
        await update.message.reply_text("Format must be mp3 or mp4. Try again or /cancel")
        return WAITING_FOR_CUT

    status = await update.message.reply_text("⏳ Starting...")

    os.makedirs("downloads", exist_ok=True)
    unique_id = str(uuid.uuid4())[:8]
    raw_path = f"downloads/raw_{unique_id}.%(ext)s"
    output_path = f"downloads/clip_{unique_id}"

    try:
        await download_with_progress(url, raw_path, status, context)

        await status.edit_text("✂️ Cutting clip...")

        raw_file = next(
            f for f in os.listdir("downloads")
            if f.startswith(f"raw_{unique_id}")
        )
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

        os.remove(final_path)

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
            f"✅ Clip saved! ID: *{clip_id}*\n\nGo to menu to broadcast it.",
            parse_mode="Markdown"
        )

    except Exception as e:
        await status.edit_text(f"❌ Error:\n{str(e)}")

    await update.message.reply_text(
        "Back to menu:", reply_markup=admin_menu()
    )
    return ConversationHandler.END


async def handle_broadcast_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return ConversationHandler.END

    text = update.message.text.strip()

    if not text.isdigit():
        await update.message.reply_text("Please send a valid clip ID number. Try again or /cancel")
        return WAITING_FOR_BROADCAST_ID

    clip_id = int(text)

    conn = sqlite3.connect("bot.db")
    cursor = conn.cursor()
    cursor.execute("SELECT file_id, fmt FROM clips WHERE id = ?", (clip_id,))
    clip = cursor.fetchone()

    if not clip:
        await update.message.reply_text("Clip not found. Try again or /cancel")
        conn.close()
        return WAITING_FOR_BROADCAST_ID

    file_id, fmt = clip

    cursor.execute("SELECT chat_id FROM subscribers")
    subscribers = cursor.fetchall()
    conn.close()

    if not subscribers:
        await update.message.reply_text("No subscribers yet.")
        await update.message.reply_text("Back to menu:", reply_markup=admin_menu())
        return ConversationHandler.END

    status = await update.message.reply_text(
        f"📡 Broadcasting clip {clip_id} to {len(subscribers)} subscribers..."
    )

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

    conn = sqlite3.connect("bot.db")
    cursor = conn.cursor()
    cursor.execute("UPDATE clips SET broadcast = 1 WHERE id = ?", (clip_id,))
    conn.commit()
    conn.close()

    await status.edit_text(
        f"✅ Broadcast complete.\n\n✔️ Sent: {success}\n❌ Failed: {failed}"
    )

    await update.message.reply_text("Back to menu:", reply_markup=admin_menu())
    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["state"] = None
    if update.effective_user.id == ADMIN_ID:
        await update.message.reply_text("Cancelled.", reply_markup=admin_menu())
    else:
        await update.message.reply_text("Cancelled.", reply_markup=user_menu())
    return ConversationHandler.END


async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    user_id = update.effective_user.id

    if data == "cut_new":
        await query.message.reply_text(
            "Send the clip details in this format:\n\n"
            "`[url] [start HH:MM:SS] [end HH:MM:SS] [mp3 or mp4]`\n\n"
            "Example:\n`https://youtube.com/watch?v=xxx 00:10:30 00:15:00 mp3`",
            parse_mode="Markdown"
        )
        context.user_data["state"] = WAITING_FOR_CUT

    elif data == "broadcast_menu":
        conn = sqlite3.connect("bot.db")
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, fmt, created_at, broadcast FROM clips ORDER BY id DESC LIMIT 10"
        )
        clips = cursor.fetchall()
        conn.close()

        if not clips:
            await query.message.reply_text("No clips yet.")
            return

        lines = ["*Recent Clips:*\n"]
        for c in clips:
            status = "✅ Sent" if c[3] else "⏳ Pending"
            lines.append(f"ID {c[0]} — {c[1].upper()} — {status} — {c[2][:10]}")

        lines.append("\nSend the clip ID you want to broadcast:")
        await query.message.reply_text("\n".join(lines), parse_mode="Markdown")
        context.user_data["state"] = WAITING_FOR_BROADCAST_ID

    elif data == "view_subs":
        conn = sqlite3.connect("bot.db")
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM subscribers")
        count = cursor.fetchone()[0]
        cursor.execute("SELECT username, joined_at FROM subscribers ORDER BY joined_at DESC LIMIT 5")
        recent = cursor.fetchall()
        conn.close()

        lines = [f"👥 *Total Subscribers: {count}*\n", "*Recent:*"]
        for r in recent:
            lines.append(f"@{r[0]} — {r[1][:10]}")

        await query.message.reply_text("\n".join(lines), parse_mode="Markdown")

    elif data == "clip_history":
        conn = sqlite3.connect("bot.db")
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, fmt, created_at, broadcast FROM clips ORDER BY id DESC LIMIT 10"
        )
        clips = cursor.fetchall()
        conn.close()

        if not clips:
            await query.message.reply_text("No clips yet.")
            return

        lines = ["*📋 Clip History:*\n"]
        for c in clips:
            status = "✅ Broadcast" if c[3] else "⏳ Not sent"
            lines.append(f"ID {c[0]} — {c[1].upper()} — {status} — {c[2][:10]}")

        await query.message.reply_text("\n".join(lines), parse_mode="Markdown")

    elif data == "subscribe":
        chat_id = update.effective_chat.id
        username = update.effective_user.username or "unknown"
        conn = sqlite3.connect("bot.db")
        cursor = conn.cursor()
        cursor.execute(
            "INSERT OR IGNORE INTO subscribers (chat_id, username) VALUES (?, ?)",
            (chat_id, username)
        )
        conn.commit()
        added = cursor.rowcount > 0
        conn.close()

        if added:
            await query.message.reply_text(
                "✅ You're subscribed! You'll receive clips when they're sent out.",
                reply_markup=user_menu()
            )
        else:
            await query.message.reply_text(
                "You're already subscribed.", reply_markup=user_menu()
            )

    elif data == "unsubscribe":
        chat_id = update.effective_chat.id
        conn = sqlite3.connect("bot.db")
        cursor = conn.cursor()
        cursor.execute("DELETE FROM subscribers WHERE chat_id = ?", (chat_id,))
        conn.commit()
        removed = cursor.rowcount > 0
        conn.close()

        if removed:
            await query.message.reply_text(
                "❌ You've been unsubscribed.", reply_markup=user_menu()
            )
        else:
            await query.message.reply_text(
                "You weren't subscribed.", reply_markup=user_menu()
            )

    elif data == "about":
        await query.message.reply_text(
            "This bot delivers short audio and video clips directly to you.\n\n"
            "Subscribe to get them automatically whenever new ones are released.",
            reply_markup=user_menu()
        )


async def message_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    state = context.user_data.get("state")

    if state == WAITING_FOR_CUT:
        context.user_data["state"] = None
        await handle_cut_input(update, context)
    elif state == WAITING_FOR_BROADCAST_ID:
        context.user_data["state"] = None
        await handle_broadcast_input(update, context)
    else:
        if update.effective_user.id == ADMIN_ID:
            await update.message.reply_text("Use the menu:", reply_markup=admin_menu())
        else:
            await update.message.reply_text("Use the menu:", reply_markup=user_menu())


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
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_router))

    print("Bot running...")
    app.run_polling()