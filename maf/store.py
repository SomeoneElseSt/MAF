"""Data access: every read and write the app, CLI, API and MCP make.

One module owns the SQL so the same logic serves the web routes, `maf` and the
read-only API. Functions return plain dicts (or dataclasses where a shape is
shared) so templates and JSON can use them directly.

Privacy notes:
- Nothing here ever stores an email address or anything derived from one.
- Items keep no IP, no user agent, and passes keep no creation time.
"""

import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import date, timedelta

from . import markdown
from .util import day_start, iso, new_item_id, new_pass_id, parse_iso, utc_now

PAGE_SIZE = 30
FOUR_DAYS = 4
FLAGS_TO_HIDE = 5
MAX_TAGS = 3
TAG_MAX_LENGTH = 24
TEXT_PREVIEW = 240
TITLE_MAX = 200
BODY_MAX = 20_000
DELETED_BY_AUTHOR = "Deleted by its author."
# A profile reply that's closed: Unmatch shows MATCH_ENDED to both; Hide leaves the owner nothing to see.
MATCH_ENDED = "This match ended."
HIDDEN_BY_OWNER = "Hidden by the profile's owner."


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
    hidden_reason: str | None = None  # set when the maintainer hid it (maf hide), shown in its place
    restored: int = 0
    pinned: int = 0
    private_to: str | None = None
    sealed: str | None = None
    removed_reason: str | None = None
    edited_at: str | None = None
    nsfw: int = 0
    nsfw_marked: int | None = None
    board: str = "main"
    author_hidden: int = 0
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
        hidden_reason=row["hidden_reason"],
        restored=row["restored"],
        pinned=row["pinned"],
        private_to=row["private_to"],
        sealed=row["sealed"],
        removed_reason=row["removed_reason"],
        edited_at=row["edited_at"],
        nsfw=row["nsfw"],
        nsfw_marked=row["nsfw_marked"],
        board=row["board"],
        author_hidden=row["author_hidden"],
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


def unused_item_id(conn: sqlite3.Connection) -> str:
    while True:
        item_id = new_item_id()
        if conn.execute("SELECT 1 FROM item WHERE id = ?", (item_id,)).fetchone() is None:
            return item_id


def create_post(
    conn: sqlite3.Connection,
    pass_id: str,
    title: str,
    text: str | None,
    url: str | None,
    tags: list[str],
    created_at: str | None = None,
    nsfw: bool = False,
    board: str = "main",
) -> Item:
    """A new post. `nsfw` is the author's answer to "Is NSFW?", kept twice: where it shows, and what was answered."""
    item_id = unused_item_id(conn)
    created_at = created_at or iso(utc_now())
    with conn:
        conn.execute(
            "INSERT INTO item (id, thread_id, pass_id, title, url, text, created_at, nsfw, nsfw_marked, board)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (item_id, item_id, pass_id, title, url, text, created_at, int(nsfw), int(nsfw), board),
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
    text: str | None,
    private_to: str | None,
    created_at: str | None = None,
    sealed: str | None = None,
) -> Item:
    """A sealed (encrypted) private reply is stored with no text at all."""
    item_id = unused_item_id(conn)
    created_at = created_at or iso(utc_now())
    with conn:
        conn.execute(
            "INSERT INTO item (id, parent_id, thread_id, pass_id, text, created_at, private_to, sealed) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (item_id, parent.id, parent.thread_id, pass_id, None if sealed else text, created_at, private_to, sealed),
        )
        if private_to is None and parent.private_to is None:
            conn.execute(
                "INSERT INTO item_fts (rowid, title, text) VALUES (?, ?, ?)",
                (rowid_of(conn, item_id), *_fts_values(None, text)),
            )
    return get_item(conn, item_id)


def thread_keys(conn: sqlite3.Connection, thread_id: str) -> dict[str, str]:
    """Each participant's public key for this thread, by pass id."""
    rows = conn.execute("SELECT pass_id, public_key FROM thread_key WHERE thread_id = ?", (thread_id,)).fetchall()
    return {row["pass_id"]: row["public_key"] for row in rows}


def set_thread_key(conn: sqlite3.Connection, pass_id: str, thread_id: str, public_key: str) -> None:
    conn.execute(
        "INSERT INTO thread_key (pass_id, thread_id, public_key) VALUES (?, ?, ?) "
        "ON CONFLICT (pass_id, thread_id) DO UPDATE SET public_key = excluded.public_key",
        (pass_id, thread_id, public_key),
    )
    conn.commit()


