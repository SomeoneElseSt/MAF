"""Data access: every read and write the app, CLI, API and MCP make.

One module owns the SQL so the same logic serves the web routes, `maf` and the
read-only API. Functions return plain dicts (or dataclasses where a shape is
shared) so templates and JSON can use them directly.

Privacy notes:
- Nothing here ever stores an email address or anything derived from one.
- Items keep no IP, no user agent, and passes keep no creation time.
"""

import sqlite3
from dataclasses import dataclass, field
from datetime import date, timedelta

from .util import day_start, iso, new_item_id, new_pass_id, parse_iso, utc_now

PAGE_SIZE = 30
FOUR_DAYS = 4
FLAGS_TO_HIDE = 5
MAX_TAGS = 3
TAG_MAX_LENGTH = 24
TEXT_PREVIEW = 240
TITLE_MAX = 200
BODY_MAX = 20_000


# -- passes and tokens ----------------------------------------------------


def create_pass(conn: sqlite3.Connection, pass_id: str | None = None) -> str:
    pass_id = pass_id or new_pass_id()
    conn.execute("INSERT INTO pass (id) VALUES (?)", (pass_id,))
    conn.commit()
    return pass_id


def pass_exists(conn: sqlite3.Connection, pass_id: str) -> bool:
    row = conn.execute("SELECT 1 FROM pass WHERE id = ?", (pass_id,)).fetchone()
    return row is not None


def token_redeemed(conn: sqlite3.Connection, token_hash: str) -> bool:
    row = conn.execute("SELECT 1 FROM redeemed_token WHERE token_hash = ?", (token_hash,)).fetchone()
    return row is not None


def redeem_token(conn: sqlite3.Connection, token_hash: str, pass_id: str) -> bool:
    """Records a redeemed token and its pass atomically. False if already used."""
    if token_redeemed(conn, token_hash):
        return False
    conn.execute("INSERT INTO redeemed_token (token_hash) VALUES (?)", (token_hash,))
    conn.execute("INSERT INTO pass (id) VALUES (?)", (pass_id,))
    conn.commit()
    return True


def create_api_token(conn: sqlite3.Connection, token_hash: str, pass_id: str, last4: str) -> None:
    conn.execute("INSERT INTO api_token (token_hash, pass_id, last4) VALUES (?, ?, ?)", (token_hash, pass_id, last4))
    conn.commit()


def api_token_pass(conn: sqlite3.Connection, token_hash: str) -> str | None:
    row = conn.execute("SELECT pass_id FROM api_token WHERE token_hash = ?", (token_hash,)).fetchone()
    return row["pass_id"] if row else None


def list_api_tokens(conn: sqlite3.Connection, pass_id: str) -> list[dict]:
    rows = conn.execute(
        "SELECT token_hash, last4 FROM api_token WHERE pass_id = ? ORDER BY token_hash", (pass_id,)
    ).fetchall()
    return [{"hash": r["token_hash"], "last4": r["last4"]} for r in rows]


def revoke_api_token(conn: sqlite3.Connection, token_hash: str, pass_id: str) -> bool:
    cur = conn.execute("DELETE FROM api_token WHERE token_hash = ? AND pass_id = ?", (token_hash, pass_id))
    conn.commit()
    return cur.rowcount > 0


# -- items ---------------------------------------------------------------


@dataclass
class Item:
    id: str
    thread_id: str
    pass_id: str
    title: str | None
    url: str | None
    text: str | None
    created_at: str
    parent_id: str | None = None
    views: int = 0
    flags: int = 0
    hidden: int = 0
    restored: int = 0
    pinned: int = 0
    private_to: str | None = None
    tags: list[str] = field(default_factory=list)
    comment_count: int = 0
    thread_title: str | None = None

    @property
    def is_post(self) -> bool:
        return self.parent_id is None

    @property
    def unlisted(self) -> bool:
        return bool(self.hidden) and not self.restored

    @property
    def is_private(self) -> bool:
        return self.private_to is not None

    @property
    def text_preview(self) -> str | None:
        if not self.text:
            return None
        return self.text[:TEXT_PREVIEW]


