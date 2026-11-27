"""The maintainer CLI: `maf <command>` on the server over SSH.

Stdlib only (argparse + sqlite3) and it reuses maf.store for the same logic the
site uses. There are no admin roles or buttons: this is the only moderation
tool.
"""

import argparse
import os
import sqlite3
import sys
from pathlib import Path

from . import store
from .settings import load_settings

# The site's settings file (systemd reads it for the running app). An SSH shell doesn't, so without
# it the CLI would open an empty database in the current folder and every id would look missing.
SITE_ENV = Path("/etc/maf/env")


def _load_env() -> None:
    """Fills in settings from the site's env file, never overriding ones already set."""
    if not SITE_ENV.is_file():
        return
    for line in SITE_ENV.read_text().splitlines():
        name, _, value = line.strip().partition("=")
        if name and not name.startswith("#") and name not in os.environ:
            os.environ[name] = value.strip().strip('"').strip("'")


def _connect():
    from .db import connect, migrate

    _load_env()
    settings = load_settings()
    if not settings.database_path.exists():
        raise SystemExit(f"No database at {settings.database_path}. Set MAF_DATABASE to the site's database.")
    conn = connect(settings.database_path)
    migrate(conn)
    return conn


def _table(rows: list[list[str]], headers: list[str]) -> str:
    widths = [max(len(str(h)), *(len(str(r[i])) for r in rows)) if rows else len(h) for i, h in enumerate(headers)]
    line = "  ".join(h.ljust(w) for h, w in zip(headers, widths))
    out = [line, "  ".join("-" * w for w in widths)]
    out += ["  ".join(str(cell).ljust(w) for cell, w in zip(row, widths)) for row in rows]
    return "\n".join(out)


DEFAULT_REMOVE_REASON = "Removed because it named someone."
DEFAULT_HIDE_REASON = "Hidden because it mentioned someone."


def _missing(item_id: str) -> int:
    print(f"No item {item_id}")
    return 1


def cmd_usage(conn: sqlite3.Connection, args) -> int:
    """How many times each API endpoint has been called, from the usage log file."""
    from .usage import usage

    _load_env()
    print(usage(load_settings().usage_log_path))
    return 0


STATS_DELTA_HOURS = 12


def _signed(n: int) -> str:
    return f"+{n}" if n > 0 else ("0" if n == 0 else str(n))


def cmd_stats(conn: sqlite3.Connection, args) -> int:
    """Descriptive counts of the site, with how much of each is new in the last 12 hours."""
    from datetime import UTC, datetime, timedelta

    from .util import iso

    since = iso(datetime.now(UTC) - timedelta(hours=STATS_DELTA_HOURS))
    rows = [[m.name, str(m.total), "-" if m.recent is None else _signed(m.recent)]
            for m in store.site_stats(conn, since)]
    print(_table(rows, ["metric", "total", f"last {STATS_DELTA_HOURS}h"]))
    return 0


def cmd_requests(conn: sqlite3.Connection, args) -> int:
    rows = store.open_requests(conn)
    if not rows:
        print("No open requests.")
        return 0
    print(_table([[r["item_id"], r["title"], r["kind"], r["count"]] for r in rows],
                 ["id", "title", "kind", "count"]))
    return 0


def cmd_hidden(conn: sqlite3.Connection, args) -> int:
    items = store.hidden_items(conn)
    if not items:
        print("No hidden items.")
        return 0
    print(_table([[i.id, i.title or (i.text or "")[:60], str(i.flags)] for i in items],
                 ["id", "title", "flags"]))
    return 0


def cmd_show(conn: sqlite3.Connection, args) -> int:
    item = store.get_item(conn, args.id)
    if item is None:
        return _missing(args.id)
    counts = store.request_counts(conn, item.id)
    print(item.id)
    print(f"  title:    {item.title or '(comment)'}")
    if item.url:
        print(f"  url:      {item.url}")
    if item.text:
        print(f"  text:     {item.text[:400]}")
    print(f"  created:  {item.created_at}")
    print(f"  flags:    {item.flags}")
    print(f"  hidden:   {bool(item.hidden)}  restored: {bool(item.restored)}  pinned: {bool(item.pinned)}")
    print(f"  requests: unhide {counts.get('unhide', 0)}, nuke {counts.get('nuke', 0)}")
    return 0


def _id_from(address: str) -> str:
    """An item id from an id, a thread address, or a reply's address (…/thread/<post>#reply-<id>)."""
    if "#" in address:
        return address.rsplit("#", 1)[1].removeprefix("reply-")
    return address.rstrip("/").rsplit("/", 1)[-1]


def cmd_hide(conn: sqlite3.Connection, args) -> int:
    """Doesn't print the item: whoever runs it never needs to read it."""
    item_id = _id_from(args.id)
    if not store.hide(conn, item_id, args.reason):
        return _missing(item_id)
    print(f'Hid {item_id}. It now reads: "{args.reason}" Undo with maf unhide {item_id}.')
    return 0


def cmd_unhide(conn: sqlite3.Connection, args) -> int:
    if not store.unhide(conn, args.id):
        return _missing(args.id)
    print(f"Unhid {args.id}. Flags can never hide it again.")
    return 0


def cmd_dismiss(conn: sqlite3.Connection, args) -> int:
    if not store.dismiss_requests(conn, args.id):
        print(f"No requests for {args.id}.")
        return 1
    print(f"Cleared requests for {args.id}.")
    return 0


