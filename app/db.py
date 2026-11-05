"""SQLite storage. One connection per request, closed automatically."""
import sqlite3

from flask import current_app, g

SCHEMA = """
CREATE TABLE IF NOT EXISTS polls (
    id          TEXT PRIMARY KEY,
    owner_id    INTEGER NOT NULL,
    owner_name  TEXT NOT NULL,
    question    TEXT NOT NULL,
    mode        TEXT NOT NULL CHECK (mode IN ('single', 'ranked', 'swipe', 'spin')),
    allow_add   INTEGER NOT NULL DEFAULT 0,
    anonymous   INTEGER NOT NULL DEFAULT 0,
    created_at  INTEGER NOT NULL,
    closes_at   INTEGER,
    closed_at   INTEGER,
    decided_option_id INTEGER,
    decided_source    TEXT
);
CREATE TABLE IF NOT EXISTS options (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    poll_id  TEXT NOT NULL REFERENCES polls(id) ON DELETE CASCADE,
    label    TEXT NOT NULL,
    added_by TEXT
);
CREATE INDEX IF NOT EXISTS options_poll ON options (poll_id);
CREATE TABLE IF NOT EXISTS ballots (
    poll_id    TEXT NOT NULL REFERENCES polls(id) ON DELETE CASCADE,
    user_id    INTEGER NOT NULL,
    user_name  TEXT NOT NULL,
    choices    TEXT NOT NULL,
    updated_at INTEGER NOT NULL,
    PRIMARY KEY (poll_id, user_id)
);
CREATE TABLE IF NOT EXISTS spins (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    poll_id    TEXT NOT NULL REFERENCES polls(id) ON DELETE CASCADE,
    slices     TEXT NOT NULL,
    landed_id  INTEGER NOT NULL,
    jitter     REAL NOT NULL,
    by_name    TEXT NOT NULL,
    created_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS spins_poll ON spins (poll_id);
CREATE TABLE IF NOT EXISTS poll_chats (
    poll_id       TEXT NOT NULL REFERENCES polls(id) ON DELETE CASCADE,
    chat_instance TEXT NOT NULL,
    PRIMARY KEY (poll_id, chat_instance)
);
CREATE INDEX IF NOT EXISTS poll_chats_chat ON poll_chats (chat_instance);
"""


def connect(path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(path, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def get_db() -> sqlite3.Connection:
    if "db" not in g:
        g.db = connect(current_app.config["APP"].db_path)
    return g.db


def close_db(_exc=None) -> None:
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db(path: str) -> None:
    conn = connect(path)
    conn.execute("PRAGMA journal_mode = WAL")
    conn.executescript(SCHEMA)
    conn.close()
