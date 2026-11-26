"""Shared plumbing for the web routes: rendering, the signed-in pass, forms."""

import base64
import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

from starlette.requests import Request
from starlette.responses import HTMLResponse, RedirectResponse, Response
from starlette.templating import Jinja2Templates

from . import display, housetags, markdown, store
from .app import App
from .emoji import PICKER_EMOJI
from .util import escape, iso, utc_now

SORT_KEYS = {"new": "Newest", "old": "Oldest", "views": "Most viewed"}
DEFAULT_SORT = "new"


STATIC_HASH_LENGTH = 10


def static_versions(static_dir: Path) -> dict[str, str]:
    """Short content hash of every static file, computed once at startup."""
    versions = {}
    for path in sorted(static_dir.rglob("*")):
        if not path.is_file():
            continue
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        versions[path.relative_to(static_dir).as_posix()] = digest[:STATIC_HASH_LENGTH]
    return versions


def inline_png(static_dir: Path, name: str) -> str:
    """A small static PNG as a data: URL, so swapping to it needs no download (the theme-matched tab icon)."""
    return "data:image/png;base64," + base64.b64encode((static_dir / name).read_bytes()).decode()


def make_static_url(static_dir: Path):
    """Returns static("style.css") -> "/static/style.css?v=<hash>", so browsers refetch changed files."""
    versions = static_versions(static_dir)

    def static(name: str) -> str:
        version = versions.get(name)
        if version is None:
            return f"/static/{name}"
        return f"/static/{name}?v={version}"

    return static


def make_templates(app: App) -> Jinja2Templates:
    templates = Jinja2Templates(directory=str(app.settings.templates_dir))
    env = templates.env
    env.filters["rel"] = display.relative_time
    env.filters["esc"] = escape
    env.filters["host"] = display.host
    env.filters["markdown"] = markdown.render
    env.filters["md_title"] = markdown.title
    env.filters["plain"] = markdown.plain
    env.globals.update(
        day_label=display.day_label,
        range_label=display.range_label,
        metadata=display.metadata,
        plural=display._plural,
        house_tags=housetags.HOUSE_TAGS,
        is_hot=housetags.is_hot,
        sort_keys=SORT_KEYS,
        picker_emoji=PICKER_EMOJI,
        submit_templates={**{t: h["submit_template"] for t, h in housetags.HOUSE_TAGS.items()}, "default": housetags.DEFAULT_SUBMIT_TEMPLATE},
        example_post=housetags.EXAMPLE_POST,
        suggested_tags=housetags.suggested_tags(app.settings.org_tag),
        org=app.settings,  # email_domain, contact_email, community, forum_name, org_tag
        base_url=app.settings.base_url,
        static=make_static_url(app.settings.static_dir),
        icon_dark=inline_png(app.settings.static_dir, "icon-32.png"),
        icon_light=inline_png(app.settings.static_dir, "icon-32-light.png"),
    )
    return templates


NSFW_COOKIE = "maf_nsfw"


@dataclass
class Page:
    """One request's context: the app, the connection and the viewer's pass."""

    app: App
    request: Request
    pass_id: str | None

    @property
    def conn(self):
        return self.app.conn

    @property
    def settings(self):
        return self.app.settings

    @property
    def memory(self):
        return self.app.memory

    @property
    def nsfw(self) -> bool:
        """Whether this browser has NSFW on: lists then show only NSFW posts. A cookie the page sets (nsfw.js),
        so it's a per-browser setting like Dark; the server never stores it."""
        return self.request.cookies.get(NSFW_COOKIE) == "1"

    def labeler_label(self, thread_id: str, pass_id: str) -> str:
        return self.app.labeler.label(pass_id, thread_id)


def page_of(request: Request) -> Page:
    """The request's Page, with the app from request.state."""
    app: App = request.state.maf
    return Page(app=app, request=request, pass_id=app.sessions.pass_id(request))


def render(page: Page, template: str, status_code: int = 200, **context: Any) -> HTMLResponse:
    """Renders a template with the shared layout context."""
    # Signed-out visitors get nothing from the forum, not even tag names in the # menu.
    tags = store.tag_counts(page.conn, page.nsfw) if page.pass_id else []
    params = dict(page.request.query_params)

    def sort_url(key: str) -> str:
        """This page with a different sort, dropping the page number."""
        updated = {**params, "sort": key}
        updated.pop("page", None)
        if key == "new":
            updated.pop("sort", None)
        query = urlencode(updated)
        return f"{page.request.url.path}?{query}" if query else page.request.url.path

    base = {
        "sort_url": sort_url,
        "viewer": page.pass_id,
        "tags": tags,
        "search_query": page.request.query_params.get("q", ""),
        "active_tag": page.request.query_params.get("tag"),
        "sort": sort_param(page.request),
        "path": page.request.url.path,
        "server_now": iso(utc_now()),
        "nsfw_mode": page.nsfw,
    }
    base.update(context)
    return page.app.templates.TemplateResponse(
        page.request, template, base, status_code=status_code,
        # Back may reuse the page, but only after checking with the server: an old saved copy would
        # show counts lower than ones already seen.
        headers={"Cache-Control": "no-cache"},
    )


def redirect(url: str, status_code: int = 303) -> RedirectResponse:
    return RedirectResponse(url, status_code=status_code)


def gone(page, thread_id: str) -> Response:
    """The reply (or post) was deleted while someone had the page open: back to the thread with a
    note, not to sign-in. Forms send thread_id because the site sends no Referer."""
    if page.pass_id is None:
        return redirect("/sign-in")
    thread = store.get_item(page.conn, thread_id) if thread_id else None
    if thread is None or not thread.is_post:
        return redirect("/")  # the whole post is gone
    return redirect(f"/thread/{thread.id}?notice=That+reply+was+deleted.")


def sort_param(request: Request) -> str:
    value = request.query_params.get("sort", DEFAULT_SORT)
    return value if value in SORT_KEYS else DEFAULT_SORT


def notice(request: Request) -> str | None:
    return request.query_params.get("notice")


def html_response(body: str, status_code: int = 200) -> Response:
    return HTMLResponse(body, status_code=status_code)


def error_page(page: Page, status_code: int, message: str) -> HTMLResponse:
    return render(page, "error.html", status_code=status_code, message=message)


async def form_values(request: Request, *names: str) -> dict[str, str]:
    form = await request.form()
    values = {}
    for name in names:
        raw = form.get(name)
        # Browsers send textarea line breaks as \r\n; store plain \n so blank lines split paragraphs.
        values[name] = raw.replace("\r\n", "\n").replace("\r", "\n").strip() if isinstance(raw, str) else ""
    return values


def wants_json(request: Request) -> bool:
    return "application/json" in request.headers.get("accept", "")
