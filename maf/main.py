"""The Starlette application: routes, middleware and startup."""

import threading
from datetime import timedelta
from urllib.parse import urlparse

from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.middleware.gzip import GZipMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, RedirectResponse, Response
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles

from . import auth, boards, housetags, post, reactions, reading, store, votes
from .app import App, build_app
from .display import day_label, four_day_window, range_label
from .settings import Settings, load_settings
from .util import iso, parse_date, today, utc_now
from .web import make_templates, page_of, redirect, render, sort_param

APP: App = None  # set by create_app


def home(request: Request) -> Response:
    """A board's front page: / for the main board, /dating/ and so on for the others."""
    page = page_of(request)
    board = boards.of_path(request.url.path) or boards.MAIN
    sort = sort_param(request)
    tag = request.query_params.get("tag", "").strip().lower()
    if tag:
        return render_tag(page, board, tag, sort, max(1, int(request.query_params.get("page", "1") or 1)))
    before = parse_date(request.query_params.get("before"))
    after = parse_date(request.query_params.get("after"))
    return render_home(page, board, sort, before, after)


def render_tag(page, board: str, tag: str, sort: str, page_number: int):
    """One board's posts with one tag, across all time, 30 per page (SPEC Hashtags)."""
    conn = page.conn
    offset = (page_number - 1) * store.PAGE_SIZE
    rows = store.tagged_posts(conn, tag, sort, store.PAGE_SIZE + 1, offset, board=board)
    has_next = len(rows) > store.PAGE_SIZE
    results = store.with_counts(conn, rows[: store.PAGE_SIZE])
    pager = {
        "prev": _tag_url(board, tag, sort, page_number - 1) if page_number > 1 else None,
        "next": _tag_url(board, tag, sort, page_number + 1) if has_next else None,
    }
    return render(page, "list.html", kind="tag", title=_board_title(board, f"#{tag}"), results=results, pager=pager)


def _board_title(board: str, title: str) -> str:
    """Page titles on other boards say which one: "/dating/", "#help · /dating/"."""
    if board == boards.MAIN:
        return title
    return f"{title} · {boards.label(board)}" if title else boards.label(board)


def _tag_url(board: str, tag: str, sort: str, page_number: int) -> str:
    from urllib.parse import urlencode

    params = {"tag": tag, "page": page_number}
    if sort != "new":
        params["sort"] = sort
    return boards.path(board) + "?" + urlencode(params)


def render_home(page, board, sort, before, after):
    conn = page.conn
    base = boards.path(board)
    title = _board_title(board, "")
    if not store.has_any_posts(conn, board):
        return render(page, "list.html", kind="home", title=title, empty=True,
                      groups=[], pinned=[], date_range=range_label(*four_day_window(today())),
                      sort_links=_sort_links(base), prev_url=None, next_url=None)

    first_day = store.first_post_day(conn, board)
    window_end = _window_end(conn, board, sort, before, after)
    # Nothing to show before the first post: a window ending earlier opens the earliest one instead.
    if first_day and window_end < first_day:
        window_end = first_day + timedelta(days=3)
    start, end = four_day_window(window_end)
    pinned: list = []
    exclude_pinned = False
    if sort == "new" and before is None:
        pinned = store.with_counts(conn, store.pinned_posts(conn, board))
        exclude_pinned = True
    posts = store.with_counts(conn, store.posts_between(conn, start, end, sort, exclude_pinned=exclude_pinned, board=board))
    latest = store.latest_comment_times(conn, [post.thread_id for post in pinned + posts], not_by=page.pass_id)
    groups = [(day_label(day), rows) for day, rows in store.day_groups(posts)]
    # The ‹ arrow stops at the window holding the first post.
    prev_url = _page_url(base, sort, (start - timedelta(days=1)).isoformat()) if first_day and start > first_day else None
    next_url = _next_url(base, sort, end)
    return render(page, "list.html", kind="home", title=title, empty=False,
                  groups=groups, pinned=pinned, latest_comments=latest, date_range=range_label(start, end),
                  prev_url=prev_url, next_url=next_url, sort_links=_sort_links(base),
                  day_param=end.isoformat(), now=iso(utc_now()),
                  range_start=start.isoformat(), range_end=end.isoformat())


def _window_end(conn, board, sort, before, after):
    """The last day of the 4-day window, so the range label always matches the posts."""
    if before:
        return before - timedelta(days=1)
    if after:
        return after + timedelta(days=3)
    if sort == "old":
        first = store.first_post_day(conn, board) or today()
        return first + timedelta(days=3)
    return today()


def _sort_links(base: str) -> dict[str, str]:
    """Switching sort resets the page: Newest and Most viewed open the latest 4 days, Oldest the earliest."""
    return {"new": base, "old": f"{base}?sort=old", "views": f"{base}?sort=views"}


def _page_url(base: str, sort: str, before: str) -> str:
    return f"{base}?before={before}" if sort == "new" else f"{base}?before={before}&sort={sort}"


def _next_url(base: str, sort: str, end) -> str | None:
    """The › arrow is disabled when the window already reaches today."""
    if end >= today():
        return None
    later = end + timedelta(days=4)
    if sort == "new":
        return base if later >= today() else f"{base}?before={later.isoformat()}"
    return f"{base}?before={later.isoformat()}&sort={sort}"