def _row_to_item(row: sqlite3.Row, tags: list[str] | None = None) -> Item:
    return Item(
        id=row["id"],
        parent_id=row["parent_id"],
        thread_id=row["thread_id"],
        pass_id=row["pass_id"],
        title=row["title"],
        url=row["url"],
        text=row["text"],
        created_at=row["created_at"],
        views=row["views"],
        flags=row["flags"],
        hidden=row["hidden"],
        restored=row["restored"],
        pinned=row["pinned"],
        private_to=row["private_to"],
        tags=tags or [],
    )


def get_item(conn: sqlite3.Connection, item_id: str) -> Item | None:
    row = conn.execute("SELECT * FROM item WHERE id = ?", (item_id,)).fetchone()
    if row is None:
        return None
    return _row_to_item(row, item_tags(conn, item_id))


def item_tags(conn: sqlite3.Connection, item_id: str) -> list[str]:
    rows = conn.execute("SELECT tag FROM item_tag WHERE item_id = ? ORDER BY rowid", (item_id,)).fetchall()
    return [r["tag"] for r in rows]


def _fts_values(title: str | None, text: str | None) -> tuple[str, str]:
    return title or "", text or ""


def create_post(
    conn: sqlite3.Connection,
    pass_id: str,
    title: str,
    text: str | None,
    url: str | None,
    tags: list[str],
    created_at: str | None = None,
) -> Item:
    item_id = new_item_id()
    created_at = created_at or iso(utc_now())
    with conn:
        conn.execute(
            "INSERT INTO item (id, thread_id, pass_id, title, url, text, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (item_id, item_id, pass_id, title, url, text, created_at),
        )
        for tag in tags:
            conn.execute("INSERT INTO item_tag (item_id, tag) VALUES (?, ?)", (item_id, tag))
        conn.execute(
            "INSERT INTO item_fts (rowid, title, text) VALUES (?, ?, ?)",
            (rowid_of(conn, item_id), *_fts_values(title, text)),
        )
    return get_item(conn, item_id)


def rowid_of(conn: sqlite3.Connection, item_id: str) -> int:
    row = conn.execute("SELECT rowid FROM item WHERE id = ?", (item_id,)).fetchone()
    return row["rowid"]


def create_comment(
    conn: sqlite3.Connection,
    pass_id: str,
    parent: Item,
    text: str,
    private_to: str | None,
    created_at: str | None = None,
) -> Item:
    item_id = new_item_id()
    created_at = created_at or iso(utc_now())
    with conn:
        conn.execute(
            "INSERT INTO item (id, parent_id, thread_id, pass_id, text, created_at, private_to) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (item_id, parent.id, parent.thread_id, pass_id, text, created_at, private_to),
        )
        if private_to is None and parent.private_to is None:
            conn.execute(
                "INSERT INTO item_fts (rowid, title, text) VALUES (?, ?, ?)",
                (rowid_of(conn, item_id), *_fts_values(None, text)),
            )
    return get_item(conn, item_id)


def post_author(conn: sqlite3.Connection, thread_id: str) -> str | None:
    row = conn.execute("SELECT pass_id FROM item WHERE id = ?", (thread_id,)).fetchone()
    return row["pass_id"] if row else None


def increment_views(conn: sqlite3.Connection, item_id: str) -> None:
    conn.execute("UPDATE item SET views = views + 1 WHERE id = ?", (item_id,))
    conn.commit()


def comment_count(conn: sqlite3.Connection, thread_id: str) -> int:
    row = conn.execute(
        "SELECT COUNT(*) AS n FROM item WHERE thread_id = ? AND parent_id IS NOT NULL AND private_to IS NULL",
        (thread_id,),
    ).fetchone()
    return row["n"]


