"""SQLite access: the schema, the connection, and the FTS5 triggers.

One file holds everything. The schema is applied with `PRAGMA user_version`
so it can be extended later without a migration framework.
"""

import sqlite3
from pathlib import Path

SCHEMA_VERSION = 8

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

-- last4 is the token's own final characters, so the owner can tell tokens
-- apart; it is shown nowhere else and reveals nothing about the rest.
CREATE TABLE IF NOT EXISTS api_token (
    token_hash TEXT PRIMARY KEY,
    pass_id TEXT NOT NULL,
    last4 TEXT NOT NULL
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

# Private replies are encrypted in the browser. item.sealed holds the encrypted reply
# (text stays NULL), and thread_key holds each participant's public key for one thread.
# Keys are per thread so they can't link a person's threads together.
SEALED_REPLIES = """
ALTER TABLE item ADD COLUMN sealed TEXT;

CREATE TABLE IF NOT EXISTS thread_key (
    pass_id TEXT NOT NULL,
    thread_id TEXT NOT NULL,
    public_key TEXT NOT NULL,
    PRIMARY KEY (pass_id, thread_id)
);
"""

# The maintainer can remove a comment's words and leave a reason in their place
# ("Removed because it named someone."). The text itself is deleted, not kept.
REMOVED_REASON = """
ALTER TABLE item ADD COLUMN removed_reason TEXT;
"""

# A reply's author can add edits under it (append-only: the original never changes).
# n counts from 1 per reply. A private reply's edits are sealed the same way (text NULL).
REPLY_EDITS = """
CREATE TABLE IF NOT EXISTS item_edit (
    item_id TEXT NOT NULL REFERENCES item(id) ON DELETE CASCADE,
    n INTEGER NOT NULL,
    text TEXT,
    sealed TEXT,
    created_at TEXT NOT NULL,
    PRIMARY KEY (item_id, n)
);
"""

# When each reaction was added, so the notification bell can tell new ones from old.
# Reactions from before this have no time and never show as new.
REACTION_TIMES = """
ALTER TABLE reaction ADD COLUMN created_at TEXT;
"""

# Step n upgrades a file at version n - 1 to version n.
# 6: edits change the item itself now, so each item notes when it was last edited. The old
# append-only item_edit table is left as it is (nothing reads it any more, no rows are dropped).
EDITED_AT = """
ALTER TABLE item ADD COLUMN edited_at TEXT;
"""

# Someone following a whole post: any activity on it reaches their Feed.
SUBSCRIPTIONS = """
CREATE TABLE IF NOT EXISTS subscription (
    pass_id TEXT NOT NULL,
    thread_id TEXT NOT NULL REFERENCES item(id) ON DELETE CASCADE,
    PRIMARY KEY (pass_id, thread_id)
);
"""

# NSFW posts show only to people who turned NSFW on. nsfw is where the post is now; nsfw_marked is what its
# author answered (NULL for posts from before the question). Where the two differ, the maintainer moved it:
# those corrections are what a classifier can learn from. Replies follow their post and are never marked.
NSFW = """
ALTER TABLE item ADD COLUMN nsfw INTEGER NOT NULL DEFAULT 0;
ALTER TABLE item ADD COLUMN nsfw_marked INTEGER;
"""

MIGRATIONS = {1: SCHEMA, 2: SEALED_REPLIES, 3: REMOVED_REASON, 4: REPLY_EDITS, 5: REACTION_TIMES, 6: EDITED_AT, 7: SUBSCRIPTIONS,
              8: NSFW}


def connect(path: Path | str) -> sqlite3.Connection:
    """Opens the database with the pragmas the app relies on."""
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA busy_timeout = 5000")  # wait for another thread's write instead of failing
    return conn


def migrate(conn: sqlite3.Connection) -> None:
    """Applies each schema step the file hasn't had yet, tracked with user_version."""
    version = conn.execute("PRAGMA user_version").fetchone()[0]
    for step in range(version + 1, SCHEMA_VERSION + 1):
        conn.executescript(MIGRATIONS[step])
        conn.execute(f"PRAGMA user_version = {step}")
        conn.commit()
