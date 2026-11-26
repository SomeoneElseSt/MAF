"""The read-only JSON API (/api/v1) with bearer tokens and a per-token limit.

Tokens belong to a pass and can only read: there is no write endpoint here.
Hidden items are excluded exactly as on the site, and private replies never
appear.
"""

from datetime import timedelta

from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

from . import store, usage
from .display import four_day_window
from .util import parse_date, sha256_hex, today

REQUESTS_PER_MINUTE = 60
SORTS = {"new", "old", "views"}


def _json(payload, status_code: int = 200, headers: dict | None = None) -> JSONResponse:
    return JSONResponse(payload, status_code=status_code, headers=headers or {})


def _authorised(request: Request) -> tuple[str | None, Response | None]:
    """Returns (pass_id, None) or (None, the error response)."""
    app = request.state.maf
    app.usage.record(usage.endpoint_of(request.method, request.url.path, request.path_params))
    header = request.headers.get("authorization", "")
    if not header.lower().startswith("bearer "):
        return None, _json({"error": "missing bearer token"}, 401, {"WWW-Authenticate": "Bearer"})
    token = header[7:].strip()
    pass_id = store.api_token_pass(app.conn, sha256_hex(token))
    if pass_id is None:
        return None, _json({"error": "invalid token"}, 401, {"WWW-Authenticate": "Bearer"})
    if not app.memory.allow(f"api:{sha256_hex(token)}", REQUESTS_PER_MINUTE):
        retry = app.memory.retry_after(f"api:{sha256_hex(token)}")
        return None, _json({"error": "rate limited"}, 429, {"Retry-After": str(retry)})
    return pass_id, None


def _guarded(handler):
    async def wrapped(request: Request):
        _, error = _authorised(request)
        if error is not None:
            return error
        return await handler(request)

    return wrapped


def _param(request: Request, name: str, default: str = "") -> str:
    return request.query_params.get(name, default)


def _sort(request: Request) -> str:
    value = _param(request, "sort", "new")
    return value if value in SORTS else "new"


def _post_json(post: store.Item) -> dict:
    return {
        "id": post.id,
        "title": post.title,
        "url": post.url,
        "text_preview": post.text_preview,
        "created_at": post.created_at,
        "edited_at": post.edited_at,
        "comment_count": post.comment_count,
        "views": post.views,
        "tags": post.tags,
        "pinned": bool(post.pinned),
    }


@_guarded
async def posts(request: Request) -> Response:
    conn = request.state.maf.conn
    sort = _sort(request)
    tag = _param(request, "tag")
    if tag:
        page_number = max(1, int(_param(request, "page", "1") or 1))
        rows = store.tagged_posts(conn, tag, sort, store.PAGE_SIZE, (page_number - 1) * store.PAGE_SIZE)
        return _json({"posts": [_post_json(p) for p in store.with_comment_counts(conn, rows)]})
    before = parse_date(_param(request, "before"))
    end = before - timedelta(days=1) if before else today()
    start, end = four_day_window(end)
    rows = store.posts_between(conn, start, end, sort)
    return _json({
        "range": {"from": start.isoformat(), "to": end.isoformat()},
        "posts": [_post_json(p) for p in store.with_comment_counts(conn, rows)],
    })


@_guarded
async def tags(request: Request) -> Response:
    conn = request.state.maf.conn
    return _json({"tags": [{"tag": t, "count": n} for t, n in store.tag_counts(conn)]})


@_guarded
async def item(request: Request) -> Response:
    app = request.state.maf
    conn = app.conn
    item_id = request.path_params["id"]
    root = store.get_item(conn, item_id)
    if root is None or root.private_to or root.unlisted:
        return _json({"error": "not found"}, 404)
    thread_id = root.thread_id
    items = [i for i in store.thread_items(conn, thread_id, None) if not i.unlisted]
    post = next(i for i in items if i.id == thread_id)
    labels = app.labeler
    nodes = _tree(store.build_tree(items, thread_id), thread_id, labels, post.pass_id)
    post.comment_count = store.comment_count(conn, thread_id)
    return _json({**_post_json(post), "author_id": labels.label(post.pass_id, thread_id), "op": True,
                  "comments": nodes})


def _tree(nodes, thread_id: str, labels, op_pass: str) -> list[dict]:
    out = []
    for node in nodes:
        item: store.Item = node["item"]
        out.append({
            "id": item.id,
            "text": item.text,
            "removed": item.removed_reason,
            "created_at": item.created_at,
            "edited_at": item.edited_at,
            "author_id": labels.label(item.pass_id, thread_id),
            "op": item.pass_id == op_pass,
            "comments": _tree(node["children"], thread_id, labels, op_pass),
        })
    return out


@_guarded
async def search(request: Request) -> Response:
    conn = request.state.maf.conn
    query = _param(request, "q")
    page_number = max(1, int(_param(request, "page", "1") or 1))
    rows = store.search(conn, query, _sort(request), store.PAGE_SIZE, (page_number - 1) * store.PAGE_SIZE)
    return _json({
        "query": query,
        "page": page_number,
        "results": [
            {
                "id": r.id,
                "title": r.title,
                "text_preview": r.text_preview,
                "created_at": r.created_at,
                "thread_id": r.thread_id,
                "is_post": r.is_post,
                "tags": r.tags,
            }
            for r in rows
        ],
    })


routes = [
    Route("/api/v1/posts", posts),
    Route("/api/v1/tags", tags),
    Route("/api/v1/threads/{id}", item),
    Route("/api/v1/search", search),
]
