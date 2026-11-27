"""Alerts: web push to devices that turned them on.

An alert says only what happened ("New reply to your post") and links to it: never anyone's words, so nothing
private shows on a lock screen. Each one is encrypted for its device (RFC 8291), so the push service that carries
it (Apple, Google, Mozilla) can't read it either. Sending happens off the request, a few at a time; a device
the push service says is gone is forgotten.
"""

import base64
import json
import logging
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
from py_vapid import Vapid
from pywebpush import WebPushException, webpush
from starlette.requests import Request
from starlette.responses import FileResponse, JSONResponse, Response
from starlette.routing import Route

from . import store
from .settings import Settings
from .web import form_values, page_of

SEND_WORKERS = 4
ALERT_TTL_SECONDS = 24 * 60 * 60  # an alert a phone couldn't get within a day isn't worth showing
GONE = {404, 410}  # the push service's answer for a device that unsubscribed or was reset
MAX_FIELD = 1024  # endpoints are a few hundred characters; anything longer isn't a real one
log = logging.getLogger("maf.push")


def load_vapid(settings: Settings) -> Vapid | None:
    """The key that signs alerts. Production reads MAF_VAPID_KEY; local development makes one next to the
    database. Without a key in production, alerts are off and everything else works."""
    path = settings.vapid_key_path
    if path is None and settings.is_production:
        log.warning("MAF_VAPID_KEY isn't set: alerts are off")
        return None
    if path is None:
        path = Path(f"{settings.database_path}.vapid")
    if not path.exists():
        key = Vapid()
        key.generate_keys()
        key.save_key(str(path))
    return Vapid.from_file(str(path))


class Pusher:
    def __init__(self, settings: Settings):
        self.vapid = load_vapid(settings)
        self.subject = f"mailto:{settings.contact_email}"
        self.pool = ThreadPoolExecutor(max_workers=SEND_WORKERS, thread_name_prefix="push")

    @property
    def public_key(self) -> str:
        """The key browsers need to subscribe, as base64url (the form PushManager.subscribe takes)."""
        if self.vapid is None:
            return ""
        raw = self.vapid.public_key.public_bytes(Encoding.X962, PublicFormat.UncompressedPoint)
        return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()

    def alert(self, app, devices: list[dict], body: str, url: str, tag: str) -> None:
        """Queues one alert to each device; returns at once."""
        if self.vapid is None or not devices:
            return
        payload = json.dumps({"title": app.settings.site_name, "body": body, "url": url, "tag": tag})
        for device in devices:
            self.pool.submit(self._send, app, device, payload)

    def _send(self, app, device: dict, payload: str) -> None:
        subscription = {"endpoint": device["endpoint"], "keys": {"p256dh": device["p256dh"], "auth": device["auth"]}}
        try:
            webpush(subscription, payload, vapid_private_key=self.vapid, vapid_claims={"sub": self.subject},
                    ttl=ALERT_TTL_SECONDS, timeout=10)
        except WebPushException as error:
            status = error.response.status_code if error.response is not None else None
            if status in GONE:
                store.remove_push_device(app.conn, device["endpoint"])
                return
            log.warning("push failed: %s", status)
        except Exception as error:  # a network problem must never reach the page that posted the reply
            log.warning("push failed: %s", type(error).__name__)


def alert_reply(page, reply: store.Item) -> None:
    """Alerts for a new reply: whoever's Feed it reaches (not reactions), on every device they turned on."""
    pusher = page.app.pusher
    if pusher.vapid is None:
        return
    url = f"/thread/{reply.thread_id}#{reply.id}"
    for pass_id, label in store.reply_alerts(page.conn, reply).items():
        pusher.alert(page.app, store.push_devices(page.conn, pass_id), label, url, tag=reply.thread_id)


def _valid(value: str) -> bool:
    return 0 < len(value) <= MAX_FIELD


async def subscribe(request: Request) -> Response:
    """Turns alerts on for this device: the browser's push address and keys, tied to this pass."""
    page = page_of(request)
    if page.pass_id is None:
        return Response(status_code=401)
    values = await form_values(request, "endpoint", "p256dh", "auth")
    if not values["endpoint"].startswith("https://") or not all(_valid(v) for v in values.values()):
        return Response(status_code=400)
    store.add_push_device(page.conn, page.pass_id, values["endpoint"], values["p256dh"], values["auth"])
    return Response(status_code=204)


async def unsubscribe(request: Request) -> Response:
    """Turns alerts off for this device."""
    page = page_of(request)
    if page.pass_id is None:
        return Response(status_code=401)
    values = await form_values(request, "endpoint")
    store.remove_push_device(page.conn, values["endpoint"], page.pass_id)
    return Response(status_code=204)


async def service_worker(request: Request) -> Response:
    """sw.js at the site's root, so it can show alerts for every page."""
    path = page_of(request).settings.static_dir / "sw.js"
    return FileResponse(path, media_type="text/javascript", headers={"Cache-Control": "no-cache"})


async def manifest(request: Request) -> Response:
    """What "Add to Home Screen" installs. iPhones only send alerts to sites added this way."""
    settings = page_of(request).settings
    return JSONResponse({
        "name": settings.forum_name, "short_name": settings.site_name, "start_url": "/", "scope": "/",
        "display": "standalone", "background_color": "#ffffff", "theme_color": "#ffffff",
        "icons": [{"src": "/static/icon-180.png", "sizes": "180x180", "type": "image/png"}],
    }, media_type="application/manifest+json")


routes = [
    Route("/push/subscribe", subscribe, methods=["POST"]),
    Route("/push/unsubscribe", unsubscribe, methods=["POST"]),
    Route("/sw.js", service_worker),
    Route("/manifest.webmanifest", manifest),
]
