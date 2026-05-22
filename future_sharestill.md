# ShareStill — Feature Status

## ✅ Done

### 1. Download without cutting
- `/download [url] [mp3/mp4] "Custom Name"` — full file download, no cut required

### 2. Better naming
- Auto-fetch title from YouTube/Drive as default via yt-dlp
- Override with quotes: `/cut [url] [start] [end] [format] "Custom Name"`

### 3. Thumbnails
- Auto-extract from MP4 / fetch for MP3 via yt-dlp
- Stored in DB, shown in clip menu

### 5. Queue System
- Jobs processed one at a time in background (`process_queue`)
- Scheduled broadcast support (`check_scheduled`)

### 7. Google Drive Integration
- Files >45MB auto-uploaded to Google Drive
- Drive links saved to database
- Download from Google Drive URL also supported

### 8. Platform Support
- YouTube, YouTube Music, Google Drive, Instagram (public), TikTok (public), Facebook, Twitter/X, Vimeo, SoundCloud, 1000+ sites via yt-dlp
- Cookie support for private content

### 9. Automated Prophecy Clip Delivery
- **Bot side**: `/prophecy` command, `prophecy_clips` / `users` / `prophecy_delivery_log` tables, `auto_deliver_prophecies()` background task, Prophecy Feed button in user menu
- **Dashboard v2** (new admin + user panel):
  - Admin ID login + email/password user registration/login
  - User dashboard with tabs: Written, Audio, Reels, Settings
  - Admin panel: prophecy manager, Telegram clip broadcast, user/subscriber management, delivery log
  - Delivery preferences (time, frequency, timezone)
  - Responsive design (lime/black, noise texture, Bebas Neue / Space Grotesk / IBM Plex Mono)
- **Deployed** at https://sharestill.paperlinkos.site
- **Pushed** to https://github.com/thisscribe000/clip-pipeline-bot

## 🔜 Upcoming

### 4. Duration limit
- Warn if clip >30min (Telegram limit)

### 6. Direct link
- Generate shareable link for clips
