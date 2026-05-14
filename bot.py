import os
import re
import uuid
import sqlite3
import subprocess
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, BotCommand
from telegram.ext import (
    ApplicationBuilder, CommandHandler, CallbackQueryHandler,
    ContextTypes, MessageHandler, filters
)

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID"))


async def on_startup(app):
    await app.bot.set_my_commands([
        BotCommand("start", "Open the main menu"),
        BotCommand("clips", "Browse or broadcast clips"),
        BotCommand("subscribe", "Subscribe to receive clips"),
        BotCommand("unsubscribe", "Unsubscribe from clips"),
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
    conn.commit()
    conn.close()


def admin_menu():
    keyboard = [
        [InlineKeyboardButton("✂️ Cut New Clip", callback_data="cut_new")],
        [InlineKeyboardButton("📡 Broadcast Clip", callback_data="broadcast_menu")],
        [InlineKeyboardButton("👥 Subscribers", callback_data="view_subs")],
        [InlineKeyboardButton("📬 Send Message", callback_data="send_message")],
        [InlineKeyboardButton("📊 Analytics", callback_data="analytics")],
        [InlineKeyboardButton("📋 Clip History", callback_data="clip_history")],
    ]
    return InlineKeyboardMarkup(keyboard)


def user_menu():
    keyboard = [
        [InlineKeyboardButton("🎬 Browse Clips", callback_data="browse_clips")],
        [InlineKeyboardButton("✅ Subscribe", callback_data="subscribe")],
        [InlineKeyboardButton("ℹ️ About", callback_data="about")],
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
            "Format: `[url] [start HH:MM:SS] [end HH:MM:SS] [mp3 or mp4]`\n\nExample:\n`https://youtube.com/watch?v=xxx 00:10:30 00:15:00 mp3`",
            parse_mode="Markdown",
            reply_markup=admin_menu()
        )
        context.user_data["state"] = "cut"
        return

    url, start, end, fmt = parts[0], parts[1], parts[2], parts[3]

    if fmt not in ("mp3", "mp4"):
        await update.message.reply_text("Format must be `mp3` or `mp4`. Try again or /cancel", parse_mode="Markdown")
        context.user_data["state"] = "cut"
        return

    title = " ".join(parts[4:]) if len(parts) > 4 else f"Clip"

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
                sent = await update.message.reply_audio(f, title=title)
                file_id = sent.audio.file_id
            else:
                sent = await update.message.reply_video(f, title=title)
                file_id = sent.video.file_id

        os.remove(final_path)

        conn = sqlite3.connect("bot.db")
        cursor = conn.cursor()
        cursor.execute("INSERT INTO clips (file_id, title, fmt) VALUES (?, ?, ?)", (file_id, title, fmt))
        clip_id = cursor.lastrowid
        conn.commit()
        conn.close()

        await status.edit_text(
            f"✅ *Clip saved!*\n\n📌 Title: {title}\n📎 Format: {fmt.upper()}\n\nClick a clip below to broadcast it.",
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

    status_text = f"📡 Broadcasting to {len(subscribers)} subscribers..."
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
    cursor.execute("INSERT INTO broadcasts (clip_id, success, failed) VALUES (?, ?, ?)", (clip_id, success, failed))
    conn.commit()
    conn.close()

    msg = f"✅ *Broadcast complete.*\n\n✔️ Sent: {success}\n❌ Failed: {failed}"
    await status_msg.edit_text(msg, parse_mode="Markdown", reply_markup=admin_menu())
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
            "`[url] [start HH:MM:SS] [end HH:MM:SS] [mp3 or mp4] [title (optional)]`\n\n"
            "Example:\n`https://youtube.com/watch?v=xxx 00:10:30 00:15:00 mp3 Amazing Sermon`",
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

    elif data.startswith("bc_"):
        clip_id = int(data.split("_")[1])
        await query.message.edit_text(f"📡 Broadcasting clip #{clip_id}...")
        await do_broadcast_clip(clip_id, context)

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
            if fmt == "mp3":
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
        await query.message.edit_text(
            "✅ *You're subscribed!*\n\nYou'll receive clips when they're sent out.",
            parse_mode="Markdown",
            reply_markup=user_menu()
        )
        conn.commit()
        added = cursor.rowcount > 0
        conn.close()

        if added:
            await query.message.edit_text(
                "✅ *You're subscribed!*\n\nYou'll receive clips when they're sent out.\n\nUse the menu below:",
                parse_mode="Markdown",
                reply_markup=user_menu()
            )
        else:
            await query.message.edit_text(
                "✅ *You're already subscribed!*",
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


async def message_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    state = context.user_data.get("state")

    if state == "cut":
        context.user_data["state"] = None
        await handle_cut_input(update, context)
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
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_router))

    print("Bot running...")
    app.run_polling()