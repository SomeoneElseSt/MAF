"""SQLite access: the schema, the connection, and the FTS5 triggers.

One file holds everything. The schema is applied with `PRAGMA user_version`
so it can be extended later without a migration framework.
"""

import sqlite3
from pathlib import Path

SCHEMA_VERSION = 1

SCHEMA = """
CREATE TABLE IF NOT EXISTS pass (
    id TEXT PRIMARY KEY
);

CREATE TABLE IF NOT EXISTS redeemed_token (
    token_hash TEXT PRIMARY KEY
);

-- thread_id is the root post's id. A post has parent_id NULL; a comment points at
-- its parent. private_to is the recipient's pass_id for private replies.
CREATE TABLE IF NOT EXISTS item (
    id TEXT PRIMARY KEY,
    parent_id TEXT REFERENCES item(id) ON DELETE CASCADE,
    thread_id TEXT NOT NULL,
    pass_id TEXT NOT NULL,
    title TEXT,
    url TEXT,
    text TEXT,
    created_at TEXT NOT NULL,
    views INTEGER NOT NULL DEFAULT 0,
    flags INTEGER NOT NULL DEFAULT 0,
    hidden INTEGER NOT NULL DEFAULT 0,
    restored INTEGER NOT NULL DEFAULT 0,
    pinned INTEGER NOT NULL DEFAULT 0,
    private_to TEXT
);
CREATE INDEX IF NOT EXISTS item_thread ON item(thread_id, created_at);
CREATE INDEX IF NOT EXISTS item_created ON item(created_at);
CREATE INDEX IF NOT EXISTS item_parent ON item(parent_id);

CREATE TABLE IF NOT EXISTS item_tag (
    item_id TEXT NOT NULL REFERENCES item(id) ON DELETE CASCADE,
    tag TEXT NOT NULL,
    PRIMARY KEY (item_id, tag)
);
CREATE INDEX IF NOT EXISTS item_tag_tag ON item_tag(tag);

CREATE TABLE IF NOT EXISTS flag (
    pass_id TEXT NOT NULL,
    item_id TEXT NOT NULL REFERENCES item(id) ON DELETE CASCADE,
    PRIMARY KEY (pass_id, item_id)
);

CREATE TABLE IF NOT EXISTS reaction (
    pass_id TEXT NOT NULL,
    item_id TEXT NOT NULL REFERENCES item(id) ON DELETE CASCADE,
    emoji TEXT NOT NULL,
    PRIMARY KEY (pass_id, item_id, emoji)
);

CREATE TABLE IF NOT EXISTS moderation_request (
    pass_id TEXT NOT NULL,
    item_id TEXT NOT NULL REFERENCES item(id) ON DELETE CASCADE,
    kind TEXT NOT NULL CHECK (kind IN ('unhide', 'nuke')),
    PRIMARY KEY (pass_id, item_id, kind)
);

CREATE TABLE IF NOT EXISTS api_token (
    token_hash TEXT PRIMARY KEY,
    pass_id TEXT NOT NULL
);

-- Full text over public items only. Private replies are never indexed.
CREATE VIRTUAL TABLE IF NOT EXISTS item_fts USING fts5(
    title,
    text,
    content='',
    tokenize='unicode61 remove_diacritics 2'
);

-- item_fts rows are inserted and deleted by the app (maf/store.py), not by
-- triggers: a contentless FTS5 table can't read its source columns back, and
-- deletes must be made with the special 'delete' command.
"""


def connect(path: Path | str) -> sqlite3.Connection:
    """Opens the database with the pragmas the app relies on."""
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


def migrate(conn: sqlite3.Connection) -> None:
    """Applies the schema once per file, tracked with user_version."""
    version = conn.execute("PRAGMA user_version").fetchone()[0]
    if version >= SCHEMA_VERSION:
        return
    conn.executescript(SCHEMA)
    conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
    conn.commit()
