# User Prophecy Bank — Test Plan

## 1. Web Dashboard (`/bank`)

- [ ] Navigate to `/bank` while **not logged in** → redirects to `/login`
- [ ] Navigate to `/bank` while **logged in** → page loads with "My Prophecy Bank" title
- [ ] Empty state: no prophecies → shows "Your prophecy bank is empty" + "Write your first prophecy →" button
- [ ] Bank nav link appears in the top navbar for logged-in users

### Create

- [ ] Click **✏️ New Prophecy** → inline form appears with Title, Content, Tags
- [ ] Submit with empty title + content → shows error "Add a title or content."
- [ ] Fill title + content + tags → click "Save to Bank" → shows success → page reloads → item appears in list
- [ ] **Cancel** button closes the form without saving

### Read / List

- [ ] Newly created prophecy shows: title, content preview (truncated at 300 chars), date, tags
- [ ] Items with `file_type: audio` show 🎙️ Audio badge
- [ ] Items with `file_type: video` show 🎞️ Video badge

### Edit

- [ ] Click ✏️ button on any prophecy → edit form opens pre-filled with existing data
- [ ] Change title → Save Changes → page reloads → title updated
- [ ] Change content → Save Changes → content updated
- [ ] Change tags → Save Changes → tags updated

### Delete

- [ ] Click 🗑 button → confirmation dialog appears
- [ ] Confirm → item is removed from list
- [ ] Cancel → item stays

### Favorites

- [ ] Click ☆ button → page reloads → star becomes ⭐
- [ ] Click ⭐ button → page reloads → star reverts to ☆

### Filters

- [ ] Click **All** → shows all items
- [ ] Click **⭐ Favorites** → shows only favorited items
- [ ] Click **📝 Text** → shows only text (`file_type: text`) items
- [ ] Click **🎙️ Audio** → shows only audio items
- [ ] Type in search box → filters by title and tags in real time

---

## 2. API (direct)

### `GET /api/user/prophecies`

- [ ] Without session cookie → 401 or redirect
- [ ] With valid session → returns `[]` when empty, array of objects when populated
- [ ] Response includes: `id, user_id, title, content_text, audio_file_id, audio_duration, video_file_id, file_type, is_favorite, tags, created_at`

### `POST /api/user/prophecies`

- [ ] Without session → 401
- [ ] With valid JSON `{title, content, tags}` → returns `{"id": N}`, 201
- [ ] Without body → returns `{"error": "Invalid JSON"}`, 400

### `GET /api/user/prophecies/<id>`

- [ ] Valid id → returns single prophecy object
- [ ] Invalid id → 404
- [ ] Another user's id → 404 (ownership enforced)

### `PUT /api/user/prophecies/<id>`

- [ ] Update title → returns `{"success": true}`
- [ ] Update content → content changes
- [ ] Update tags → tags changes
- [ ] Partial update (send only title) → only title changes, other fields unchanged

### `DELETE /api/user/prophecies/<id>`

- [ ] Delete own prophecy → returns `{"success": true}`
- [ ] Delete another user's prophecy → 404

### `POST /api/user/prophecies/<id>/favorite`

- [ ] Toggle favorite → returns `{"success": true}`
- [ ] Toggle twice → alternates between 0 and 1

---

## 3. Telegram Bot

- [ ] Send `/start` → menu shows "📓 My Prophecy Bank" button
- [ ] Tap "📓 My Prophecy Bank" → shows last 10 prophecies with ⭐ for favorited
- [ ] Tap with empty bank → shows "Your Prophecy Bank is empty" message
- [ ] Message includes link `sharestill.paperlinkos.site/bank`

### Test Data (create via API)
```bash
curl -X POST https://sharestill.paperlinkos.site/api/user/prophecies \
  -H "Content-Type: application/json" \
  -b "session=<YOUR_SESSION_COOKIE>" \
  -d '{"title":"Healing is Mine","content":"By His stripes I am healed","tags":"healing,2026"}'
```
