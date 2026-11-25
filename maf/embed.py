"""Preview cards for replies that link to another MAF thread.

A link to /thread/<id> (or /<id>, the bare form the API returns) gets a card with the
thread's title, the first lines of its post and its details, instead of a bare URL.
Only public threads: private replies and unlisted posts never get a card.
"""

import re
from dataclasses import dataclass
from urllib.parse import urlsplit

from . import markdown, store

# Up to three cards per item, so one reply can't turn a thread into a list of previews.
EMBEDS_PER_ITEM = 3
THREAD_PATH = re.compile(r"^/(?:thread/)?([a-z0-9]+(?:-[a-z0-9]+)*)/?$")


@dataclass
class Embed:
    id: str
    title: str
    preview: str
    label: str
    created_at: str
    views: int
    comment_count: int
    tags: list[str]


def thread_id_in(url: str, host: str) -> str | None:
    """The thread id a link points at, for links to this site's threads, else None."""
    parts = urlsplit(url)
    if parts.query or parts.fragment:
        return None
    # A relative link is this site's by definition; a full one must point at this site.
    if (parts.scheme or parts.netloc) and (parts.scheme not in ("http", "https") or parts.netloc != host):
        return None
    match = THREAD_PATH.match(parts.path)
    return match.group(1) if match else None


def embeds_in(conn, text: str | None, labeler, viewer_thread: str, host: str) -> list[Embed]:
    """A card for each of the first MAF thread links in the text that is readable here."""
    if not text:
        return []
    found: list[Embed] = []
    seen: set[str] = set()
    for url in markdown.link_urls(text):
        thread_id = thread_id_in(url, host)
        if thread_id is None or thread_id in seen or len(found) >= EMBEDS_PER_ITEM:
            continue
        seen.add(thread_id)
        post = store.get_item(conn, thread_id)
        if post is None or not post.is_post or post.private_to or post.unlisted or post.removed_reason:
            continue
        found.append(Embed(
            id=post.id,
            title=markdown.plain(post.title or ""),
            preview=markdown.plain(post.text or ""),
            label=labeler.label(post.pass_id, viewer_thread),
            created_at=post.created_at,
            views=post.views,
            comment_count=store.comment_count(conn, post.id),
            tags=post.tags,
        ))
    return found