def is_participant(conn: sqlite3.Connection, pass_id: str, thread_id: str) -> bool:
    """True if this pass wrote the post or any comment in the thread."""
    row = conn.execute("SELECT 1 FROM item WHERE thread_id = ? AND pass_id = ? LIMIT 1", (thread_id, pass_id)).fetchone()
    return row is not None


def post_author(conn: sqlite3.Connection, thread_id: str) -> str | None:
    row = conn.execute("SELECT pass_id FROM item WHERE id = ?", (thread_id,)).fetchone()
    return row["pass_id"] if row else None


def increment_views(conn: sqlite3.Connection, item_id: str) -> None:
    conn.execute("UPDATE item SET views = views + 1 WHERE id = ?", (item_id,))
    conn.commit()


def comment_count(conn: sqlite3.Connection, thread_id: str) -> int:
    row = conn.execute(
        "SELECT COUNT(*) AS n FROM item WHERE thread_id = ? AND parent_id IS NOT NULL AND private_to IS NULL "
        "AND removed_reason IS NULL",  # a deleted or removed reply's note isn't a comment
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
        "AND parent_id IS NOT NULL AND private_to IS NULL AND removed_reason IS NULL GROUP BY thread_id",
        thread_ids,
    ).fetchall()
    return {r["thread_id"]: r["n"] for r in rows}


def latest_comment_times(conn: sqlite3.Connection, thread_ids: list[str], not_by: str | None = None) -> dict[str, str]:
    """When each thread last got a comment, by thread id (public comments only, like the counts).
    With not_by, that pass's own comments don't count: your own comment isn't news to you."""
    if not thread_ids:
        return {}
    marks = ",".join("?" * len(thread_ids))
    rows = conn.execute(
        f"SELECT thread_id, MAX(created_at) AS latest FROM item WHERE thread_id IN ({marks}) "
        "AND parent_id IS NOT NULL AND private_to IS NULL AND removed_reason IS NULL AND pass_id IS NOT ? GROUP BY thread_id",
        [*thread_ids, not_by],
    ).fetchall()
    return {row["thread_id"]: row["latest"] for row in rows}


NEW_ACTIVITY_LIMIT = 100


def new_activity(conn: sqlite3.Connection, viewer_pass: str, since: str, nsfw: bool = False) -> list[Item]:
    """Listed posts with something new since `since` for this pass: posted by someone else after it, or
    commented on by someone else after it. Pinned posts never count (they have their own section). Newest activity first. The browser decides which of these the
    person has already opened (that stays in the browser)."""
    rows = conn.execute(
        "SELECT * FROM ("
        "  SELECT i.*, (SELECT MAX(c.created_at) FROM item c WHERE c.thread_id = i.id AND c.parent_id IS NOT NULL"
        "    AND c.private_to IS NULL AND c.removed_reason IS NULL AND c.pass_id IS NOT ?) AS latest_other"
        "  FROM item i WHERE i.parent_id IS NULL AND i.private_to IS NULL AND i.removed_reason IS NULL"
        "    AND NOT (i.hidden = 1 AND i.restored = 0) AND i.author_hidden = 0 AND i.nsfw = ? AND i.board = 'main'"
        ") WHERE (pass_id IS NOT ? AND created_at > ?) OR latest_other > ? "
        "ORDER BY MAX(created_at, COALESCE(latest_other, '')) DESC LIMIT ?",
        (viewer_pass, int(nsfw), viewer_pass, since, since, NEW_ACTIVITY_LIMIT),
    ).fetchall()
    return [_row_to_item(r) for r in rows]


def is_subscribed(conn: sqlite3.Connection, pass_id: str | None, thread_id: str) -> bool:
    if pass_id is None:
        return False
    row = conn.execute("SELECT 1 FROM subscription WHERE pass_id = ? AND thread_id = ?", (pass_id, thread_id)).fetchone()
    return row is not None


def set_subscribed(conn: sqlite3.Connection, pass_id: str, thread_id: str, subscribed: bool) -> None:
    with conn:
        if subscribed:
            conn.execute("INSERT OR IGNORE INTO subscription (pass_id, thread_id) VALUES (?, ?)", (pass_id, thread_id))
        else:
            conn.execute("DELETE FROM subscription WHERE pass_id = ? AND thread_id = ?", (pass_id, thread_id))


def subscribers(conn: sqlite3.Connection, thread_id: str) -> list[str]:
    """Everyone following this post, the post's author first."""
    rows = conn.execute(
        "SELECT s.pass_id FROM subscription s JOIN item i ON i.id = s.thread_id "
        "WHERE s.thread_id = ? ORDER BY s.pass_id = i.pass_id DESC", (thread_id,)
    ).fetchall()
    return [r["pass_id"] for r in rows]


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


MAIN = "main"
BOARDS = (MAIN, "dates")  # the front page, and the Dates page