def comment_counts(conn: sqlite3.Connection, thread_ids: list[str]) -> dict[str, int]:
    """Public comment counts for many threads at once."""
    if not thread_ids:
        return {}
    marks = ",".join("?" * len(thread_ids))
    rows = conn.execute(
        f"SELECT thread_id, COUNT(*) AS n FROM item WHERE thread_id IN ({marks}) "
        "AND parent_id IS NOT NULL AND private_to IS NULL GROUP BY thread_id",
        thread_ids,
    ).fetchall()
    return {r["thread_id"]: r["n"] for r in rows}


def with_comment_counts(conn: sqlite3.Connection, items: list[Item]) -> list[Item]:
    counts = comment_counts(conn, [i.thread_id for i in items])
    for item in items:
        item.comment_count = counts.get(item.thread_id, 0)
    return items


def thread_items(conn: sqlite3.Connection, thread_id: str, viewer_pass: str | None) -> list[Item]:
    """The post plus every comment the viewer may see, oldest first per level.

    Private replies are returned only to their author's pass and their recipient;
    for anyone else they and their descendants are absent.
    """
    rows = conn.execute(
        "SELECT * FROM item WHERE thread_id = ? ORDER BY created_at, rowid", (thread_id,)
    ).fetchall()
    items = [_row_to_item(r, item_tags(conn, r["id"])) for r in rows]
    visible_ids = _visible_ids(items, viewer_pass)
    return [i for i in items if i.id in visible_ids]


def _visible_ids(items: list[Item], viewer_pass: str | None) -> set[str]:
    by_id = {i.id: i for i in items}
    visible: set[str] = set()
    for item in items:
        if item.private_to is None:
            visible.add(item.id)
            continue
        if viewer_pass in (item.pass_id, item.private_to):
            visible.add(item.id)
    # A public child of a private parent is only possible if the parent is visible;
    # drop anything whose ancestor chain leaves the visible set.
    def chain_visible(item: Item) -> bool:
        node = item
        while node is not None:
            if node.id not in visible:
                return False
            node = by_id.get(node.parent_id)
        return True

    return {i.id for i in items if chain_visible(i)}


def build_tree(items: list[Item], root_id: str) -> list[dict]:
    """Nests a flat, ordered list into {item, children} nodes.

    Returns the top-level nodes below the root: the root itself is left out,
    since a thread page renders it as the post, not as a comment.
    """
    nodes: dict[str, dict] = {}
    for item in items:
        nodes[item.id] = {"item": item, "children": []}
    for item in items:
        parent = nodes.get(item.parent_id or "")
        if parent is not None:
            parent["children"].append(nodes[item.id])
    return nodes[root_id]["children"] if root_id in nodes else []


# -- listing -------------------------------------------------------------


def _post_where(public_only: bool = True) -> str:
    clauses = ["parent_id IS NULL"]
    if public_only:
        clauses.append("private_to IS NULL")
        clauses.append("NOT (hidden = 1 AND restored = 0)")
    return " AND ".join(clauses)


def posts_between(
    conn: sqlite3.Connection,
    start: date,
    end: date,
    sort: str = "new",
    limit: int | None = None,
    offset: int = 0,
    exclude_pinned: bool = False,
) -> list[Item]:
    """Posts in the 4-day window start..end inclusive, newest/oldest/most viewed."""
    order = {"new": "created_at DESC, rowid DESC", "old": "created_at ASC, rowid ASC", "views": "views DESC, created_at DESC"}[sort]
    lo, hi = iso(day_start(start)), iso(day_start(end + timedelta(days=1)))
    where = _post_where() + " AND created_at >= ? AND created_at < ?"
    params: list = [lo, hi]
    if exclude_pinned:
        where += " AND pinned = 0"
    sql = f"SELECT * FROM item WHERE {where} ORDER BY {order}"
    if limit is not None:
        sql += " LIMIT ? OFFSET ?"
        params += [limit, offset]
    items = [_row_to_item(r, item_tags(conn, r["id"])) for r in conn.execute(sql, params).fetchall()]
    return items


