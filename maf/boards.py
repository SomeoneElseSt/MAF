"""Boards: separate front pages. Every post lives on exactly one; its replies follow it.

"main" is the front page at /. Every other board has its own page at /<name>/ with its own
pinned posts, New section, hashtags and 4-day windows. Search covers all of them.
Adding a board is one entry here (plus its colour in style.css).
"""

MAIN = "main"

# name -> (label shown to people, page path)
BOARDS = {
    MAIN: ("Main", "/"),
    "dating": ("/dating/", "/dating/"),
}


def valid(name: str | None) -> str:
    """The board a form or URL asked for, or main when it named none or one that doesn't exist."""
    return name if name in BOARDS else MAIN


def path(name: str) -> str:
    return BOARDS[valid(name)][1]


def label(name: str) -> str:
    return BOARDS[valid(name)][0]


def of_path(url_path: str) -> str | None:
    """Which board's page this is (/dating/ -> "dating"), or None for any other page."""
    for name, (_, board_path) in BOARDS.items():
        if url_path == board_path:
            return name
    return None
