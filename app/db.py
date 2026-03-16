import sqlite3
import time
from contextlib import contextmanager
from app.config import DB_PATH


SCHEMA = """
CREATE TABLE IF NOT EXISTS magic_links (
    token TEXT PRIMARY KEY,
    label TEXT,
    created_at INTEGER,
    used_at INTEGER,
    expires_at INTEGER,
    multi_use INTEGER DEFAULT 0,
    is_admin INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS sessions (
    session_id TEXT PRIMARY KEY,
    magic_token TEXT,
    created_at INTEGER,
    expires_at INTEGER,
    last_seen INTEGER,
    is_admin INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS positions (
    user_id TEXT,
    book_id TEXT,
    file_index INTEGER DEFAULT 0,
    time_seconds REAL DEFAULT 0,
    updated_at INTEGER,
    PRIMARY KEY (user_id, book_id)
);

CREATE TABLE IF NOT EXISTS users (
    user_id TEXT PRIMARY KEY,
    email TEXT UNIQUE NOT NULL,
    is_admin INTEGER DEFAULT 0,
    created_at INTEGER,
    debug_logging INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS allowed_emails (
    email TEXT PRIMARY KEY,
    is_admin INTEGER DEFAULT 0,
    added_at INTEGER
);

CREATE TABLE IF NOT EXISTS listening_heartbeats (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL,
    book_id TEXT NOT NULL,
    at INTEGER NOT NULL,
    pos_seconds REAL NOT NULL DEFAULT 0,
    file_index INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_listening_heartbeats_user_book
    ON listening_heartbeats (user_id, book_id, at);
"""


MIGRATIONS = [
    "ALTER TABLE magic_links ADD COLUMN is_admin INTEGER DEFAULT 0",
    "ALTER TABLE sessions ADD COLUMN is_admin INTEGER DEFAULT 0",
    # User-based auth additions
    "ALTER TABLE magic_links ADD COLUMN email TEXT",
    "ALTER TABLE sessions ADD COLUMN user_id TEXT",
    "ALTER TABLE positions ADD COLUMN user_id TEXT",
    "ALTER TABLE users ADD COLUMN debug_logging INTEGER DEFAULT 0",
    "ALTER TABLE listening_heartbeats ADD COLUMN pos_seconds REAL NOT NULL DEFAULT 0",
    "ALTER TABLE listening_heartbeats ADD COLUMN file_index INTEGER NOT NULL DEFAULT 0",
]


def init_db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with get_db() as db:
        db.executescript(SCHEMA)
        for sql in MIGRATIONS:
            try:
                db.execute(sql)
            except sqlite3.OperationalError as e:
                if "duplicate column" not in str(e).lower():
                    raise
        # Migrate positions table from (session_id, book_id) PK to (user_id, book_id) PK
        cols = {row[1] for row in db.execute("PRAGMA table_info(positions)")}
        if "session_id" in cols:
            db.executescript("""
                CREATE TABLE positions_new (
                    user_id TEXT,
                    book_id TEXT,
                    file_index INTEGER DEFAULT 0,
                    time_seconds REAL DEFAULT 0,
                    updated_at INTEGER,
                    PRIMARY KEY (user_id, book_id)
                );
                INSERT OR IGNORE INTO positions_new (user_id, book_id, file_index, time_seconds, updated_at)
                    SELECT user_id, book_id, file_index, time_seconds, updated_at
                    FROM positions WHERE user_id IS NOT NULL;
                DROP TABLE positions;
                ALTER TABLE positions_new RENAME TO positions;
            """)


@contextmanager
def get_db():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