def day_groups(items: list[Item]) -> list[tuple[date, list[Item]]]:
    """Groups posts by their UTC calendar day, preserving the list's order of days."""
    groups: dict[date, list[Item]] = {}
    for item in items:
        groups.setdefault(parse_iso(item.created_at).date(), []).append(item)
    return list(groups.items())


def pinned_posts(conn: sqlite3.Connection) -> list[Item]:
    rows = conn.execute(
        f"SELECT * FROM item WHERE {_post_where()} AND pinned = 1 ORDER BY created_at DESC"
    ).fetchall()
    return [_row_to_item(r, item_tags(conn, r["id"])) for r in rows]


def tagged_posts(conn: sqlite3.Connection, tag: str, sort: str, limit: int = PAGE_SIZE, offset: int = 0) -> list[Item]:
    order = {"new": "i.created_at DESC, i.rowid DESC", "old": "i.created_at ASC, i.rowid ASC", "views": "i.views DESC, i.created_at DESC"}[sort]
    sql = (
        "SELECT i.* FROM item i JOIN item_tag t ON t.item_id = i.id "
        f"WHERE t.tag = ? AND {_post_where()} ORDER BY {order} LIMIT ? OFFSET ?"
    )
    rows = conn.execute(sql, (tag, limit, offset)).fetchall()
    return [_row_to_item(r, item_tags(conn, r["id"])) for r in rows]


def tagged_count(conn: sqlite3.Connection, tag: str) -> int:
    row = conn.execute(
        "SELECT COUNT(*) AS n FROM item_tag t JOIN item i ON i.id = t.item_id "
        "WHERE t.tag = ? AND i.parent_id IS NULL AND i.private_to IS NULL "
        "AND NOT (i.hidden = 1 AND i.restored = 0)",
        (tag,),
    ).fetchone()
    return row["n"]


def tag_counts(conn: sqlite3.Connection) -> list[tuple[str, int]]:
    """Every tag on a visible public post, most used first then alphabetical."""
    rows = conn.execute(
        "SELECT t.tag AS tag, COUNT(*) AS n FROM item_tag t JOIN item i ON i.id = t.item_id "
        "WHERE i.parent_id IS NULL AND i.private_to IS NULL AND NOT (i.hidden = 1 AND i.restored = 0) "
        "GROUP BY t.tag ORDER BY n DESC, t.tag ASC"
    ).fetchall()
    return [(r["tag"], r["n"]) for r in rows]


def has_any_posts(conn: sqlite3.Connection) -> bool:
    row = conn.execute(f"SELECT 1 FROM item WHERE {_post_where()} LIMIT 1").fetchone()
    return row is not None


def first_post_day(conn: sqlite3.Connection) -> date | None:
    row = conn.execute(f"SELECT MIN(created_at) AS m FROM item WHERE {_post_where()}").fetchone()
    return parse_iso(row["m"]).date() if row and row["m"] else None


def latest_post_day(conn: sqlite3.Connection) -> date | None:
    row = conn.execute(f"SELECT MAX(created_at) AS m FROM item WHERE {_post_where()}").fetchone()
    return parse_iso(row["m"]).date() if row and row["m"] else None


def search(
    conn: sqlite3.Connection,
    query: str,
    sort: str = "new",
    limit: int = PAGE_SIZE,
    offset: int = 0,
) -> list[Item]:
    """FTS5 over public titles, text and comments; hidden items excluded."""
    match = _fts_query(query)
    if not match:
        return []
    order = {"new": "i.created_at DESC", "old": "i.created_at ASC", "views": "i.views DESC"}[sort]
    sql = (
        "SELECT i.* FROM item_fts f JOIN item i ON i.rowid = f.rowid "
        "WHERE item_fts MATCH ? AND NOT (i.hidden = 1 AND i.restored = 0) "
        f"ORDER BY {order} LIMIT ? OFFSET ?"
    )
    try:
        rows = conn.execute(sql, (match, limit, offset)).fetchall()
    except sqlite3.OperationalError:
        return []
    items = [_row_to_item(r, item_tags(conn, r["id"])) for r in rows]
    titles = {
        r["id"]: r["title"]
        for r in conn.execute(
            f"SELECT id, title FROM item WHERE id IN ({','.join('?' * len({i.thread_id for i in items}))})",
            list({i.thread_id for i in items}),
        ).fetchall()
    } if items else {}
    for item in items:
        item.thread_title = titles.get(item.thread_id)
    return items


