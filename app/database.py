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
    # Migration: add youtube_url column to existing DBs
    try:
        conn.execute('ALTER TABLE events ADD COLUMN youtube_url TEXT')
        conn.commit()
    except Exception:
        pass
    conn.close()
