# ShareStill — Session Context

## Date: June 8, 2026

---

## Status: ALL SYSTEMS OPERATIONAL

---

## URLs
- **Landing/Dashboard**: https://sharestill.paperlinkos.site (Flask on port 5000)
- **Location**: `/var/www/paperlink_os/sites/sharestill`
- **Dashboard app**: `dashboard/app.py` + `dashboard/models.py`
- **Templates**: `dashboard/templates/`

---

## Completed Features

### Core Pipeline
- Clip cutting via yt-dlp with title auto-fetch + custom override with quotes
- `/download` full file download
- Thumbnails (auto-extract MP4 / fetch MP3)
- 1000+ platform support via yt-dlp
- Cookie support for private content

### File Converter
- Audio/video conversion (mp3, mp4, wav, aac, mov)
- Send file with format caption to convert

### Queue & Broadcast
- Queue system (background job processing)
- Broadcast preview (confirm/cancel before sending)
- Scheduled broadcast (set future datetime)
- Selective broadcast (pick specific subscribers)

### Admin Dashboard
- Full admin panel: create/manage clips, users, delivery log
- Search, filter by type/status, pagination
- Login with admin_id or email/password
- Admin testimonies review (approve/reject/delete/reinstate)

### Prophecy Bank (User Vault)
- Create, edit, delete personal prophecies (text)
- Star favorites, filter by favorites/text/audio
- Search by title or tags
- API: GET/POST `/api/user/prophecies`, PUT/DELETE `/<id>`, POST `/<id>/favorite`

### Testimonies System
- DB table: testimonies (user_id, user_name, title, content, category, status, source)
- User dashboard tab: own testimonies with status badges (Posted/Pending/Rejected/Deleted)
- Create from dashboard or landing page
- Edit: resets to pending (admin re-approval needed)
- Delete: soft-delete (archived, visible to admin, reinstateable)
- Category dropdown: Messages, Prophecies, Prayers, Services
- Admin review: approve / reject / delete / reinstate
- API: GET/POST `/api/user/testimonies`, PUT/DELETE `/<id>`

### Platform & UX
- Clickable logo, SVG favicon (lime hexagon)
- Mobile overflow fix, emoji-free UI
- Player bar with play/pause/progress for audio previews

---

## Recent Changes (June 8, 2026)

### Testimonies Tab (replaced Reels tab on dashboard)
- Users see their own testimonies with status badges
- Write, Edit, Delete functionality
- Edit resets to pending (admin re-approval)
- Delete soft-archives in DB (2-week window for admin reinstate)
- Category dropdown (Messages, Prophecies, Prayers, Services)

### Bank Alignment Fix
- Filter buttons and search bar now same height (consistent padding, font-size, borders)

### Technical
- Added `deleted_at`, `deleted_by_user`, `category` columns to testimonies table
- `Cache-Control: no-cache` headers added to nginx config
- `bot.db` removed from git tracking (user data)

---

## Bot
- Telegram bot: `bot.py` at root of `/var/www/paperlink_os/sites/sharestill/`
- Background tasks: process_queue + check_scheduled
- Commands: /start, /help, /cut, /download, /bank, /testimony

---

## Repos
- **Main**: `github.com/thisscribe000/paperlink_os` (monorepo, sharestill in `sites/sharestill/`)
- **Subtree**: `github.com/thisscribe000/clip-pipeline-bot` (sharestill-only push via `git subtree push --prefix sites/sharestill clip-bot main`)
