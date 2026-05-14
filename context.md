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

## Commands

| Command | Who | Description |
|---|---|---|
| `/start` | anyone | Shows admin or user menu |
| `/clips` | anyone | Admins: broadcast clips. Users: browse/request clips |
| `/subscribe` | anyone | Subscribe to receive clips |
| `/unsubscribe` | anyone | Unsubscribe from clips |
| `/stats` | admin | View analytics (subscribers, clips, broadcasts) |
| `/cancel` | anyone | Cancel current action |

## User Flows

### Admin
- `✂️ Cut New Clip` — Download video, cut clip, save to Telegram
- `📡 Broadcast Clip` — Send clip to all subscribers
- `👥 Subscribers` — View subscriber list
- `📊 Analytics` — Stats dashboard
- `📋 Clip History` — View all clips with status

### User
- `🎬 Browse Clips` — View available clips, tap to get sent
- `✅ Subscribe` — Get added to broadcast list
- `ℹ️ About` — Bot info

## Database Schema

**subscribers**: chat_id (PK), username, joined_at

**clips**: id (PK), file_id, title, fmt, created_at, broadcast (0/1)

**broadcasts**: id (PK), clip_id (FK), success, failed, sent_at

## File Structure

```
clip-pipeline-bot/
├── bot.py              # Telegram bot (polling)
├── bot.db              # SQLite DB (gitignored)
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

## Progress

- [x] Admin/user menu separation
- [x] /stats command with analytics
- [x] /clips for both admin (broadcast) and users (browse/request)
- [x] Users can request clips to be sent to their chat
- [x] Broadcast tracking per session (success/failed)
- [x] Dashboard with subscriber management (remove subscribers)
- [x] Dashboard with success rate analytics
- [x] Clip title support
- [ ] Cleanup temp files after broadcast
- [ ] systemd service files for VPS auto-start