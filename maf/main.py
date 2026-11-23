"""The Starlette application: routes, middleware and startup."""

from datetime import timedelta

from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.middleware.gzip import GZipMiddleware
from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles

from . import auth, post, reading, store
from .app import App, build_app
from .display import day_label, four_day_window, range_label
from .settings import Settings, load_settings
from .util import parse_date, today
from .web import make_templates, page_of, redirect, render, sort_param

APP: App = None  # set by create_app


def home(request: Request) -> Response:
    page = page_of(request)
    sort = sort_param(request)
    before = parse_date(request.query_params.get("before"))
    after = parse_date(request.query_params.get("after"))
    return render_home(page, sort, before, after)


def render_home(page, sort, before, after):
    conn = page.conn
    if not store.has_any_posts(conn):
        return render(page, "list.html", kind="home", title="", empty=True,
                      groups=[], pinned=[], range_label=range_label(*four_day_window(today())),
                      sort_links=_home_sort_links(None), prev_url=None, next_url=None)

    window_end = _window_end(conn, sort, before, after)
    start, end = four_day_window(window_end)
    pinned: list = []
    exclude_pinned = False
    if sort == "new" and before is None:
        pinned = store.pinned_posts(conn)
        exclude_pinned = True
    posts = store.with_comment_counts(conn, store.posts_between(conn, start, end, sort, exclude_pinned=exclude_pinned))
    groups = [(day_label(day), rows) for day, rows in store.day_groups(posts)]
    prev_url = _page_url(sort, (start - timedelta(days=1)).isoformat())
    next_url = _next_url(sort, end)
    return render(page, "list.html", kind="home", title="", empty=False,
                  groups=groups, pinned=pinned, range_label=range_label(start, end),
                  prev_url=prev_url, next_url=next_url, sort_links=_home_sort_links(start),
                  day_param=end.isoformat())


def _window_end(conn, sort, before, after):
    """The last day of the 4-day window, so the range label always matches the posts."""
    if before:
        return before - timedelta(days=1)
    if after:
        return after + timedelta(days=3)
    if sort == "old":
        first = store.first_post_day(conn) or today()
        return first + timedelta(days=3)
    return today()


def _home_sort_links(start) -> dict[str, str]:
    base = "/" if start is None else f"/?before={(start + timedelta(days=3)).isoformat()}"
    joiner = "&" if "?" in base else "?"
    return {
        "new": base if start is None else "/",
        "old": f"{base}{joiner}sort=old",
        "views": f"{base}{joiner}sort=views",
    }


def _page_url(sort: str, before: str) -> str:
    return f"/?before={before}" if sort == "new" else f"/?before={before}&sort={sort}"


def _next_url(sort: str, end) -> str | None:
    """The › arrow is disabled when the window already reaches today."""
    if end >= today():
        return None
    later = end + timedelta(days=4)
    if sort == "new":
        return "/" if later >= today() else f"/?before={later.isoformat()}"
    return f"/?before={later.isoformat()}&sort={sort}"


def search(request: Request) -> Response:
    page = page_of(request)
    query = request.query_params.get("q", "").strip()
    if query.startswith("#") and len(query) > 1:
        return redirect(f"/?tag={query[1:].strip().lower()}")
    sort = sort_param(request)
    page_number = max(1, int(request.query_params.get("page", "1") or 1))
    offset = (page_number - 1) * store.PAGE_SIZE
    results = store.with_comment_counts(
        page.conn, store.search(page.conn, query, sort, store.PAGE_SIZE + 1, offset)
    ) if query else []
    has_next = len(results) > store.PAGE_SIZE
    results = results[: store.PAGE_SIZE]
    pager = {
        "prev": _search_url(query, sort, page_number - 1) if page_number > 1 else None,
        "next": _search_url(query, sort, page_number + 1) if has_next else None,
    }
    return render(page, "list.html", kind="search", title="Search",
                  search_query=query, results=results, pager=pager, page_number=page_number)


def _search_url(query: str, sort: str, page_number: int) -> str:
    from urllib.parse import urlencode

    params = {"q": query, "page": page_number}
    if sort != "new":
        params["sort"] = sort
    return "/search?" + urlencode(params)


def tags_page(request: Request) -> Response:
    page = page_of(request)
    return render(page, "tags.html", title="Hashtags", tag_list=store.tag_counts(page.conn))


def about(request: Request) -> Response:
    page = page_of(request)
    return render(page, "about.html", title="About")


def guide(request: Request) -> Response:
    page = page_of(request)
    return render(page, "guide.html", title="User Guide")


def guide_data(request: Request) -> Response:
    page = page_of(request)
    tokens = store.list_api_tokens(page.conn, page.pass_id) if page.pass_id else []
    return render(page, "guide-data.html", title="Use this data", tokens=tokens,
                  notice=request.query_params.get("notice"),
                  new_token=request.query_params.get("token"))


def logout(request: Request) -> Response:
    page = page_of(request)
    response = redirect("/")
    page.app.sessions.clear(response)
    return response


def not_found(request: Request, exc) -> Response:
    page = page_of(request)
    return render(page, "error.html", status_code=404, title="Not found",
                  message="That page doesn't exist.")


class WithApp:
    """Puts the App on request.state so routes don't need a global."""

    def __init__(self, asgi_app) -> None:
        self._app = asgi_app

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] == "http":
            scope.setdefault("state", {})["maf"] = APP
        await self._app(scope, receive, send)


def create_app(settings: Settings | None = None) -> Starlette:
    global APP
    settings = settings or load_settings()
    app = build_app(settings)
    app.templates = make_templates(app)
    APP = app
    from . import api

    routes = [
        Route("/", home),
        Route("/search", search),
        Route("/tags", tags_page),
        Route("/about", about),
        Route("/guide", guide),
        Route("/guide/data", guide_data),
        Route("/logout", logout, methods=["POST"]),
        Mount("/static", StaticFiles(directory=str(settings.static_dir)), name="static"),
        *reading.routes,
        *post.routes,
        *auth.routes,
        *api.routes,
    ]
    starlette = Starlette(routes=routes, exception_handlers={404: not_found},
                          middleware=[Middleware(GZipMiddleware, minimum_size=500), Middleware(WithApp)])
    starlette.state.maf = app
    return starlette


def main() -> None:
    import uvicorn

    settings = load_settings()
    uvicorn.run(
        create_app(settings),
        host="127.0.0.1",
        port=int(settings.base_url.rsplit(":", 1)[-1]) if ":" in settings.base_url else 8000,
        access_log=False,  # no IP addresses in logs
    )