def _fts_query(query: str) -> str:
    """Quotes each term so user input can't inject FTS operators."""
    terms = [t for t in query.replace('"', " ").split() if t]
    if not terms:
        return ""
    return " AND ".join(f'"{t}"' for t in terms)


# -- tags ----------------------------------------------------------------


def normalise_tags(raw: str) -> tuple[list[str], bool]:
    """Returns (tags, too_many). Lowercase, no #, [a-z0-9-], 1-24 chars, deduped."""
    tags: list[str] = []
    for part in raw.split(","):
        tag = part.strip().lstrip("#").lower()
        tag = "".join(c for c in tag if c in "abcdefghijklmnopqrstuvwxyz0123456789-")
        tag = tag[:TAG_MAX_LENGTH]
        if not tag or tag in tags:
            continue
        tags.append(tag)
    return tags[:MAX_TAGS], len(tags) > MAX_TAGS


# -- flags and moderation ------------------------------------------------


def add_flag(conn: sqlite3.Connection, pass_id: str, item_id: str) -> bool:
    """Records one flag per pass; hides the item at 5 flags unless restored."""
    with conn:
        cur = conn.execute("INSERT OR IGNORE INTO flag (pass_id, item_id) VALUES (?, ?)", (pass_id, item_id))
        if cur.rowcount == 0:
            return False
        conn.execute("UPDATE item SET flags = flags + 1 WHERE id = ?", (item_id,))
        conn.execute(
            "UPDATE item SET hidden = 1 WHERE id = ? AND restored = 0 AND flags >= ?",
            (item_id, FLAGS_TO_HIDE),
        )
    return True


def remove_flag(conn: sqlite3.Connection, pass_id: str, item_id: str) -> bool:
    """Takes a pass's flag back; an item hidden by flags comes back once it drops below 5."""
    with conn:
        cur = conn.execute("DELETE FROM flag WHERE pass_id = ? AND item_id = ?", (pass_id, item_id))
        if cur.rowcount == 0:
            return False
        conn.execute("UPDATE item SET flags = flags - 1 WHERE id = ? AND flags > 0", (item_id,))
        conn.execute("UPDATE item SET hidden = 0 WHERE id = ? AND flags < ?", (item_id, FLAGS_TO_HIDE))
    return True


def has_flagged(conn: sqlite3.Connection, pass_id: str, item_id: str) -> bool:
    row = conn.execute("SELECT 1 FROM flag WHERE pass_id = ? AND item_id = ?", (pass_id, item_id)).fetchone()
    return row is not None


def add_moderation_request(conn: sqlite3.Connection, pass_id: str, item_id: str, kind: str) -> bool:
    cur = conn.execute(
        "INSERT OR IGNORE INTO moderation_request (pass_id, item_id, kind) VALUES (?, ?, ?)",
        (pass_id, item_id, kind),
    )
    conn.commit()
    return cur.rowcount > 0


def request_counts(conn: sqlite3.Connection, item_id: str) -> dict[str, int]:
    rows = conn.execute(
        "SELECT kind, COUNT(*) AS n FROM moderation_request WHERE item_id = ? GROUP BY kind", (item_id,)
    ).fetchall()
    return {r["kind"]: r["n"] for r in rows}


