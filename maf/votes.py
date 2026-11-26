"""Up and down votes on posts: one vote per pass per post, toggled, and the per-pass rate limit."""

from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import Route

from . import live, store
from .web import form_values, gone, page_of, redirect

VOTES_PER_MINUTE = 60
VALUES = {"up": 1, "down": -1}


async def vote(request: Request) -> Response:
    page = page_of(request)
    values = await form_values(request, "item_id", "thread_id", "value")
    item = store.get_item(page.conn, values["item_id"])
    if page.pass_id is None or item is None:
        return gone(page, values["thread_id"])
    # Posts only: replies are answered with reactions, and private items aren't posts.
    if not item.is_post or values["value"] not in VALUES:
        return redirect(f"/thread/{item.thread_id}")
    if not page.memory.allow(f"vote:{page.pass_id}", VOTES_PER_MINUTE):
        return redirect(f"/thread/{item.id}?notice=Slow+down+a+little.+Try+again+in+a+minute.")
    cast = store.cast_vote(page.conn, page.pass_id, item.id, VALUES[values["value"]])
    if cast == 1 and item.pass_id != page.pass_id:  # only upvotes reach the author's Feed
        page.app.live.publish(live.bell(item.pass_id))
    return redirect(f"/thread/{item.id}")


routes = [Route("/vote", vote, methods=["POST"])]
