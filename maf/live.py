"""Live pings for open thread pages (new replies and reactions), over Server-Sent Events.

A ping carries no content. Each page then fetches the thread as its own viewer, so a private
reply only ever shows up for the two people in it. Subscribers live in memory in this one process;
nothing about who is watching is stored or logged.
"""

import asyncio
from collections import defaultdict

KEEPALIVE_SECONDS = 25  # a comment line this often keeps proxies from closing an idle stream
RETRY_MILLISECONDS = 3000  # how soon browsers reconnect, e.g. after a release restarts the server


class Notifier:
    def __init__(self) -> None:
        self._queues: dict[str, set[asyncio.Queue]] = defaultdict(set)

    def subscribe(self, thread_id: str) -> asyncio.Queue:
        # One pending ping is enough: the page re-checks the whole thread when it wakes.
        queue: asyncio.Queue = asyncio.Queue(maxsize=1)
        self._queues[thread_id].add(queue)
        return queue

    def unsubscribe(self, thread_id: str, queue: asyncio.Queue) -> None:
        subscribers = self._queues.get(thread_id)
        if subscribers is None:
            return
        subscribers.discard(queue)
        if not subscribers:
            del self._queues[thread_id]

    def publish(self, thread_id: str) -> None:
        for queue in self._queues.get(thread_id, ()):
            if queue.empty():
                queue.put_nowait(True)

    def watching(self, thread_id: str) -> int:
        return len(self._queues.get(thread_id, ()))


async def stream(notifier: Notifier, thread_id: str, queue: asyncio.Queue):
    """The text/event-stream body: a retry hint, then a `change` event per ping, with keepalives between."""
    try:
        yield f"retry: {RETRY_MILLISECONDS}\n\n"
        while True:
            try:
                await asyncio.wait_for(queue.get(), KEEPALIVE_SECONDS)
            except TimeoutError:
                yield ": keepalive\n\n"
                continue
            yield "event: change\ndata: 1\n\n"
    finally:
        notifier.unsubscribe(thread_id, queue)