def open_requests(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute(
        "SELECT r.item_id, r.kind, COUNT(*) AS n, i.title, i.text FROM moderation_request r "
        "JOIN item i ON i.id = r.item_id GROUP BY r.item_id, r.kind ORDER BY r.item_id"
    ).fetchall()
    return [
        {
            "item_id": r["item_id"],
            "kind": r["kind"],
            "count": r["n"],
            "title": r["title"] or (r["text"] or "")[:60],
        }
        for r in rows
    ]


def hidden_items(conn: sqlite3.Connection) -> list[Item]:
    rows = conn.execute("SELECT * FROM item WHERE hidden = 1 AND restored = 0 ORDER BY created_at DESC").fetchall()
    return [_row_to_item(r) for r in rows]


def unhide(conn: sqlite3.Connection, item_id: str) -> bool:
    with conn:
        cur = conn.execute("UPDATE item SET hidden = 0, restored = 1 WHERE id = ?", (item_id,))
        conn.execute("DELETE FROM moderation_request WHERE item_id = ?", (item_id,))
    return cur.rowcount > 0


def dismiss_requests(conn: sqlite3.Connection, item_id: str) -> bool:
    cur = conn.execute("DELETE FROM moderation_request WHERE item_id = ?", (item_id,))
    conn.commit()
    return cur.rowcount > 0


def set_pinned(conn: sqlite3.Connection, item_id: str, pinned: bool) -> bool:
    cur = conn.execute("UPDATE item SET pinned = ? WHERE id = ? AND parent_id IS NULL", (int(pinned), item_id))
    conn.commit()
    return cur.rowcount > 0


def delete_item(conn: sqlite3.Connection, item_id: str) -> None:
    """Deletes a post and its whole thread, or a comment and its replies."""
    item = get_item(conn, item_id)
    if item is None:
        return
    scope = "thread_id = ?" if item.is_post else "id = ?"
    scope_value = item.thread_id if item.is_post else item_id
    indexed = conn.execute(
        f"SELECT rowid, title, text FROM item WHERE {scope} AND rowid IN (SELECT rowid FROM item_fts)",
        (scope_value,),
    ).fetchall()
    with conn:
        for row in indexed:
            conn.execute("INSERT INTO item_fts (item_fts, rowid, title, text) VALUES ('delete', ?, ?, ?)",
                         (row["rowid"], row["title"] or "", row["text"] or ""))
        conn.execute(f"DELETE FROM item WHERE {scope}", (scope_value,))
        conn.execute("DELETE FROM item_tag WHERE item_id = ?", (item_id,))


def reply_count(conn: sqlite3.Connection, item_id: str) -> int:
    row = conn.execute("SELECT COUNT(*) AS n FROM item WHERE parent_id = ?", (item_id,)).fetchone()
    return row["n"]


# -- reactions -----------------------------------------------------------


def toggle_reaction(conn: sqlite3.Connection, pass_id: str, item_id: str, emoji: str) -> bool:
    """Adds or removes one reaction. Returns True if it is now set."""
    row = conn.execute(
        "SELECT 1 FROM reaction WHERE pass_id = ? AND item_id = ? AND emoji = ?", (pass_id, item_id, emoji)
    ).fetchone()
    with conn:
        if row:
            conn.execute(
                "DELETE FROM reaction WHERE pass_id = ? AND item_id = ? AND emoji = ?", (pass_id, item_id, emoji)
            )
            return False
        conn.execute(
            "INSERT INTO reaction (pass_id, item_id, emoji) VALUES (?, ?, ?)", (pass_id, item_id, emoji)
        )
    return True


def reaction_summary(conn: sqlite3.Connection, item_id: str, viewer_pass: str | None) -> tuple[dict[str, int], set[str]]:
    rows = conn.execute(
        "SELECT emoji, COUNT(*) AS n FROM reaction WHERE item_id = ? GROUP BY emoji", (item_id,)
    ).fetchall()
    counts = {r["emoji"]: r["n"] for r in rows}
    mine: set[str] = set()
    if viewer_pass:
        mine = {
            r["emoji"]
            for r in conn.execute(
                "SELECT emoji FROM reaction WHERE item_id = ? AND pass_id = ?", (item_id, viewer_pass)
            ).fetchall()
        }
    return counts, mine
