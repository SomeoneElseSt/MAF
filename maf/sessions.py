"""The session cookie: a long-lived HttpOnly cookie holding the pass id.

Passes don't expire, so the cookie is long-lived too. It is signed so it can't
be forged, and it holds nothing but the anonymous pass id.
"""

from starlette.requests import Request
from starlette.responses import Response

from .settings import Settings

COOKIE_NAME = "maf_pass"
SESSION_MAX_AGE = 10 * 365 * 24 * 60 * 60  # ten years: passes don't expire


class Sessions:
    def __init__(self, settings: Settings) -> None:
        from itsdangerous import URLSafeSerializer

        self._serializer = URLSafeSerializer(settings.session_secret, salt="maf-pass")
        self._secure = settings.is_production

    def pass_id(self, request: Request) -> str | None:
        raw = request.cookies.get(COOKIE_NAME)
        if not raw:
            return None
        try:
            value = self._serializer.loads(raw)
        except Exception:
            return None
        return value if isinstance(value, str) else None

    def set(self, response: Response, pass_id: str) -> None:
        response.set_cookie(
            COOKIE_NAME,
            self._serializer.dumps(pass_id),
            max_age=SESSION_MAX_AGE,
            httponly=True,
            samesite="lax",
            secure=self._secure,
            path="/",
        )

    def clear(self, response: Response) -> None:
        response.delete_cookie(COOKIE_NAME, path="/")