def _post_where(public_only: bool = True, nsfw: bool = False, board: str = MAIN) -> str:
    """Listed posts on one page. On the front page, one side: NSFW posts only with NSFW on, the rest only
    with it off. The Dates page shows its own posts whichever side you're on."""
    assert board in BOARDS
    clauses = ["parent_id IS NULL", f"board = '{board}'"]
    if board == MAIN:
        clauses.append(f"nsfw = {int(nsfw)}")
    if public_only:
        clauses.append("private_to IS NULL")
        clauses.append("NOT (hidden = 1 AND restored = 0)")
        clauses.append("author_hidden = 0")
    return " AND ".join(clauses)


def posts_between(
    conn: sqlite3.Connection,
    start: date,
    end: date,
    sort: str = "new",
    limit: int | None = None,
    offset: int = 0,
    exclude_pinned: bool = False,
    nsfw: bool = False,
) -> list[Item]:
    """Posts in the 4-day window start..end inclusive, newest/oldest/most viewed."""
    order = {"new": "created_at DESC, rowid DESC", "old": "created_at ASC, rowid ASC", "views": "views DESC, created_at DESC"}[sort]
    lo, hi = iso(day_start(start)), iso(day_start(end + timedelta(days=1)))
    where = _post_where(nsfw=nsfw) + " AND created_at >= ? AND created_at < ?"
    params: list = [lo, hi]
    if exclude_pinned:
        where += " AND pinned = 0"
    sql = f"SELECT * FROM item WHERE {where} ORDER BY {order}"
    if limit is not None:
        sql += " LIMIT ? OFFSET ?"
        params += [limit, offset]
    items = [_row_to_item(r, item_tags(conn, r["id"])) for r in conn.execute(sql, params).fetchall()]
    return items


def is_profile(post: Item) -> bool:
    """A profile is a Dates post that isn't pinned. Pinned Dates posts are the maintainer's notes, with normal replies."""
    return post.board == "dates" and not post.pinned


def own_profile(conn: sqlite3.Connection, pass_id: str | None) -> Item | None:
    """This pass's profile (is_profile: a Dates post of its own that isn't pinned), if it has one."""
    if pass_id is None:
        return None
    row = conn.execute(
        f"SELECT id FROM item WHERE {_post_where(board='dates')} AND pinned = 0 AND pass_id = ? LIMIT 1", (pass_id,)
    ).fetchone()
    return get_item(conn, row["id"]) if row else None


def has_profile(conn: sqlite3.Connection, pass_id: str | None) -> bool:
    return own_profile(conn, pass_id) is not None


def board_posts(conn: sqlite3.Connection, board: str, sort: str = "new", limit: int = PAGE_SIZE) -> list[Item]:
    """A board's listed posts, newest, oldest or most viewed first, pinned ones left out (they show above)."""
    order = {"new": "created_at DESC, rowid DESC", "old": "created_at ASC, rowid ASC", "views": "views DESC, created_at DESC"}[sort]
    rows = conn.execute(
        f"SELECT * FROM item WHERE {_post_where(board=board)} AND pinned = 0 ORDER BY {order} LIMIT ?",
        (limit,),
    ).fetchall()
    return [_row_to_item(r, item_tags(conn, r["id"])) for r in rows]


def day_groups(items: list[Item]) -> list[tuple[date, list[Item]]]:
    """Groups posts by their UTC calendar day, preserving the list's order of days."""
    groups: dict[date, list[Item]] = {}
    for item in items:
        groups.setdefault(parse_iso(item.created_at).date(), []).append(item)
    return list(groups.items())


def pinned_posts(conn: sqlite3.Connection, nsfw: bool = False, board: str = MAIN) -> list[Item]:
    rows = conn.execute(
        f"SELECT * FROM item WHERE {_post_where(nsfw=nsfw, board=board)} AND pinned = 1 ORDER BY created_at DESC"
    ).fetchall()
    return [_row_to_item(r, item_tags(conn, r["id"])) for r in rows]


def tagged_posts(conn: sqlite3.Connection, tag: str, sort: str, limit: int = PAGE_SIZE, offset: int = 0,
                 nsfw: bool = False) -> list[Item]:
    order = {"new": "i.created_at DESC, i.rowid DESC", "old": "i.created_at ASC, i.rowid ASC", "views": "i.views DESC, i.created_at DESC"}[sort]
    sql = (
        "SELECT i.* FROM item i JOIN item_tag t ON t.item_id = i.id "
        f"WHERE t.tag = ? AND {_post_where(nsfw=nsfw)} ORDER BY {order} LIMIT ? OFFSET ?"
    )
    rows = conn.execute(sql, (tag, limit, offset)).fetchall()
    return [_row_to_item(r, item_tags(conn, r["id"])) for r in rows]


