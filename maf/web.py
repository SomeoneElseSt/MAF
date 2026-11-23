"""Shared plumbing for the web routes: rendering, the signed-in pass, forms."""

from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode

from starlette.background import BackgroundTask
from starlette.requests import Request
from starlette.responses import HTMLResponse, RedirectResponse, Response
from starlette.templating import Jinja2Templates

from . import display, housetags, store
from .emoji import PICKER_EMOJI
from .app import App
from .util import escape

SORT_KEYS = {"new": "Newest", "old": "Oldest", "views": "Most viewed"}
DEFAULT_SORT = "new"


def make_templates(app: App) -> Jinja2Templates:
    templates = Jinja2Templates(directory=str(app.settings.templates_dir))
    env = templates.env
    env.filters["rel"] = display.relative_time
    env.filters["esc"] = escape
    env.filters["host"] = display.host
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
        base_url=app.settings.base_url,
    )
    return templates


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

    def labeler_label(self, thread_id: str, pass_id: str) -> str:
        return self.app.labeler.label(pass_id, thread_id)


def page_of(request: Request) -> Page:
    """The request's Page, with the app from request.state."""
    app: App = request.state.maf
    return Page(app=app, request=request, pass_id=app.sessions.pass_id(request))


def render(page: Page, template: str, status_code: int = 200, **context: Any) -> HTMLResponse:
    """Renders a template with the shared layout context."""
    tags = store.tag_counts(page.conn)
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
    }
    base.update(context)
    return page.app.templates.TemplateResponse(
        page.request, template, base, status_code=status_code
    )


def redirect(url: str, status_code: int = 303) -> RedirectResponse:
    return RedirectResponse(url, status_code=status_code)


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
        values[name] = raw.strip() if isinstance(raw, str) else ""
    return values


def wants_json(request: Request) -> bool:
    return "application/json" in request.headers.get("accept", "")
