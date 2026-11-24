"""Emoji reactions: the fixed set, toggling, and the per-pass rate limit."""

from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import Route

from . import store
from .emoji import PICKER_EMOJI
from .web import form_values, page_of, redirect

REACTIONS_PER_MINUTE = 60


async def react(request: Request) -> Response:
    page = page_of(request)
    values = await form_values(request, "item_id", "emoji")
    item = store.get_item(page.conn, values["item_id"])
    if page.pass_id is None or item is None:
        return redirect("/sign-in")
    if values["emoji"] not in PICKER_EMOJI:
        return redirect(f"/thread/{item.id}")
    if item.private_to and page.pass_id not in (item.pass_id, item.private_to):
        return redirect(f"/thread/{item.id}")
    if not page.memory.allow(f"react:{page.pass_id}", REACTIONS_PER_MINUTE):
        return redirect(f"/thread/{item.id}?notice=Slow+down+a+little.+Try+again+in+a+minute.")
    store.toggle_reaction(page.conn, page.pass_id, item.id, values["emoji"])
    page.app.live.publish(item.thread_id)
    return redirect(f"/thread/{item.thread_id}#{item.id}")


routes = [Route("/react", react, methods=["POST"])]