def cmd_nuke(conn: sqlite3.Connection, args) -> int:
    item = store.get_item(conn, args.id)
    if item is None:
        return _missing(args.id)
    replies = store.reply_count(conn, item.id)
    label = f"post {item.id}" if item.is_post else f"comment {item.id}"
    print(f"{label}: {item.title or (item.text or '')[:200]}")
    answer = input(f"Delete post {args.id} and its {replies} comments? [y/N] ")
    if answer.strip().lower() != "y":
        print("Cancelled.")
        return 0
    store.delete_item(conn, item.id)
    print(f"Deleted {args.id}.")
    return 0


def cmd_remove(conn: sqlite3.Connection, args) -> int:
    """Doesn't print the comment: whoever runs it never needs to read it."""
    item = store.get_item(conn, args.id)
    if item is None or item.is_post:
        print(f"No comment {args.id} (posts can only be nuked)")
        return 1
    if not args.yes:
        answer = input(f'Delete the words of comment {args.id} for good and show "{args.reason}"? [y/N] ')
        if answer.strip().lower() != "y":
            print("Cancelled.")
            return 0
    store.remove_comment(conn, args.id, args.reason)
    print(f'Removed comment {args.id}. It now reads: "{args.reason}"')
    return 0


def cmd_pin(conn: sqlite3.Connection, args, pinned: bool) -> int:
    item = store.get_item(conn, args.id)
    if item is None or not item.is_post:
        print(f"No post {args.id}")
        return 1
    store.set_pinned(conn, args.id, pinned)
    print(("Pinned" if pinned else "Unpinned") + f" {args.id}.")
    return 0


def cmd_nsfw(conn: sqlite3.Connection, args, nsfw: bool) -> int:
    """Moves a post to NSFW or back. Takes an id or the post's address (https://…/thread/<id>)."""
    post_id = args.id.rstrip("/").rsplit("/", 1)[-1].split("#")[0]
    item = store.get_item(conn, post_id)
    if item is None or not item.is_post:
        print(f"No post {post_id}")
        return 1
    store.set_nsfw(conn, post_id, nsfw)
    print(f"Moved {post_id} to " + ("NSFW." if nsfw else "the normal list."))
    return 0


def cmd_board(conn: sqlite3.Connection, args) -> int:
    """Moves a post to the Dates page or back to the front page. Takes an id or the post's address."""
    post_id = args.id.rstrip("/").rsplit("/", 1)[-1].split("#")[0]
    if not store.set_board(conn, post_id, args.board):
        print(f"No post {post_id}")
        return 1
    print(f"Moved {post_id} to " + ("Dates." if args.board == "dates" else "the front page."))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="maf", description="MAF maintainer commands")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("requests", help="items with open moderation requests").set_defaults(func=cmd_requests)
    sub.add_parser("usage", help="API request counts per endpoint, from MAF_USAGE_LOG").set_defaults(func=cmd_usage)
    sub.add_parser("stats", help=f"site totals, with the change in the last {STATS_DELTA_HOURS} hours").set_defaults(func=cmd_stats)
    sub.add_parser("hidden", help="hidden items").set_defaults(func=cmd_hidden)
    show = sub.add_parser("show", help="print one item")
    show.add_argument("id")
    show.set_defaults(func=cmd_show)
    hide = sub.add_parser("hide", help="hide a post or reply, with a reason in its place; undo with unhide")
    hide.add_argument("id", help="id, or the post's or reply's address")
    hide.add_argument("--reason", default=DEFAULT_HIDE_REASON, help=f'default: "{DEFAULT_HIDE_REASON}"')
    hide.set_defaults(func=cmd_hide)
    unhide = sub.add_parser("unhide", help="unhide an item; flags can never hide it again")
    unhide.add_argument("id")
    unhide.set_defaults(func=cmd_unhide)
    nuke = sub.add_parser("nuke", help="delete an item and its replies after confirmation")
    nuke.add_argument("id")
    nuke.set_defaults(func=cmd_nuke)
    remove = sub.add_parser("remove", help="delete a comment's words and show a reason instead; replies stay")
    remove.add_argument("id")
    remove.add_argument("--reason", default=DEFAULT_REMOVE_REASON, help=f'default: "{DEFAULT_REMOVE_REASON}"')
    remove.add_argument("--yes", action="store_true", help="skip the confirmation")
    remove.set_defaults(func=cmd_remove)
    dismiss = sub.add_parser("dismiss", help="clear an item's requests")
    dismiss.add_argument("id")
    dismiss.set_defaults(func=cmd_dismiss)
    pin = sub.add_parser("pin", help="pin a post above Today")
    pin.add_argument("id")
    pin.set_defaults(func=lambda conn, args: cmd_pin(conn, args, True))
    unpin = sub.add_parser("unpin", help="unpin a post")
    unpin.add_argument("id")
    unpin.set_defaults(func=lambda conn, args: cmd_pin(conn, args, False))
    nsfw = sub.add_parser("nsfw", help="move a post to NSFW (id or its address)")
    nsfw.add_argument("id")
    nsfw.set_defaults(func=lambda conn, args: cmd_nsfw(conn, args, True))
    sfw = sub.add_parser("sfw", help="move a post back from NSFW (id or its address)")
    sfw.add_argument("id")
    sfw.set_defaults(func=lambda conn, args: cmd_nsfw(conn, args, False))
    board = sub.add_parser("board", help="move a post to Dates or back to the front page: maf board dates <id>")
    board.add_argument("board", choices=store.BOARDS)
    board.add_argument("id")
    board.set_defaults(func=cmd_board)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    conn = _connect()
    try:
        return args.func(conn, args)
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