def tagged_count(conn: sqlite3.Connection, tag: str, nsfw: bool = False) -> int:
    row = conn.execute(
        "SELECT COUNT(*) AS n FROM item_tag t JOIN item i ON i.id = t.item_id "
        "WHERE t.tag = ? AND i.parent_id IS NULL AND i.private_to IS NULL "
        "AND NOT (i.hidden = 1 AND i.restored = 0) AND i.author_hidden = 0 AND i.nsfw = ? AND i.board = 'main'",
        (tag, int(nsfw)),
    ).fetchone()
    return row["n"]


def tag_counts(conn: sqlite3.Connection, nsfw: bool = False) -> list[tuple[str, int]]:
    """Every tag on a visible public post on this side, most used first then alphabetical."""
    rows = conn.execute(
        "SELECT t.tag AS tag, COUNT(*) AS n FROM item_tag t JOIN item i ON i.id = t.item_id "
        "WHERE i.parent_id IS NULL AND i.private_to IS NULL AND NOT (i.hidden = 1 AND i.restored = 0) AND i.author_hidden = 0 "
        "AND i.nsfw = ? AND i.board = 'main' GROUP BY t.tag ORDER BY n DESC, t.tag ASC",
        (int(nsfw),),
    ).fetchall()
    return [(r["tag"], r["n"]) for r in rows]


def has_any_posts(conn: sqlite3.Connection, nsfw: bool = False) -> bool:
    row = conn.execute(f"SELECT 1 FROM item WHERE {_post_where(nsfw=nsfw)} LIMIT 1").fetchone()
    return row is not None


def first_post_day(conn: sqlite3.Connection, nsfw: bool = False) -> date | None:
    row = conn.execute(f"SELECT MIN(created_at) AS m FROM item WHERE {_post_where(nsfw=nsfw)}").fetchone()
    return parse_iso(row["m"]).date() if row and row["m"] else None


def latest_post_day(conn: sqlite3.Connection, nsfw: bool = False) -> date | None:
    row = conn.execute(f"SELECT MAX(created_at) AS m FROM item WHERE {_post_where(nsfw=nsfw)}").fetchone()
    return parse_iso(row["m"]).date() if row and row["m"] else None


def search(
    conn: sqlite3.Connection,
    query: str,
    sort: str = "new",
    limit: int = PAGE_SIZE,
    offset: int = 0,
    nsfw: bool = False,
) -> list[Item]:
    """FTS5 over public titles, text and comments on this side (a comment's side is its post's); hidden items excluded.
    Matching posts come first, then matching comments, each in the chosen order."""
    match = _fts_query(query)
    if not match:
        return []
    order = {"new": "i.created_at DESC", "old": "i.created_at ASC", "views": "i.views DESC"}[sort]
    sql = (
        "SELECT i.* FROM item_fts f JOIN item i ON i.rowid = f.rowid JOIN item p ON p.id = i.thread_id "
        "WHERE item_fts MATCH ? AND NOT (i.hidden = 1 AND i.restored = 0) AND p.author_hidden = 0 AND p.nsfw = ? AND p.board = 'main' "
        f"ORDER BY i.parent_id IS NOT NULL, {order} LIMIT ? OFFSET ?"
    )
    try:
        rows = conn.execute(sql, (match, int(nsfw), limit, offset)).fetchall()
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
    """Takes a pass's flag back; an item hidden by flags comes back once it drops below 5 (not one the maintainer hid)."""
    with conn:
        cur = conn.execute("DELETE FROM flag WHERE pass_id = ? AND item_id = ?", (pass_id, item_id))
        if cur.rowcount == 0:
            return False
        conn.execute("UPDATE item SET flags = flags - 1 WHERE id = ? AND flags > 0", (item_id,))
        conn.execute("UPDATE item SET hidden = 0 WHERE id = ? AND flags < ? AND hidden_reason IS NULL", (item_id, FLAGS_TO_HIDE))
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


def hide(conn: sqlite3.Connection, item_id: str, reason: str) -> bool:
    """The maintainer hides an item: it's unlisted like one hidden by flags, with the reason shown in its place.
    Undone with unhide. Unflagging doesn't bring it back."""
    with conn:
        cur = conn.execute("UPDATE item SET hidden = 1, restored = 0, hidden_reason = ? WHERE id = ?", (reason, item_id))
    return cur.rowcount > 0


