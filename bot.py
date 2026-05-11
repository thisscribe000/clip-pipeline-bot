import os
import re
import uuid
import sqlite3
import subprocess
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, BotCommand, MenuButtonCommands
from telegram.ext import (
    ApplicationBuilder, CommandHandler, CallbackQueryHandler,
    ContextTypes, MessageHandler, filters
)

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID"))


async def on_startup(app):
    commands = [
        BotCommand("start", "Open the main menu"),
        BotCommand("clips", "List clips to broadcast"),
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


async def download_with_progress(url: str, raw_path: str, status_msg):
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
                    await status_msg.edit_text(f"📥 Downloading...\n\n{bar} {bucket}%")
                except Exception:
                    pass

    process.wait()
    if process.returncode != 0:
        raise Exception("yt-dlp failed during download.")


async def handle_cut_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return

    text = update.message.text.strip()
    parts = text.split()

    if len(parts) < 4:
        await update.message.reply_text(
            "Format: [url] [start HH:MM:SS] [end HH:MM:SS] [mp3 or mp4]\n\nTry again or /cancel",
            reply_markup=admin_menu()
        )
        context.user_data["state"] = "cut"
        return

    url, start, end, fmt = parts[0], parts[1], parts[2], parts[3]

    if fmt not in ("mp3", "mp4"):
        await update.message.reply_text("Format must be mp3 or mp4. Try again or /cancel")
        context.user_data["state"] = "cut"
        return

    status = await update.message.reply_text("⏳ Starting...")

    os.makedirs("downloads", exist_ok=True)
    unique_id = str(uuid.uuid4())[:8]
    raw_path = f"downloads/raw_{unique_id}.%(ext)s"
    output_path = f"downloads/clip_{unique_id}"

    try:
        await download_with_progress(url, raw_path, status)

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
        cursor.execute("INSERT INTO clips (file_id, fmt) VALUES (?, ?)", (file_id, fmt))
        clip_id = cursor.lastrowid
        conn.commit()
        conn.close()

        await status.edit_text(
            f"✅ Clip saved! ID: *{clip_id}*\n\nClick a clip below to broadcast it.",
            parse_mode="Markdown",
            reply_markup=build_broadcast_menu()
        )

    except Exception as e:
        await status.edit_text(f"❌ Error:\n{str(e)}\n\nUse /start to return to menu.")
        await update.message.reply_text("Back to menu:", reply_markup=admin_menu())

    context.user_data["state"] = None


def build_broadcast_menu():
    conn = sqlite3.connect("bot.db")
    cursor = conn.cursor()
    cursor.execute("SELECT id, fmt, broadcast FROM clips ORDER BY id DESC LIMIT 9")
    clips = cursor.fetchall()
    conn.close()

    rows = []
    for c in clips:
        clip_id, fmt, broadcast = c[0], c[1], c[2]
        icon = "📤" if broadcast else "📡"
        label = f"{icon} Clip #{clip_id} ({fmt.upper()})"
        rows.append([InlineKeyboardButton(label, callback_data=f"bc_{clip_id}")])

    rows.append([InlineKeyboardButton("🔙 Back to Menu", callback_data="back_to_menu")])
    return InlineKeyboardMarkup(rows)


async def do_broadcast_clip(clip_id, context):
    conn = sqlite3.connect("bot.db")
    cursor = conn.cursor()
    cursor.execute("SELECT file_id, fmt FROM clips WHERE id = ?", (clip_id,))
    clip = cursor.fetchone()

    if not clip:
        conn.close()
        return "❌ Clip not found."

    file_id, fmt = clip

    cursor.execute("SELECT chat_id FROM subscribers")
    subscribers = cursor.fetchall()
    conn.close()

    if not subscribers:
        return "❌ No subscribers yet."

    status_text = f"📡 Broadcasting clip #{clip_id} to {len(subscribers)} subscribers..."
    status_msg = await context.bot.send_message(
        chat_id=ADMIN_ID, text=status_text
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

    msg = f"✅ Broadcast complete.\n\n✔️ Sent: {success}\n❌ Failed: {failed}"
    await status_msg.edit_text(msg, reply_markup=admin_menu())
    return msg


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
    cursor.execute(
        "INSERT OR IGNORE INTO subscribers (chat_id, username) VALUES (?, ?)",
        (chat_id, username)
    )
    conn.commit()
    added = cursor.rowcount > 0
    conn.close()

    if added:
        await update.message.reply_text(
            "✅ You're subscribed! You'll receive clips when they're sent out.",
            reply_markup=user_menu()
        )
    else:
        await update.message.reply_text(
            "You're already subscribed. ✅",
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
            "❌ You've been unsubscribed.",
            reply_markup=user_menu()
        )
    else:
        await update.message.reply_text(
            "You weren't subscribed.",
            reply_markup=user_menu()
        )


async def handle_clips(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("Unauthorized.")
        return

    await update.message.reply_text(
        "📡 *Select a clip to broadcast:*",
        parse_mode="Markdown",
        reply_markup=build_broadcast_menu()
    )


async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "cut_new":
        await query.message.reply_text(
            "Send the clip details in this format:\n\n"
            "`[url] [start HH:MM:SS] [end HH:MM:SS] [mp3 or mp4]`\n\n"
            "Example:\n`https://youtube.com/watch?v=xxx 00:10:30 00:15:00 mp3`",
            parse_mode="Markdown",
            reply_markup=admin_menu()
        )
        context.user_data["state"] = "cut"

    elif data == "broadcast_menu":
        await query.message.reply_text(
            "📡 *Select a clip to broadcast:*",
            parse_mode="Markdown",
            reply_markup=build_broadcast_menu()
        )

    elif data == "back_to_menu":
        if update.effective_user.id == ADMIN_ID:
            await query.message.edit_text(
                "👋 Back to menu:", reply_markup=admin_menu()
            )
        else:
            await query.message.edit_text(
                "👋 Back to menu:", reply_markup=user_menu()
            )

    elif data.startswith("bc_"):
        clip_id = int(data.split("_")[1])
        await query.message.edit_text(f"📡 Broadcasting clip #{clip_id}...")
        await do_broadcast_clip(clip_id, context)

    elif data == "view_subs":
        conn = sqlite3.connect("bot.db")
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM subscribers")
        count = cursor.fetchone()[0]
        cursor.execute("SELECT username, joined_at FROM subscribers ORDER BY joined_at DESC LIMIT 10")
        recent = cursor.fetchall()
        conn.close()

        if count == 0:
            await query.message.reply_text(
                "👥 No subscribers yet.\n\nShare the bot with your audience!",
                reply_markup=admin_menu()
            )
            return

        lines = [f"👥 *Total Subscribers: {count}*\n"]
        if recent:
            lines.append("*Recent:*")
            for r in recent:
                lines.append(f"  @{r[0]} — {r[1][:10]}")
        await query.message.reply_text("\n".join(lines), parse_mode="Markdown")

    elif data == "clip_history":
        conn = sqlite3.connect("bot.db")
        cursor = conn.cursor()
        cursor.execute("SELECT id, fmt, created_at, broadcast FROM clips ORDER BY id DESC LIMIT 10")
        clips = cursor.fetchall()
        conn.close()

        if not clips:
            await query.message.reply_text(
                "📋 No clips yet.", reply_markup=admin_menu()
            )
            return

        lines = ["*📋 Clip History:*\n"]
        for c in clips:
            status = "✅" if c[3] else "⏳"
            lines.append(f"{status} #{c[0]} — {c[1].upper()} — {c[2][:16]}")

        lines.append("\nGo to Broadcast to send a clip:")
        await query.message.reply_text(
            "\n".join(lines), parse_mode="Markdown", reply_markup=admin_menu()
        )

    elif data == "subscribe":
        chat_id = query.message.chat_id
        username = query.from_user.username or "unknown"
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
            await query.message.edit_text(
                "✅ You're subscribed!\n\nYou'll receive clips when they're sent out.\n\nUse the menu below:",
                reply_markup=user_menu()
            )
        else:
            await query.message.edit_text(
                "✅ You're already subscribed!\n\nUse the menu below:",
                reply_markup=user_menu()
            )

    elif data == "unsubscribe":
        chat_id = query.message.chat_id
        conn = sqlite3.connect("bot.db")
        cursor = conn.cursor()
        cursor.execute("DELETE FROM subscribers WHERE chat_id = ?", (chat_id,))
        conn.commit()
        removed = cursor.rowcount > 0
        conn.close()

        if removed:
            await query.message.edit_text(
                "❌ You've been unsubscribed.\n\nUse the menu below:",
                reply_markup=user_menu()
            )
        else:
            await query.message.edit_text(
                "You weren't subscribed.\n\nUse the menu below:",
                reply_markup=user_menu()
            )

    elif data == "about":
        await query.message.edit_text(
            "🎬 *Clip Pipeline Bot*\n\n"
            "This bot delivers short audio and video clips directly to you.\n\n"
            "📌 Subscribe to receive clips automatically when they're released.\n"
            "📌 Unsubscribe anytime if you no longer want to receive them.\n\n"
            "Contact the admin if you have questions.",
            parse_mode="Markdown",
            reply_markup=user_menu()
        )


async def message_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    state = context.user_data.get("state")

    if state == "cut":
        context.user_data["state"] = None
        await handle_cut_input(update, context)
    else:
        if update.effective_user.id == ADMIN_ID:
            await update.message.reply_text(
                "Use the menu below:", reply_markup=admin_menu()
            )
        else:
            await update.message.reply_text(
                "Use the menu below:", reply_markup=user_menu()
            )


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
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_router))

    print("Bot running...")
    app.run_polling()