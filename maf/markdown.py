"""Markdown in posts, replies and edits: bold, italics, underline, links, lists, quotes, code, strikethrough.
Titles get only bold, italics, underline and strikethrough.

Underline is __text__ (as in chat apps; plain markdown has no underline), so bold is **text** only.

No raw HTML, images (they'd load from other sites) or headings ("# " stays text, so it never fights with
hashtags). Single line breaks stay, as before markdown. The browser renders private replies with the same
library and rules (maf/static/markdown.js), so both look the same.
"""

import html
import re

from markupsafe import Markup, escape
from markdown_it import MarkdownIt

OFF = ["image", "heading", "lheading", "html_block", "html_inline"]


def _open_links_in_new_tab(renderer, tokens, idx, options, env):
    tokens[idx].attrSet("target", "_blank")
    tokens[idx].attrSet("rel", "nofollow noopener noreferrer")
    return renderer.renderToken(tokens, idx, options, env)


def _underline_open(renderer, tokens, idx, options, env):
    return "<u>" if tokens[idx].markup == "__" else renderer.renderToken(tokens, idx, options, env)


def _underline_close(renderer, tokens, idx, options, env):
    return "</u>" if tokens[idx].markup == "__" else renderer.renderToken(tokens, idx, options, env)


def _with_underline(md: MarkdownIt) -> MarkdownIt:
    md.add_render_rule("strong_open", _underline_open)
    md.add_render_rule("strong_close", _underline_close)
    return md


_md = _with_underline(
    MarkdownIt("commonmark", {"html": False, "breaks": True, "linkify": True})
    .enable(["strikethrough", "linkify"])
    .disable(OFF)
)
_md.add_render_rule("link_open", _open_links_in_new_tab)
_title_md = _with_underline(MarkdownIt("zero", {"html": False}).enable(["emphasis", "strikethrough", "escape"]))
_TAG = re.compile(r"<[^>]+>")


def render(text: str | None, label: str = "") -> Markup:
    """HTML for a post's or reply's text. A label ("Edit #2:") goes at the start of the first paragraph."""
    html = _md.render(text or "")
    if not label:
        return Markup(html)
    if html.startswith("<p>"):
        return Markup(f"<p>{escape(label)} {html[3:]}")
    return Markup(f"<p>{escape(label)}</p>{html}")


def title(text: str | None) -> Markup:
    """HTML for a post title: bold, italics, underline and strikethrough only."""
    return Markup(_title_md.renderInline(text or ""))


def plain(text: str | None) -> str:
    """The words without markdown symbols, for the tab title, the Feed and search snippets."""
    return " ".join(words(text).split())


def words(text: str | None) -> str:
    """The text as it reads on the page, line breaks kept: what the name check reads, so "**Priya Raman**"
    or "P**riya Ram**an" can't slip past it."""
    return html.unescape(_TAG.sub("", _md.render(text or "")))
