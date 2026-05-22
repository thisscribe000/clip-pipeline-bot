import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "bot.db")


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_prophecy_tables():
    conn = get_db()
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            telegram_id INTEGER,
            delivery_time TEXT DEFAULT '08:00',
            delivery_frequency TEXT DEFAULT 'daily',
            timezone TEXT DEFAULT 'Africa/Lagos',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS prophecy_clips (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            content_text TEXT,
            audio_file_id TEXT,
            audio_url TEXT,
            video_file_id TEXT,
            video_url TEXT,
            thumbnail TEXT,
            month TEXT DEFAULT '',
            program TEXT DEFAULT '',
            series TEXT DEFAULT '',
            speaker TEXT DEFAULT '',
            service_date TEXT DEFAULT '',
            tags TEXT DEFAULT '',
            source TEXT DEFAULT 'web',
            uploaded_by INTEGER,
            is_featured INTEGER DEFAULT 0,
            is_active INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS user_prophecies (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            title TEXT DEFAULT '',
            content_text TEXT DEFAULT '',
            audio_file_id TEXT DEFAULT '',
            audio_duration REAL DEFAULT 0,
            video_file_id TEXT DEFAULT '',
            file_type TEXT DEFAULT 'text',
            is_favorite INTEGER DEFAULT 0,
            tags TEXT DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS prophecy_delivery_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            clip_id INTEGER,
            delivered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            method TEXT DEFAULT 'telegram',
            FOREIGN KEY (user_id) REFERENCES users(id),
            FOREIGN KEY (clip_id) REFERENCES prophecy_clips(id)
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS testimonies (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            user_name TEXT DEFAULT '',
            title TEXT DEFAULT '',
            content TEXT NOT NULL,
            media_file_id TEXT DEFAULT '',
            media_type TEXT DEFAULT '',
            status TEXT DEFAULT 'pending',
            is_public INTEGER DEFAULT 0,
            source TEXT DEFAULT 'web',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            approved_at TIMESTAMP,
            approved_by INTEGER,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)
    conn.commit()
    conn.close()
    migrate_prophecy_clips()


def migrate_prophecy_clips():
    conn = get_db()
    existing = [row[1] for row in conn.execute("PRAGMA table_info(prophecy_clips)").fetchall()]
    new_cols = {
        "month": "TEXT DEFAULT ''",
        "program": "TEXT DEFAULT ''",
        "series": "TEXT DEFAULT ''",
        "speaker": "TEXT DEFAULT ''",
        "service_date": "TEXT DEFAULT ''",
        "tags": "TEXT DEFAULT ''",
        "source": "TEXT DEFAULT 'web'",
        "uploaded_by": "INTEGER",
        "is_featured": "INTEGER DEFAULT 0",
    }
    for col, col_type in new_cols.items():
        if col not in existing:
            conn.execute(f"ALTER TABLE prophecy_clips ADD COLUMN {col} {col_type}")
    conn.commit()
    conn.close()


def get_user_by_email(email):
    conn = get_db()
    user = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
    conn.close()
    return user


def get_user_by_id(user_id):
    conn = get_db()
    user = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    conn.close()
    return user


def create_user(email, password_hash, telegram_id=None):
    conn = get_db()
    c = conn.cursor()
    c.execute(
        "INSERT INTO users (email, password_hash, telegram_id) VALUES (?, ?, ?)",
        (email, password_hash, telegram_id)
    )
    conn.commit()
    user_id = c.lastrowid
    conn.close()
    return user_id


def update_user_prefs(user_id, delivery_time, delivery_frequency, timezone):
    conn = get_db()
    conn.execute(
        "UPDATE users SET delivery_time = ?, delivery_frequency = ?, timezone = ? WHERE id = ?",
        (delivery_time, delivery_frequency, timezone, user_id)
    )
    conn.commit()
    conn.close()


def get_opt_in_telegram_users():
    conn = get_db()
    users = conn.execute(
        "SELECT * FROM users WHERE telegram_id IS NOT NULL"
    ).fetchall()
    conn.close()
    return users


def get_active_prophecy_clips():
    conn = get_db()
    clips = conn.execute(
        "SELECT * FROM prophecy_clips WHERE is_active = 1 ORDER BY created_at DESC"
    ).fetchall()
    conn.close()
    return clips


def get_all_prophecy_clips():
    conn = get_db()
    clips = conn.execute(
        "SELECT * FROM prophecy_clips ORDER BY created_at DESC"
    ).fetchall()
    conn.close()
    return clips


def get_prophecy_clip(clip_id):
    conn = get_db()
    clip = conn.execute("SELECT * FROM prophecy_clips WHERE id = ?", (clip_id,)).fetchone()
    conn.close()
    return clip


def create_prophecy_clip(
    title, content_text=None, audio_file_id=None, audio_url=None,
    video_file_id=None, video_url=None, thumbnail=None,
    month=None, program=None, series=None, speaker=None,
    service_date=None, tags=None, source='web', uploaded_by=None,
    is_featured=0
):
    conn = get_db()
    c = conn.cursor()
    c.execute(
        """INSERT INTO prophecy_clips
           (title, content_text, audio_file_id, audio_url, video_file_id, video_url,
            thumbnail, month, program, series, speaker, service_date, tags,
            source, uploaded_by, is_featured)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (title, content_text, audio_file_id, audio_url, video_file_id, video_url,
         thumbnail, month or '', program or '', series or '',
         speaker or '', service_date or '', tags or '',
         source, uploaded_by, is_featured)
    )
    conn.commit()
    clip_id = c.lastrowid
    conn.close()
    return clip_id


def update_prophecy_clip(
    clip_id, title, content_text=None, is_active=1,
    month=None, program=None, series=None, speaker=None,
    service_date=None, tags=None, is_featured=0,
    audio_file_id=None, audio_url=None, video_file_id=None, video_url=None
):
    conn = get_db()
    conn.execute(
        """UPDATE prophecy_clips SET title=?, content_text=?, is_active=?,
           month=?, program=?, series=?, speaker=?, service_date=?,
           tags=?, is_featured=?, audio_file_id=?, audio_url=?,
           video_file_id=?, video_url=?
           WHERE id=?""",
        (title, content_text, is_active,
         month or '', program or '', series or '',
         speaker or '', service_date or '', tags or '', is_featured,
         audio_file_id, audio_url, video_file_id, video_url, clip_id)
    )
    conn.commit()
    conn.close()


def delete_prophecy_clip(clip_id):
    conn = get_db()
    conn.execute("DELETE FROM prophecy_clips WHERE id = ?", (clip_id,))
    conn.commit()
    conn.close()


def search_prophecy_clips(month=None, program=None, series=None, speaker=None, q=None, is_active_only=True):
    conn = get_db()
    sql = "SELECT * FROM prophecy_clips WHERE 1=1"
    params = []
    if is_active_only:
        sql += " AND is_active = 1"
    if month:
        sql += " AND month = ?"
        params.append(month)
    if program:
        sql += " AND program = ?"
        params.append(program)
    if series:
        sql += " AND series = ?"
        params.append(series)
    if speaker:
        sql += " AND speaker = ?"
        params.append(speaker)
    if q:
        sql += " AND (title LIKE ? OR content_text LIKE ? OR tags LIKE ?)"
        like = f"%{q}%"
        params.extend([like, like, like])
    sql += " ORDER BY created_at DESC"
    clips = conn.execute(sql, params).fetchall()
    conn.close()
    return clips


def get_distinct_values(column):
    conn = get_db()
    rows = conn.execute(
        f"SELECT DISTINCT {column} FROM prophecy_clips WHERE {column} IS NOT NULL AND {column} != '' ORDER BY {column}"
    ).fetchall()
    conn.close()
    return [r[column] for r in rows]


def get_delivery_log(user_id=None, limit=20):
    conn = get_db()
    if user_id:
        rows = conn.execute(
            """SELECT p.title, d.delivered_at, d.method
               FROM prophecy_delivery_log d
               JOIN prophecy_clips p ON d.clip_id = p.id
               WHERE d.user_id = ?
               ORDER BY d.delivered_at DESC LIMIT ?""",
            (user_id, limit)
        ).fetchall()
    else:
        rows = conn.execute(
            """SELECT p.title, d.delivered_at, d.method, u.email
               FROM prophecy_delivery_log d
               JOIN prophecy_clips p ON d.clip_id = p.id
               JOIN users u ON d.user_id = u.id
               ORDER BY d.delivered_at DESC LIMIT ?""",
            (limit,)
        ).fetchall()
    conn.close()
    return rows


def log_delivery(user_id, clip_id, method="telegram"):
    conn = get_db()
    conn.execute(
        "INSERT INTO prophecy_delivery_log (user_id, clip_id, method) VALUES (?, ?, ?)",
        (user_id, clip_id, method)
    )
    conn.commit()
    conn.close()


def get_next_undelivered_clip(user_id):
    conn = get_db()
    clip = conn.execute(
        """SELECT * FROM prophecy_clips WHERE is_active = 1 AND id NOT IN (
               SELECT clip_id FROM prophecy_delivery_log WHERE user_id = ?
           ) ORDER BY created_at ASC LIMIT 1""",
        (user_id,)
    ).fetchone()
    conn.close()
    return clip


def create_user_prophecy(user_id, title='', content_text='', audio_file_id='', audio_duration=0, video_file_id='', file_type='text', tags=''):
    conn = get_db()
    c = conn.cursor()
    c.execute(
        """INSERT INTO user_prophecies
           (user_id, title, content_text, audio_file_id, audio_duration, video_file_id, file_type, tags)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (user_id, title, content_text, audio_file_id, audio_duration, video_file_id, file_type, tags)
    )
    conn.commit()
    pid = c.lastrowid
    conn.close()
    return pid


def get_user_prophecies(user_id):
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM user_prophecies WHERE user_id = ? ORDER BY created_at DESC",
        (user_id,)
    ).fetchall()
    conn.close()
    return rows


def get_user_prophecy(prophecy_id):
    conn = get_db()
    row = conn.execute("SELECT * FROM user_prophecies WHERE id = ?", (prophecy_id,)).fetchone()
    conn.close()
    return row


def update_user_prophecy(prophecy_id, user_id, title=None, content_text=None, tags=None):
    conn = get_db()
    sets = []
    params = []
    if title is not None:
        sets.append("title = ?")
        params.append(title)
    if content_text is not None:
        sets.append("content_text = ?")
        params.append(content_text)
    if tags is not None:
        sets.append("tags = ?")
        params.append(tags)
    if sets:
        conn.execute(
            f"UPDATE user_prophecies SET {', '.join(sets)} WHERE id = ? AND user_id = ?",
            params + [prophecy_id, user_id]
        )
        conn.commit()
    conn.close()


def delete_user_prophecy(prophecy_id):
    conn = get_db()
    conn.execute("DELETE FROM user_prophecies WHERE id = ?", (prophecy_id,))
    conn.commit()
    conn.close()


def toggle_user_prophecy_favorite(prophecy_id):
    conn = get_db()
    conn.execute(
        "UPDATE user_prophecies SET is_favorite = CASE WHEN is_favorite = 1 THEN 0 ELSE 1 END WHERE id = ?",
        (prophecy_id,)
    )
    conn.commit()
    conn.close()


def create_testimony(user_id=None, user_name='', title='', content='', media_file_id='', media_type='', source='web'):
    conn = get_db()
    c = conn.cursor()
    c.execute(
        """INSERT INTO testimonies (user_id, user_name, title, content, media_file_id, media_type, source)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (user_id, user_name, title, content, media_file_id, media_type, source)
    )
    conn.commit()
    tid = c.lastrowid
    conn.close()
    return tid


def get_testimonies(status=None, is_public=None, limit=50):
    conn = get_db()
    sql = "SELECT * FROM testimonies WHERE 1=1"
    params = []
    if status:
        sql += " AND status = ?"
        params.append(status)
    if is_public is not None:
        sql += " AND is_public = ?"
        params.append(is_public)
    sql += " ORDER BY created_at DESC LIMIT ?"
    params.append(limit)
    rows = conn.execute(sql, params).fetchall()
    conn.close()
    return rows


def get_testimony(testimony_id):
    conn = get_db()
    row = conn.execute("SELECT * FROM testimonies WHERE id = ?", (testimony_id,)).fetchone()
    conn.close()
    return row


def approve_testimony(testimony_id, approved_by=None):
    conn = get_db()
    conn.execute(
        "UPDATE testimonies SET status='approved', is_public=1, approved_at=CURRENT_TIMESTAMP, approved_by=? WHERE id=?",
        (approved_by, testimony_id)
    )
    conn.commit()
    conn.close()


def reject_testimony(testimony_id):
    conn = get_db()
    conn.execute(
        "UPDATE testimonies SET status='rejected', is_public=0 WHERE id=?",
        (testimony_id,)
    )
    conn.commit()
    conn.close()


def delete_testimony(testimony_id):
    conn = get_db()
    conn.execute("DELETE FROM testimonies WHERE id = ?", (testimony_id,))
    conn.commit()
    conn.close()
