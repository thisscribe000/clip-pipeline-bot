# Share Still — Project Context

## What It Is
A Telegram bot that downloads YouTube videos, cuts clips by timestamp, broadcasts to subscribers, with a web dashboard.

## Bot: @sharestillbot
- **Token:** 8690897881:AAEGA8PYHxR4_C7Eu9azYuSvmzC6SiHNBoM
- **Admin ID:** 1099422307

## Deployment
- **VPS:** /var/www/paperlink_os/sites/sharestill
- **Dashboard URL:** http://sharestill.paperlinkos.site:5002
- **Repo:** https://github.com/thisscribe000/clip-pipeline-bot

## Running on VPS
```bash
# Bot
cd /var/www/paperlink_os/sites/sharestill
source venv/bin/activate
nohup python bot.py > bot.log 2>&1 &

# Dashboard
cd /var/www/paperlink_os/sites/sharestill
source venv/bin/activate
PORT=5002 nohup python dashboard/app.py > dashboard.log 2>&1 &
```

## Features Working

### Telegram Bot
- [x] Admin menu: Cut New Clip, Broadcast Clip, Subscribers, Send Message, Analytics, Clip History
- [x] User menu: Browse Clips, Subscribe, About
- [x] /clips works for both (admin broadcasts, users request)
- [x] New subscriber notification to admin
- [x] Send custom message to all subscribers
- [x] /subscribe and /unsubscribe commands

### Dashboard (port 5002)
- [x] Admin login with Telegram User ID
- [x] Stats: subscribers, clips, broadcasts sent, success rate
- [x] Subscriber list with remove option
- [x] Clips table with broadcast button
- [x] Auto-refresh every 30s
- [x] Logo and favicon
- [x] "Powered by Paperlinkos" footer

### Web Pages
- [x] `/` - Login page (enter admin ID)
- [x] `/dashboard` - Admin dashboard (after login)
- [x] `/subscribe` - Public subscribe page for non-admins
- [x] `/forbidden` - Shown when non-admin tries dashboard

## To Do
- [ ] Test cutting a real clip
- [ ] Test broadcast functionality
- [ ] Test subscriber notification
- [ ] systemd services for auto-start
- [ ] Cleanup temp files after broadcast

## Key Files
- `bot.py` - Telegram bot
- `dashboard/app.py` - Flask dashboard
- `dashboard/templates/index.html` - Admin dashboard HTML
- `dashboard/templates/login.html` - Login page
- `dashboard/templates/subscribe.html` - Public subscribe page
- `dashboard/templates/forbidden.html` - Access denied page
- `dashboard/static/logo.svg` - App logo
- `dashboard/static/favicon.svg` - Favicon
- `context.md` - This file