def unhide(conn: sqlite3.Connection, item_id: str) -> bool:
    with conn:
        cur = conn.execute("UPDATE item SET hidden = 0, restored = 1, hidden_reason = NULL WHERE id = ?", (item_id,))
        conn.execute("DELETE FROM moderation_request WHERE item_id = ?", (item_id,))
    return cur.rowcount > 0


@contextmanager
def _secure_delete(conn: sqlite3.Connection):
    """Deleted words are overwritten in the database file (and the WAL is folded in), not just unlinked.
    Older backups still have them."""
    conn.execute("PRAGMA secure_delete = ON")
    try:
        yield
    finally:
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        conn.execute("PRAGMA secure_delete = OFF")


def remove_comment(conn: sqlite3.Connection, item_id: str, reason: str) -> bool:
    """Deletes a comment's words for good and shows `reason` in their place. Replies stay."""
    item = get_item(conn, item_id)
    if item is None or item.is_post:
        return False
    indexed = conn.execute(
        "SELECT rowid, title, text FROM item WHERE id = ? AND rowid IN (SELECT rowid FROM item_fts)", (item_id,)
    ).fetchone()
    with _secure_delete(conn), conn:
        if indexed:
            conn.execute("INSERT INTO item_fts (item_fts, rowid, title, text) VALUES ('delete', ?, ?, ?)",
                         (indexed["rowid"], indexed["title"] or "", indexed["text"] or ""))
        conn.execute("UPDATE item SET text = NULL, sealed = NULL, removed_reason = ? WHERE id = ?", (reason, item_id))
        conn.execute("DELETE FROM reaction WHERE item_id = ?", (item_id,))
        conn.execute("DELETE FROM moderation_request WHERE item_id = ?", (item_id,))
    return True


def delete_own_comment(conn: sqlite3.Connection, item_id: str) -> None:
    """The author deletes their reply: gone entirely, or "Deleted by its author." if others replied to it."""
    if reply_count(conn, item_id):
        remove_comment(conn, item_id, DELETED_BY_AUTHOR)
        return
    with _secure_delete(conn):
        delete_item(conn, item_id)


# -- edits -----------------------------------------------------------------


def edit_item(conn: sqlite3.Connection, item_id: str, text: str | None, sealed: str | None = None,
              title: str | None = None) -> None:
    """Replaces an item's words (and a post's title, if given) and notes when. The search index follows."""
    item = get_item(conn, item_id)
    if item is None:
        return
    indexed = conn.execute(
        "SELECT rowid FROM item WHERE id = ? AND rowid IN (SELECT rowid FROM item_fts)", (item_id,)
    ).fetchone()
    with _secure_delete(conn), conn:
        if indexed:
            conn.execute("INSERT INTO item_fts (item_fts, rowid, title, text) VALUES ('delete', ?, ?, ?)",
                         (indexed["rowid"], *_fts_values(item.title, item.text)))
        title = title or item.title
        conn.execute("UPDATE item SET title = ?, text = ?, sealed = ?, edited_at = ? WHERE id = ?",
                     (title, text, sealed, iso(utc_now()), item_id))
        if indexed and not item.private_to and text is not None:
            conn.execute("INSERT INTO item_fts (rowid, title, text) VALUES (?, ?, ?)",
                         (indexed["rowid"], *_fts_values(title, text)))


def dismiss_requests(conn: sqlite3.Connection, item_id: str) -> bool:
    cur = conn.execute("DELETE FROM moderation_request WHERE item_id = ?", (item_id,))
    conn.commit()
    return cur.rowcount > 0


def set_nsfw(conn: sqlite3.Connection, item_id: str, nsfw: bool) -> bool:
    """The maintainer moves a post to NSFW or back. Its author's answer (nsfw_marked) is kept, so the move
    stays on record as a correction. False if there's no such post."""
    with conn:
        cur = conn.execute("UPDATE item SET nsfw = ? WHERE id = ? AND parent_id IS NULL", (int(nsfw), item_id))
    return cur.rowcount > 0


def set_board(conn: sqlite3.Connection, item_id: str, board: str) -> bool:
    """The maintainer moves a post (its replies follow) to the front page or the Dates page. False if there's
    no such post."""
    assert board in BOARDS
    with conn:
        cur = conn.execute("UPDATE item SET board = ? WHERE id = ? AND parent_id IS NULL", (board, item_id))
    return cur.rowcount > 0


def set_author_hidden(conn: sqlite3.Connection, item_id: str, hidden: bool) -> None:
    """The author's Hide Post: off every list and search, the link still works. Unhide brings it back."""
    with conn:
        conn.execute("UPDATE item SET author_hidden = ? WHERE id = ?", (int(hidden), item_id))


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
        # A post's replies go with it, and each reply's words go for good (secure_delete is still on).
        conn.execute(f"DELETE FROM item WHERE {scope}", (scope_value,))
        conn.execute("DELETE FROM item_tag WHERE item_id = ?", (item_id,))
        if item.is_post:
            conn.execute("DELETE FROM thread_key WHERE thread_id = ?", (item.thread_id,))


