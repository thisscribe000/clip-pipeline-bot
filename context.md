# clip-pipeline-bot — Dev Context

A Telegram bot that downloads YouTube videos, cuts clips by timestamp using ffmpeg, broadcasts to subscribers, and has a web dashboard.

## Stack
- **Runtime**: Python 3, venv
- **Bot**: python-telegram-bot (v21+)
- **Download**: yt-dlp
- **Video processing**: ffmpeg
- **Database**: SQLite (bot.db — shared between bot and dashboard)
- **Dashboard**: Flask + HTML/CSS (dark-themed)
- **Auth**: Session-based admin login
- **Env vars**: python-dotenv

## Architecture

```
bot.py (Telegram bot)  ← shares →  bot.db (SQLite)
                                        ↑
                                  dashboard/app.py (Flask)
                                        ↑
                                  dashboard/templates/*.html
```

Both bot.py and dashboard/app.py read/write the same `bot.db` file.

## Dashboard Pages

| Route | Auth | Description |
|-------|------|-------------|
| `/` | Required | Admin dashboard (login if not authenticated) |
| `/login` | - | Admin login with Telegram User ID |
| `/logout` | - | Logout |
| `/subscribe` | Public | Subscribe page for non-admin users |
| `/static/*` | Public | Logo, favicon |

## Telegram Commands

| Command | Who | Description |
|---|---|---|
| `/start` | anyone | Shows admin or user menu |
| `/clips` | anyone | Admins: broadcast clips. Users: browse/request clips |
| `/subscribe` | anyone | Subscribe to receive clips |
| `/unsubscribe` | anyone | Unsubscribe from clips |
| `/cancel` | anyone | Cancel current action |

## User Flows

### Admin (Telegram)
- `✂️ Cut New Clip` — Download video, cut clip, save to Telegram
- `📡 Broadcast Clip` — Send clip to all subscribers
- `👥 Subscribers` — View subscriber list
- `📬 Send Message` — Send custom message to all subscribers
- `📊 Analytics` — Stats dashboard
- `📋 Clip History` — View all clips with status

### Admin (Dashboard — http://sharestill.paperlinkos.site:5002)
- Login with Telegram User ID
- View stats: subscribers, clips, broadcasts, success rate
- Manage subscribers (view, remove)
- Broadcast clips
- Clip history with status
- Auto-refresh every 30s
- **Admin notified via Telegram when someone subscribes**

### User (Telegram)
- `🎬 Browse Clips` — View available clips, tap to get sent
- `✅ Subscribe` — Get added to broadcast list
- `ℹ️ About` — Bot info

### User (Web — /subscribe)
- Landing page with subscribe button
- Links to open Telegram bot
- Features overview
- "Powered by Paperlinkos" footer

## Database Schema

**subscribers**: chat_id (PK), username, joined_at

**clips**: id (PK), file_id, title, fmt, created_at, broadcast (0/1)

**broadcasts**: id (PK), clip_id (FK), success, failed, sent_at

## File Structure

```
clip-pipeline-bot/
├── bot.py                    # Telegram bot (polling)
├── bot.db                    # SQLite DB (gitignored)
├── .env                      # BOT_TOKEN, ADMIN_ID, SECRET_KEY, PORT (gitignored)
├── .gitignore
├── venv/                     # Python venv (gitignored)
├── downloads/                # Temp video files (gitignored)
└── dashboard/
    ├── app.py               # Flask backend
    ├── dashboard.log        # Dashboard logs (gitignored)
    ├── static/
    │   ├── logo.svg         # App logo
    │   └── favicon.svg      # Favicon
    └── templates/
        ├── index.html       # Admin dashboard
        ├── login.html       # Admin login page
        ├── subscribe.html   # Public subscribe page
        └── forbidden.html   # Access denied page
```

## VPS Deployment

### Start bot
```bash
cd /var/www/paperlink_os/sites/sharestill
source venv/bin/activate
nohup python bot.py > bot.log 2>&1 &
```

### Start dashboard
```bash
cd /var/www/paperlink_os/sites/sharestill
source venv/bin/activate
PORT=5002 nohup python dashboard/app.py > dashboard.log 2>&1 &
```

### URLs
- Dashboard: http://sharestill.paperlinkos.site:5002
- Subscribe page: http://sharestill.paperlinkos.site:5002/subscribe
- Admin login: http://sharestill.paperlinkos.site:5002 (redirects to login if not authenticated)

## Environment Variables (.env)

```
BOT_TOKEN=your_telegram_bot_token
ADMIN_ID=your_telegram_user_id
SECRET_KEY=random_secret_for_sessions
PORT=5002
```

## Progress

- [x] Admin/user menu separation
- [x] /clips for both admin (broadcast) and users (browse/request)
- [x] Users can request clips to be sent to their chat
- [x] Broadcast tracking per session (success/failed)
- [x] Dashboard with subscriber management (remove subscribers)
- [x] Dashboard with success rate analytics
- [x] Clip title support
- [x] Admin notified via Telegram on new subscriber
- [x] Send custom message to all subscribers
- [x] Dashboard login with Telegram User ID
- [x] Public subscribe landing page
- [x] Access denied page for non-admin
- [x] Custom logo and favicon
- [x] Paperlinkos branding footer
- [ ] Cleanup temp files after broadcast
- [ ] systemd service files for VPS auto-start