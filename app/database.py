import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), '..', 'data', 'marathon.db')

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    conn.executescript('''
        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            date TEXT NOT NULL,
            prefecture TEXT NOT NULL,
            region TEXT NOT NULL,
            distance TEXT NOT NULL,
            venue TEXT,
            entry_start TEXT,
            entry_end TEXT,
            fee TEXT,
            time_limit TEXT,
            url TEXT,
            entry_url TEXT,
            entry_site TEXT,
            confirmed INTEGER DEFAULT 0,
            source TEXT,
            youtube_url TEXT,
            updated_at TEXT DEFAULT (datetime('now', 'localtime'))
        );

        CREATE TABLE IF NOT EXISTS user_progress (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_id INTEGER NOT NULL,
            status TEXT DEFAULT 'none',
            memo TEXT,
            finish_time TEXT,
            by_admin INTEGER DEFAULT 0,
            updated_at TEXT DEFAULT (datetime('now', 'localtime')),
            FOREIGN KEY (event_id) REFERENCES events(id)
        );

    ''')
    conn.commit()
    conn.executescript('''
        CREATE TABLE IF NOT EXISTS visitor_log (
            date TEXT NOT NULL,
            visitor_id TEXT NOT NULL,
            PRIMARY KEY (date, visitor_id)
        );
    ''')
    conn.commit()
    # Migration: add columns to existing DBs
    for col_def in [
        'ALTER TABLE events ADD COLUMN youtube_url TEXT',
        'ALTER TABLE events ADD COLUMN youtube_locked INTEGER DEFAULT 0',
        "ALTER TABLE user_progress ADD COLUMN visitor_id TEXT DEFAULT 'admin'",
    ]:
        try:
            conn.execute(col_def)
            conn.commit()
        except Exception:
            pass
    # 既存レコードを管理者レコードとして明示
    conn.execute("UPDATE user_progress SET visitor_id = 'admin' WHERE visitor_id IS NULL")
    conn.commit()
    conn.close()