def close_profile_reply(conn: sqlite3.Connection, reply_id: str, reason: str) -> None:
    """Unmatch or Hide: the conversation under a profile reply is erased for good, and `reason` takes the
    reply's place. The reply stays (without its words) so its sender can't send their profile again."""
    under = [row["id"] for row in conn.execute(
        "WITH RECURSIVE below(id) AS (SELECT id FROM item WHERE parent_id = ?"
        " UNION ALL SELECT i.id FROM item i JOIN below ON i.parent_id = below.id) SELECT id FROM below", (reply_id,))]
    with _secure_delete(conn), conn:
        for item_id in under:
            conn.execute("DELETE FROM item WHERE id = ?", (item_id,))
            conn.execute("DELETE FROM reaction WHERE item_id = ?", (item_id,))
    remove_comment(conn, reply_id, reason)


def close_sent_profiles(conn: sqlite3.Connection, pass_id: str) -> None:
    """Deleting your profile takes back the copies you sent: a match ends, one not yet matched just goes."""
    rows = conn.execute(
        "SELECT r.id, EXISTS (SELECT 1 FROM item c WHERE c.parent_id = r.id) AS matched FROM item r"
        " JOIN item p ON p.id = r.parent_id WHERE r.pass_id = ? AND p.board = 'dates' AND p.pinned = 0"
        " AND p.parent_id IS NULL AND r.removed_reason IS NULL", (pass_id,)).fetchall()
    for row in rows:
        close_profile_reply(conn, row["id"], MATCH_ENDED if row["matched"] else HIDDEN_BY_OWNER)


def delete_own_post(conn: sqlite3.Connection, item_id: str) -> None:
    """The author deletes their post, and its thread with it; the words are overwritten, not just unlinked."""
    with _secure_delete(conn):
        delete_item(conn, item_id)


def reply_count(conn: sqlite3.Connection, item_id: str) -> int:
    row = conn.execute("SELECT COUNT(*) AS n FROM item WHERE parent_id = ?", (item_id,)).fetchone()
    return row["n"]


# -- descriptive statistics ----------------------------------------------


@dataclass
class Metric:
    """One number about the site, plus how much of it is new since a moment (None when unknown)."""

    name: str
    total: int
    recent: int | None = None


def _count(conn: sqlite3.Connection, sql: str, params: tuple = ()) -> int:
    return conn.execute(sql, params).fetchone()[0]


def site_stats(conn: sqlite3.Connection, since: str) -> list[Metric]:
    """Descriptive counts of the site. Only rows that carry a time can have a delta (`since`):
    passes have none, and a reaction from before reaction times were kept has none either."""

    def metric(name: str, sql: str, recent_sql: str | None = None) -> Metric:
        recent = _count(conn, recent_sql, (since,)) if recent_sql else None
        return Metric(name, _count(conn, sql), recent)

    public = "parent_id IS NULL AND private_to IS NULL AND removed_reason IS NULL"
    reply = "parent_id IS NOT NULL AND private_to IS NULL AND removed_reason IS NULL"
    return [
        metric("passes", "SELECT COUNT(*) FROM pass"),
        metric("people with a post", "SELECT COUNT(DISTINCT pass_id) FROM item WHERE parent_id IS NULL"),
        metric("posts", f"SELECT COUNT(*) FROM item WHERE {public}",
               f"SELECT COUNT(*) FROM item WHERE {public} AND created_at >= ?"),
        # Views aren't timed (a count on each post), so they have no delta.
        metric("post views", "SELECT COALESCE(SUM(views), 0) FROM item WHERE parent_id IS NULL"),
        metric("replies", f"SELECT COUNT(*) FROM item WHERE {reply}",
               f"SELECT COUNT(*) FROM item WHERE {reply} AND created_at >= ?"),
        metric("private replies", "SELECT COUNT(*) FROM item WHERE private_to IS NOT NULL",
               "SELECT COUNT(*) FROM item WHERE private_to IS NOT NULL AND created_at >= ?"),
        metric("reactions", "SELECT COUNT(*) FROM reaction",
               "SELECT COUNT(*) FROM reaction WHERE created_at >= ?"),
        metric("tags", "SELECT COUNT(*) FROM item_tag"),
        metric("subscriptions", "SELECT COUNT(*) FROM subscription"),
        metric("push devices", "SELECT COUNT(*) FROM push_device"),
        metric("hidden", "SELECT COUNT(*) FROM item WHERE hidden = 1 AND restored = 0"),
        metric("open requests", "SELECT COUNT(*) FROM moderation_request"),
    ]


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
            "INSERT INTO reaction (pass_id, item_id, emoji, created_at) VALUES (?, ?, ?, ?)",
            (pass_id, item_id, emoji, iso(utc_now())),
        )
    return True


