"""Writing: posts, comments, flags, moderation requests and API tokens."""

import secrets
from urllib.parse import urlsplit

from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import Route

from . import store
from .email import moderation_email
from .housetags import submit_placeholder
from .util import sha256_hex
from .web import form_values, page_of, redirect, render

POSTS_PER_MINUTE = 6
COMMENTS_PER_MINUTE = 12
TOKEN_BYTES = 32
MAX_TOKENS_PER_PASS = 5  # the Create token button greys out at this many


def _login(page) -> Response:
    return redirect("/sign-in")


def _allowed(page, key: str, limit: int) -> bool:
    return page.memory.allow(f"{key}:{page.pass_id}", limit)


async def submit_page(request: Request) -> Response:
    page = page_of(request)
    if page.pass_id is None:
        return _login(page)
    tags: list[str] = []
    return render(page, "submit.html", tags=tags, placeholder=submit_placeholder(tags),
                  values={}, errors={})


async def submit_post(request: Request) -> Response:
    page = page_of(request)
    if page.pass_id is None:
        return _login(page)
    values = await form_values(request, "title", "url", "text", "tags", "confirm_names")
    tags, too_many = store.normalise_tags(values["tags"])
    errors = _validate_post(values, too_many)
    if errors:
        return _form_error(page, values, tags, errors)
    if values["confirm_names"] != "1" and page.app.name_filter.finds_name(values["title"], values["text"]):
        return _name_warning(page, values, tags)
    if not _allowed(page, "post", POSTS_PER_MINUTE):
        return _form_error(page, values, tags, {"form": "You're posting fast. Wait a minute and try again."})
    post = store.create_post(
        page.conn, page.pass_id, values["title"], values["text"] or None, values["url"] or None, tags
    )
    return redirect(f"/thread/{post.id}")


def _validate_post(values: dict[str, str], too_many: bool) -> dict[str, str]:
    errors: dict[str, str] = {}
    if not values["title"]:
        errors["title"] = "Add a title."
    elif len(values["title"]) > store.TITLE_MAX:
        errors["title"] = f"Keep the title under {store.TITLE_MAX} characters."
    if not values["text"] and not values["url"]:
        errors["form"] = "Write something or add a link."
    if values["url"] and not _valid_url(values["url"]):
        errors["url"] = "That link doesn't look like a web address."
    if len(values["text"]) > store.BODY_MAX:
        errors["text"] = "That's too long. Try trimming it."
    if too_many:
        errors["tags"] = "Use at most 3 hashtags."
    return errors


def _valid_url(url: str) -> bool:
    parts = urlsplit(url)
    return parts.scheme in {"http", "https"} and bool(parts.netloc)


def _form_error(page, values, tags, errors) -> Response:
    return render(page, "submit.html", status_code=400, tags=tags,
                  placeholder=submit_placeholder(tags), values=values, errors=errors)


def _name_warning(page, values, tags) -> Response:
    return render(page, "submit-warning.html", status_code=400, tags=tags,
                  placeholder=submit_placeholder(tags), values=values)


async def comment(request: Request) -> Response:
    page = page_of(request)
    values = await form_values(request, "parent_id", "text", "private", "confirm_names")
    parent = store.get_item(page.conn, values["parent_id"])
    if page.pass_id is None or parent is None:
        return _login(page)
    if not values["text"]:
        return redirect(f"/thread/{parent.thread_id}?notice=Write+something+first.")
    if values["confirm_names"] != "1" and page.app.name_filter.finds_name(values["text"]):
        return redirect(f"/thread/{parent.thread_id}?notice=This+looks+like+it+names+someone.+Edit+it+and+try+again.")
    if not _allowed(page, "comment", COMMENTS_PER_MINUTE):
        return redirect(f"/thread/{parent.thread_id}?notice=You're+replying+fast.+Wait+a+minute.")
    private_to = _private_recipient(page, parent, values["private"] == "on")
    store.create_comment(page.conn, page.pass_id, parent, values["text"], private_to)
    return redirect(f"/thread/{parent.thread_id}#comments")


def _private_recipient(page, parent: store.Item, wants_private: bool) -> str | None:
    """The recipient for a private reply, or None for a public one.

    Replies inside a private exchange are forced private to the other party.
    """
    if parent.private_to:
        other = parent.private_to if parent.pass_id == page.pass_id else parent.pass_id
        return None if other == page.pass_id else other
    if not wants_private:
        return None
    recipient = parent.pass_id
    return None if recipient == page.pass_id else recipient


async def flag(request: Request) -> Response:
    page = page_of(request)
    values = await form_values(request, "item_id")
    item = store.get_item(page.conn, values["item_id"])
    if page.pass_id is None or item is None:
        return _login(page)
    # Clicking again takes the flag back.
    if item.private_to is None and not store.remove_flag(page.conn, page.pass_id, item.id):
        store.add_flag(page.conn, page.pass_id, item.id)
    return redirect(f"/thread/{item.thread_id}#{item.id}")


async def moderation_request(request: Request) -> Response:
    page = page_of(request)
    values = await form_values(request, "item_id", "kind")
    item = store.get_item(page.conn, values["item_id"])
    if page.pass_id is None or item is None or values["kind"] not in {"unhide", "nuke"}:
        return _login(page)
    if store.add_moderation_request(page.conn, page.pass_id, item.id, values["kind"]):
        count = sum(store.request_counts(page.conn, item.id).values())
        page.app.emailer.send(
            moderation_email(page.settings.maintainer_email, values["kind"], item.id, count, page.settings.base_url)
        )
    return redirect(f"/thread/{item.id}?notice=Request+sent.+Thank+you.")


async def create_token(request: Request) -> Response:
    page = page_of(request)
    if page.pass_id is None:
        return _login(page)
    if len(store.list_api_tokens(page.conn, page.pass_id)) >= MAX_TOKENS_PER_PASS:
        return redirect("/guide/use-this-data")
    token = secrets.token_urlsafe(TOKEN_BYTES)
    store.create_api_token(page.conn, sha256_hex(token), page.pass_id, token[-4:])
    # Redirect so a reload doesn't create another token; the next page load shows it once (see Memory.take_new_token).
    page.memory.hold_new_token(page.pass_id, token)
    return redirect("/guide/use-this-data")


async def revoke_token(request: Request) -> Response:
    page = page_of(request)
    values = await form_values(request, "token_hash")
    if page.pass_id is not None:
        store.revoke_api_token(page.conn, values["token_hash"], page.pass_id)
    return redirect("/guide/use-this-data?notice=Token+revoked.")


routes = [
    Route("/submit", submit_page),
    Route("/submit", submit_post, methods=["POST"]),
    Route("/comment", comment, methods=["POST"]),
    Route("/flag", flag, methods=["POST"]),
    Route("/moderation-request", moderation_request, methods=["POST"]),
    Route("/tokens", create_token, methods=["POST"]),
    Route("/tokens/revoke", revoke_token, methods=["POST"]),
]
