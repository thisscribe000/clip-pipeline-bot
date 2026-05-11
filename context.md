# clip-pipeline-bot — Dev Context

A Telegram bot that downloads YouTube videos, cuts clips by timestamp using ffmpeg, broadcasts to subscribers, and has a web dashboard.

## Stack
- **Runtime**: Python 3, venv
- **Bot**: python-telegram-bot (v21+)
- **Download**: yt-dlp
- **Video processing**: ffmpeg
- **Database**: SQLite (bot.db — shared between bot and dashboard)
- **Dashboard**: Flask + HTML/CSS (dark-themed)
- **Env vars**: python-dotenv

## Architecture

```
bot.py (Telegram bot)  ← shares →  bot.db (SQLite)
                                        ↑
                                  dashboard/app.py (Flask)
                                        ↑
                                  dashboard/templates/index.html
```

Both bot.py and dashboard/app.py read/write the same `bot.db` file. The bot runs on port 5001 (polling), dashboard on port 5000 (HTTP).

## Commands (registered with Telegram via set_my_commands)

| Command | Who | Description |
|---|---|---|
| `/start` | anyone | Bot alive — shows admin or user menu |
| `/clips` | admin | Lists all clips with clickable broadcast buttons |
| `/subscribe` | anyone | Subscribe to receive clips |
| `/unsubscribe` | anyone | Unsubscribe from clips |
| `/cancel` | anyone | Cancel current action |

## Bot Flow

### Cutting a clip (admin)
```
Admin: /start → menu
Admin: "✂️ Cut New Clip" button
Admin: sends "[url] [start HH:MM:SS] [end HH:MM:SS] [mp3 or mp4]"
  ├─ yt-dlp downloads full video (progress bar: ████░░░░░░ 40%)
  ├─ ffmpeg cuts clip
  ├─ upload to Telegram → get file_id
  ├─ save file_id + fmt to clips table
  └─ show clip with "Broadcast" buttons
```

### Broadcasting (admin)
```
Admin: "📡 Broadcast Clip" button → shows clips as inline buttons
Admin: clicks "📡 Clip #3 (MP4)" button
  ├─ bot fetches file_id + subscribers from DB
  ├─ loops through all subscribers
  ├─ sends clip via Telegram API (no re-upload)
  └─ marks clip as broadcast=1
```

Or via dashboard at http://localhost:5000 (or sharestill.paperlinkos.site):
- View stats, subscribers, clips table
- Click BROADCAST button per clip
- Auto-refreshes every 30s

### Subscribing (users)
```
User: /start → user menu
User: clicks "✅ Subscribe" button or sends /subscribe
  → added to subscribers table
User: /unsubscribe or clicks button → removed
```

## Database Schema

**subscribers**: chat_id (PK), username, joined_at

**clips**: id (PK), file_id, title, fmt, created_at, broadcast (0/1)

## File Structure

```
clip-pipeline-bot/
├── bot.py              # Telegram bot (port 5001 polling)
├── bot.db              # SQLite DB (gitignored — lives on VPS)
├── .env                # BOT_TOKEN, ADMIN_ID (gitignored)
│                       # PORT=5000 (for dashboard)
├── .gitignore
├── venv/               # Python venv (gitignored)
├── downloads/          # Temp video files (gitignored)
└── dashboard/
    ├── app.py          # Flask backend (port 5000)
    └── templates/
        └── index.html  # Dark-themed admin dashboard
```

## VPS Deployment

### Start bot
```bash
cd clip-pipeline-bot
source venv/bin/activate
python bot.py
```

### Start dashboard
```bash
cd clip-pipeline-bot/dashboard
source ../venv/bin/activate
python app.py
# runs on 0.0.0.0:5000
```

### Or use systemd (production)
Create `/etc/systemd/system/clip-bot.service` for auto-restart on crash.

## Progress

- [x] Bot skeleton with /start, /subscribe, /unsubscribe
- [x] /cut command — yt-dlp + ffmpeg pipeline
- [x] Live progress bar during download (█░░░░░░░░░ 40%)
- [x] SQLite subscriber system
- [x] /broadcast command (now clickable inline buttons)
- [x] Bot commands registered via set_my_commands
- [x] Menu button set via set_chat_menu_button
- [x] Flask dashboard with dark theme
- [x] /clips command — list clips with clickable broadcast
- [x] Broadcast clips via inline buttons (no typing IDs)
- [ ] Cleanup temp files after broadcast
- [ ] /stats command — subscriber count, broadcast stats
- [ ] systemd service files for VPS auto-start