# -- notifications ---------------------------------------------------------

NOTIFICATIONS_SHOWN = 30
SNIPPET_LENGTH = 60


def _snippet(row: sqlite3.Row) -> str:
    """Your own post's title or the first words of your own reply, to say which one it's about."""
    if row["t_title"]:
        return markdown.plain(row["t_title"])
    if row["t_sealed"]:
        return "your private reply"
    text = markdown.plain(row["t_text"])
    return text if len(text) <= SNIPPET_LENGTH else text[:SNIPPET_LENGTH].rstrip() + "…"


def _reply_label(row: sqlite3.Row) -> str:
    """What a reply says in the Feed. On Dates: someone's profile sent to yours, or a match (the owner's first
    message under the profile you sent)."""
    if row["on_profile"] and row["on_post"]:
        return "Someone replied with their profile"
    if row["on_profile"] and row["first_from_owner"]:
        return "Someone matched with you"
    if row["on_profile"]:
        return "New message from your match"
    return f"New reply to your {'post' if row['on_post'] else 'comment'}"


def _reply_about(row: sqlite3.Row) -> str:
    """Which post or reply it's about. On Dates, the profile's title: a profile reply's own words are its answers."""
    return markdown.plain(row["p_title"]) if row["on_profile"] else _snippet(row)


def add_push_device(conn: sqlite3.Connection, pass_id: str, endpoint: str, p256dh: str, auth: str) -> None:
    """Turns alerts on for one device. The same device signing in with another pass moves to that pass."""
    with conn:
        conn.execute(
            "INSERT INTO push_device (endpoint, pass_id, p256dh, auth) VALUES (?, ?, ?, ?) "
            "ON CONFLICT(endpoint) DO UPDATE SET pass_id = excluded.pass_id, p256dh = excluded.p256dh, auth = excluded.auth",
            (endpoint, pass_id, p256dh, auth),
        )


def remove_push_device(conn: sqlite3.Connection, endpoint: str, pass_id: str | None = None) -> None:
    """Turns alerts off for one device (only the owning pass's, when given)."""
    with conn:
        if pass_id is None:
            conn.execute("DELETE FROM push_device WHERE endpoint = ?", (endpoint,))
        else:
            conn.execute("DELETE FROM push_device WHERE endpoint = ? AND pass_id = ?", (endpoint, pass_id))


def push_devices(conn: sqlite3.Connection, pass_id: str) -> list[dict]:
    rows = conn.execute("SELECT endpoint, p256dh, auth FROM push_device WHERE pass_id = ?", (pass_id,)).fetchall()
    return [dict(r) for r in rows]


def reply_alerts(conn: sqlite3.Connection, reply: Item) -> dict[str, str]:
    """Who gets an alert for a new reply, and what it says: the same people and wording as their Feed.
    The author of what it answers gets the reply line ("New reply to your post", a match on Dates); people
    subscribed to the post get "New activity on a post you subscribed to" for public replies. Never the replier."""
    parent = get_item(conn, reply.parent_id)
    post = get_item(conn, reply.thread_id)
    if parent is None or post is None:
        return {}
    alerts: dict[str, str] = {}
    if reply.private_to is None:
        for pass_id in subscribers(conn, reply.thread_id):
            alerts[pass_id] = "New activity on a post you subscribed to"
    if reply.private_to in (None, parent.pass_id):
        on_profile = post.board == "dates" and not post.pinned
        first_from_owner = (
            reply.pass_id == post.pass_id and parent.parent_id == post.id
            and conn.execute("SELECT id FROM item WHERE parent_id = ? AND pass_id = ? ORDER BY created_at, id LIMIT 1",
                             (parent.id, post.pass_id)).fetchone()["id"] == reply.id
        )
        alerts[parent.pass_id] = _reply_label({"on_post": parent.parent_id is None, "on_profile": on_profile,
                                               "first_from_owner": first_from_owner})
    alerts.pop(reply.pass_id, None)
    return alerts


