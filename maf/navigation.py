"""Where the header's MAF logo, Submit, Dates and NSFW lead from the page you're on. One place for the rules:

- MAF goes up one level: from any page to the home of the board you're on; from a board's home to the main home.
- Dates and NSFW take you to that board's home; on that home already, they take you back to the main home.
- Submit opens the form for the board you're on.

The board you're on is a post's own, the Dates page and form's, or else the side you're browsing. The NSFW side
is a per-browser setting (a cookie). Links that change it go through /?side=nsfw or /?side=main, which set it and
land on the front page (or on `next`).

Posts live under their board too: thread_url() gives a post's address, and any other address for it redirects there.
A post's hashtags open on the post's side (tag_url).
"""

from dataclasses import dataclass
from urllib.parse import quote

MAIN, NSFW, DATES = "main", "nsfw", "dates"
SIDE_URL = {MAIN: "/?side=main", NSFW: "/?side=nsfw"}
BOARD_HOME = {MAIN: SIDE_URL[MAIN], NSFW: SIDE_URL[NSFW], DATES: "/dates"}


@dataclass(frozen=True)
class Nav:
    logo: str
    submit: str
    dates: str
    nsfw: str
    on_dates: bool  # the Dates word lights up
    nsfw_on: bool  # the NSFW word lights up


def page_board(nsfw_on: bool, dates_page: bool, post_board: str | None) -> str:
    """The board this page belongs to: a post's own, the Dates page's, or the side being browsed."""
    if post_board:
        return post_board
    if dates_page:
        return DATES
    return NSFW if nsfw_on else MAIN


def header_links(path: str, has_query: bool, nsfw_on: bool, dates_page: bool, post_board: str | None) -> Nav:
    board = page_board(nsfw_on, dates_page, post_board)
    at_dates_home = path == "/dates"
    at_nsfw_home = path == "/" and not has_query and nsfw_on
    side_now = NSFW if nsfw_on else MAIN
    submit = {
        DATES: "/dates/submit",
        MAIN: "/submit" if side_now == MAIN else f"{SIDE_URL[MAIN]}&next=/submit",
        NSFW: "/submit" if side_now == NSFW else f"{SIDE_URL[NSFW]}&next=/submit",
    }[board]
    return Nav(
        logo=BOARD_HOME[MAIN] if at_dates_home or at_nsfw_home else BOARD_HOME[board],
        submit=submit,
        dates=BOARD_HOME[MAIN] if at_dates_home else BOARD_HOME[DATES],
        nsfw=BOARD_HOME[MAIN] if at_nsfw_home else BOARD_HOME[NSFW],
        on_dates=board == DATES,
        nsfw_on=nsfw_on and not dates_page,  # the Dates page always shows NSFW off
    )


def post_board_of(post) -> str:
    return DATES if post.board == DATES else (NSFW if post.nsfw else MAIN)


# A post's address carries its board: /thread/<id>, /nsfw/thread/<id> or /dates/thread/<id>.
THREAD_PREFIX = {MAIN: "", NSFW: "/nsfw", DATES: "/dates"}


def thread_url(post, item_id: str | None = None) -> str:
    """Where a post (or, with item_id, something in it) lives, by the post's board."""
    return f"{THREAD_PREFIX[post_board_of(post)]}/thread/{item_id or post.id}"


def tag_url(tag: str, post) -> str:
    """A hashtag on a post opens on the post's side, so the post is in the list it leads to. (Hashtags aren't
    listed for Dates, so one left on a moved Dates post opens on the normal side.)"""
    side = NSFW if post_board_of(post) == NSFW else MAIN
    return f"{SIDE_URL[side]}&next={quote('/?tag=' + tag, safe='/')}"


def safe_next(value: str | None) -> str:
    """Where /?side=… lands: a path on this site only, else the front page."""
    if value and value.startswith("/") and not value.startswith("//"):
        return value
    return "/"
