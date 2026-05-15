# ShareStill - Future Features

## 1. Download without cutting

Add a flag to download full file without cutting:

```
[url] full mp3 "Full Song"
# or
[url] 00:00:00 full mp3 "Full Song"
```

Or new command `/download` - prompts for URL and format, no time needed.

## 2. Better naming

- Auto-fetch title from YouTube/Drive as default
- Allow override with quotes

## 3. Thumbnails

Extract frame with ffmpeg:
```python
subprocess.run(["ffmpeg", "-i", video_path, "-ss", "00:00:01", "-vframes", "1", thumbnail_path])
```
Store in DB, show in clip menu.

## 4. Duration limit

Warn if clip >30min (Telegram limit)

## 5. Queue

Process multiple clips sequentially

## 6. Progress

Show Drive upload progress

## 7. Direct link

Generate shareable link for clips

## 8. Platform support

- TikTok
- SoundCloud
- Vimeo