def search(request: Request) -> Response:
    page = page_of(request)
    query = request.query_params.get("q", "").strip()
    if query.startswith("#") and len(query) > 1:
        board = boards.valid(request.query_params.get("board"))
        return redirect(f"{boards.path(board)}?tag={query[1:].strip().lower()}")
    sort = sort_param(request)
    page_number = max(1, int(request.query_params.get("page", "1") or 1))
    offset = (page_number - 1) * store.PAGE_SIZE
    results = store.with_counts(
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
    board = boards.valid(request.query_params.get("board"))
    return render(page, "tags.html", title=_board_title(board, "Hashtags"), board=board,
                  tag_list=store.tag_counts(page.conn, board))


def about(request: Request) -> Response:
    page = page_of(request)
    return render(page, "about.html", title="About")


def privacy(request: Request) -> Response:
    page = page_of(request)
    return render(page, "privacy.html", title="Privacy")


def guide(request: Request) -> Response:
    page = page_of(request)
    return render(page, "guide.html", title="User Guide")


def guide_data(request: Request) -> Response:
    page = page_of(request)
    tokens = store.list_api_tokens(page.conn, page.pass_id) if page.pass_id else []
    new_token = page.memory.take_new_token(page.pass_id) if page.pass_id else None
    return render(page, "guide-data.html", title="Use this data", tokens=tokens, new_token=new_token,
                  max_tokens=post.MAX_TOKENS_PER_PASS,
                  notice=request.query_params.get("notice"))


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


IN_PLACE_HEADER = b"x-maf-in-place"


class InPlaceRedirects:
    """Forms on the thread page send in the background (replies.js) so posting doesn't add a step to the
    browser's history (Back would land on the same thread first). For those requests a redirect comes
    back as 200 {"location": ...}, which the page follows by replacing itself. Normal form posts are untouched."""

    def __init__(self, asgi_app) -> None:
        self._app = asgi_app

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http" or IN_PLACE_HEADER not in dict(scope["headers"]):
            await self._app(scope, receive, send)
            return
        redirected = False

        async def send_in_place(message) -> None:
            nonlocal redirected
            if message["type"] == "http.response.start" and 300 <= message["status"] < 400:
                redirected = True
                location = dict(message["headers"]).get(b"location", b"/").decode()
                await JSONResponse({"location": location})(scope, receive, send)
                return
            if redirected:
                return
            await send(message)

        await self._app(scope, receive, send_in_place)


# Pages a signed-out visitor may open. Everything else needs a pass; the API checks its own bearer tokens.
PUBLIC_PATHS = {"/sign-in", "/sign-in/code", "/sign-in/sent", "/sign-in/key", "/sign-in/blind-sign", "/sign-in/redeem", "/about", "/privacy"}
PUBLIC_PREFIXES = ("/static/", "/api/")


class RequireSignIn:
    """Only students can read MAF: without a valid pass, every non-public request goes to Sign in."""

    def __init__(self, asgi_app) -> None:
        self._app = asgi_app

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http" or _is_public(scope["path"]):
            await self._app(scope, receive, send)
            return
        if APP.sessions.pass_id(Request(scope)) is not None:
            await self._app(scope, receive, send)
            return
        await RedirectResponse("/sign-in", status_code=303)(scope, receive, send)


def _is_public(path: str) -> bool:
    return path in PUBLIC_PATHS or path.startswith(PUBLIC_PREFIXES)


def create_app(settings: Settings | None = None) -> Starlette:
    global APP
    settings = settings or load_settings()
    if settings.hashtags_file:
        housetags.load_file(settings.hashtags_file)
    app = build_app(settings)
    app.templates = make_templates(app)
    APP = app
    from . import api

    routes = [
        Route("/", home),
        *[Route(boards.path(name), home) for name in boards.BOARDS if name != boards.MAIN],
        Route("/search", search),
        Route("/tags", tags_page),
        Route("/about", about),
        Route("/privacy", privacy),
        Route("/guide", guide),
        Route("/guide/use-this-data", guide_data),
        Route("/sign-out", logout, methods=["POST"]),
        *reading.routes,
        *post.routes,
        *auth.routes,
        *api.routes,
        *reactions.routes,
        *votes.routes,
        # Mounts last: a Mount matches any path under its prefix.
        Mount("/static", StaticFiles(directory=str(settings.static_dir)), name="static"),
    ]
    starlette = Starlette(routes=routes, exception_handlers={404: not_found},
                          middleware=[Middleware(GZipMiddleware, minimum_size=500), Middleware(WithApp), Middleware(InPlaceRedirects), Middleware(RequireSignIn)])
    starlette.state.maf = app
    return starlette


DEFAULT_PORT = 8000


def listen_port(base_url: str) -> int:
    """The port in MAF_BASE_URL (http://localhost:8000), else 8000 (https://maforum.net has none)."""
    return urlparse(base_url).port or DEFAULT_PORT


def main() -> None:
    import uvicorn

    settings = load_settings()
    app = create_app(settings)
    # In the background, so the server answers straight away; a post arriving meanwhile just waits for it.
    threading.Thread(target=APP.name_filter.warm_up, name="name-check-warm-up", daemon=True).start()
    uvicorn.run(
        app,
        host="127.0.0.1",
        port=listen_port(settings.base_url),
        access_log=False,  # no IP addresses in logs
        timeout_graceful_shutdown=3,  # open live-reply streams would otherwise hold a restart
    )



if __name__ == "__main__":
    main()