def notifications(conn: sqlite3.Connection, pass_id: str) -> list[dict]:
    """What's new on your posts and replies, newest first: replies from others, others' reactions
    (grouped per post or reply, with each reaction's time so the browser can count the new ones), and
    everything new on posts you subscribed to. Replies you can't see, removed or in-review replies,
    and your own activity never appear."""
    replies = conn.execute(
        "SELECT c.id, c.thread_id, c.created_at, t.parent_id IS NULL AS on_post, "
        "t.title AS t_title, t.text AS t_text, t.sealed AS t_sealed, "
        # Dates: the profile it's on, and whether this is the profile's owner first answering your profile (a match)
        "p.title AS p_title, p.board = 'dates' AND p.pinned = 0 AS on_profile, "
        "c.pass_id = p.pass_id AND t.parent_id = p.id AND c.id = (SELECT f.id FROM item f WHERE f.parent_id = t.id "
        "  AND f.pass_id = p.pass_id ORDER BY f.created_at, f.id LIMIT 1) AS first_from_owner "
        "FROM item c JOIN item t ON t.id = c.parent_id JOIN item p ON p.id = c.thread_id "
        "WHERE t.pass_id = ? AND c.pass_id != ? AND (c.private_to IS NULL OR c.private_to = ?) "
        "AND c.removed_reason IS NULL AND NOT (c.hidden = 1 AND c.restored = 0) AND t.removed_reason IS NULL "
        "ORDER BY c.created_at DESC LIMIT ?",
        (pass_id, pass_id, pass_id, NOTIFICATIONS_SHOWN),
    ).fetchall()
    reactions = conn.execute(
        "SELECT t.id, t.thread_id, t.parent_id IS NULL AS on_post, t.title AS t_title, t.text AS t_text, "
        "t.sealed AS t_sealed, GROUP_CONCAT(r.created_at, ' ') AS times, GROUP_CONCAT(r.emoji, ' ') AS emoji, "
        "MAX(r.created_at) AS latest "
        "FROM reaction r JOIN item t ON t.id = r.item_id "
        "WHERE t.pass_id = ? AND r.pass_id != ? AND r.created_at IS NOT NULL AND t.removed_reason IS NULL "
        "GROUP BY t.id ORDER BY latest DESC LIMIT ?",
        (pass_id, pass_id, NOTIFICATIONS_SHOWN),
    ).fetchall()
    followed = conn.execute(
        "SELECT c.id, c.thread_id, c.created_at, c.parent_id, t.title AS t_title, t.text AS t_text, t.sealed AS t_sealed "
        "FROM subscription s JOIN item c ON c.thread_id = s.thread_id JOIN item t ON t.id = c.id "
        "WHERE s.pass_id = ? AND c.id != c.thread_id AND c.pass_id != ? AND c.removed_reason IS NULL "
        "AND NOT (c.hidden = 1 AND c.restored = 0) AND (c.private_to IS NULL OR c.private_to = ?) "
        "ORDER BY c.created_at DESC LIMIT ?",
        (pass_id, pass_id, pass_id, NOTIFICATIONS_SHOWN),
    ).fetchall()
    found = [
        {"kind": "activity", "on": "post" if not f["parent_id"] else "comment", "about": _snippet(f),
         "label": "New activity on a post you subscribed to",
         "url": f"/thread/{f['thread_id']}#{f['id']}", "at": f["created_at"], "times": [f["created_at"]]}
        for f in followed
    ] + [
        {"kind": "reply", "on": "post" if r["on_post"] else "comment", "about": _reply_about(r), "label": _reply_label(r),
         "url": f"/thread/{r['thread_id']}#{r['id']}", "at": r["created_at"], "times": [r["created_at"]]}
        for r in replies
    ] + [
        {"kind": "reactions", "on": "post" if r["on_post"] else "comment", "about": _snippet(r),
         "url": f"/thread/{r['thread_id']}" + ("" if r["on_post"] else f"#{r['id']}"), "at": r["latest"],
         "times": r["times"].split(" "), "emoji": list(dict.fromkeys(r["emoji"].split(" ")))}
        for r in reactions
    ]
    for n in found:
        if n["kind"] == "reactions":
            count = len(n["times"])
            n["label"] = f"{' '.join(n['emoji'])} {count} reaction{'' if count == 1 else 's'} on your {n['on']}"
    found.sort(key=lambda n: n["at"], reverse=True)
    return found[:NOTIFICATIONS_SHOWN]


def latest_reactions(conn: sqlite3.Connection, item_id: str, not_by: str | None) -> dict[str, str]:
    """When each emoji on an item was last added by someone other than `not_by`, so a returning reader's
    browser can highlight emoji added since their last visit."""
    rows = conn.execute(
        "SELECT emoji, MAX(created_at) AS latest FROM reaction WHERE item_id = ? AND pass_id IS NOT ? GROUP BY emoji",
        (item_id, not_by),
    ).fetchall()
    return {r["emoji"]: r["latest"] for r in rows}


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
