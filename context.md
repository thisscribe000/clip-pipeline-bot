# clip-pipeline-bot — Dev Context

A Telegram bot that downloads YouTube videos, cuts clips by timestamp using ffmpeg, and broadcasts to subscribers.

## Stack
- **Runtime**: Python 3, venv
- **Bot**: python-telegram-bot
- **Download**: yt-dlp
- **Video processing**: ffmpeg
- **Database**: SQLite (bot.db)
- **Env vars**: python-dotenv

## Commands

| Command | Who | Description |
|---|---|---|
| `/start` | anyone | Bot alive |
| `/subscribe` | anyone | Opt-in to clips |
| `/unsubscribe` | anyone | Opt-out |
| `/cut [url] [start] [end] [mp3/mp4]` | admin | Download + cut + save clip |
| `/broadcast [clip_id]` | admin | Send saved clip to all subscribers |

## Bot Flow

```
Admin: /cut <url> <start> <end> <format>
  ├─ yt-dlp downloads full video
  ├─ ffmpeg cuts clip
  ├─ upload to Telegram
  ├─ save file_id to clips table
  └─ respond with clip_id

Admin: /broadcast <clip_id>
  ├─ fetch file_id from DB
  ├─ loop through subscribers
  └─ send via Telegram API (no re-upload)

Users: /subscribe → added to subscribers table
       /unsubscribe → removed
```

## Database Schema

**subscribers**: chat_id (PK), username, joined_at

**clips**: id (PK), file_id, title, fmt, created_at, broadcast (0/1)

## Project Structure

```
clip-pipeline-bot/
├── bot.py          # Main bot code
├── bot.db          # SQLite (gitignored)
├── .env            # BOT_TOKEN, ADMIN_ID (gitignored)
├── .gitignore
├── venv/           # Python venv (gitignored)
└── downloads/      # Temp clip files (gitignored)
```

## Progress

- [x] Bot skeleton with /start, /subscribe, /unsubscribe
- [x] /cut command — yt-dlp + ffmpeg pipeline
- [x] Live progress status updates
- [x] SQLite subscriber system
- [x] /broadcast command using saved file_ids
- [ ] /clips command — list saved clips
- [ ] Cleanup temp files after broadcast
- [ ] /stats command — subscriber count, broadcast stats
- [ ] Deploy (hosting)