"""Sign in: email -> code -> blinded token -> /sign-in/redeem -> pass.

The email is used to send a code and is then forgotten. The server never sees
the token: the browser blinds it, the server signs the blinded value, and the
browser unblinds before redeeming. Nothing derived from the email is stored.
"""

import base64
import binascii
import re

from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import Route

from . import store
from .email import code_email, sign_in_paused_email
from .util import new_pass_id, sha256_hex
from .web import form_values, page_of, redirect, render

ALLOWED_DOMAIN = "uni.minerva.edu"
EMAIL_PATTERN = re.compile(r"[a-z0-9._+-]+@" + re.escape(ALLOWED_DOMAIN))
PAUSED_ERROR = "MAF is currently under maintenance. Try again in {minutes} minute{s}."
CODE_LENGTH = 6
TOKEN_MIN_BYTES = 32


def normalise_email(raw: str) -> str | None:
    """Lowercases and returns a plain Minerva address, else None. Only simple addresses pass, so nothing like
    "Name <someone@gmail.com>, x@uni.minerva.edu" can reach SES and send a code somewhere else."""
    email = raw.strip().lower()
    return email if EMAIL_PATTERN.fullmatch(email) else None


def _code_page_waiting(page, email: str) -> Response:
    """After 5 wrong codes the Continue button itself counts down, like Send code does during the cooldown."""
    return render(page, "login-code.html", status_code=429, email=email,
                  cooldown_seconds=page.memory.cooldown_left(email), wait_seconds=page.memory.code_lock_left(email))


def _alert_if_paused(page) -> None:
    """Emails the maintainer the moment wrong codes hit the site-wide cap: someone is probably guessing."""
    if page.memory.take_pause_alert():
        email = sign_in_paused_email(page.settings.maintainer_email, page.memory.code_guessing_minutes_left())
        page.app.emailer.send_soon(email)


def _paused_error(minutes: int) -> str:
    return PAUSED_ERROR.format(minutes=minutes, s="" if minutes == 1 else "s")


def code_accepted(page, email: str, code: str, consume: bool = True) -> bool:
    """The emailed code, or in local development only, the fixed dev code (see settings.DEV_LOGIN_CODE)."""
    dev_code = page.settings.dev_login_code
    if dev_code is not None and code.strip() == dev_code:
        return True
    return page.memory.check_code(email, code, consume=consume)


def signed_out_only(handler):
    """Sign-in pages say so instead of starting over when the visitor already has a pass."""
    async def wrapped(request: Request) -> Response:
        page = page_of(request)
        if page.pass_id:
            return render(page, "signed-in.html", title="Sign in")
        return await handler(request)

    return wrapped


@signed_out_only
async def login_page(request: Request) -> Response:
    page = page_of(request)
    return render(page, "login.html")


@signed_out_only
async def login_submit(request: Request) -> Response:
    page = page_of(request)
    values = await form_values(request, "email")
    email = normalise_email(values["email"])
    if email is None:
        return render(page, "login.html", status_code=400,
                      error="Please enter a valid email.",
                      email=values["email"])
    code = page.memory.issue_code(email)
    if code is None:
        return render(page, "login.html", status_code=429,
                      error="A code was already sent to this address.",
                      cooldown_seconds=max(1, page.memory.cooldown_left(email)),
                      email=values["email"])
    # The email goes out in the background: the code page shows straight away.
    page.app.emailer.send_soon(code_email(email, code))
    # Rendered directly rather than redirected, so the address reaches the code form without going into a URL.
    return render(page, "login-code.html", email=email, cooldown_seconds=page.memory.cooldown_left(email))


@signed_out_only
async def code_page(request: Request) -> Response:
    page = page_of(request)
    return render(page, "login-code.html")


@signed_out_only
async def code_submit(request: Request) -> Response:
    page = page_of(request)
    values = await form_values(request, "email", "code")
    email = normalise_email(values["email"])
    if page.memory.code_guessing_paused():
        return render(page, "login-code.html", status_code=429,
                      error=_paused_error(page.memory.code_guessing_minutes_left()),
                      email=values["email"], cooldown_seconds=page.memory.cooldown_left(email) if email else 0)
    if email and page.memory.code_lock_left(email):
        return _code_page_waiting(page, email)
    if not values["code"].strip():
        return render(page, "login-code.html", status_code=400, error="Enter the 6-digit code from the email.",
                      email=values["email"], cooldown_seconds=page.memory.cooldown_left(email) if email else 0)
    if email is None or not code_accepted(page, email, values["code"], consume=False):
        _alert_if_paused(page)
        return render(page, "login-code.html", status_code=400,
                      error="That code didn't match. Check the 6 digits, or ask for a new code.",
                      email=values["email"],
                      cooldown_seconds=page.memory.cooldown_left(email) if email else 0,
                      wait_seconds=page.memory.code_lock_left(email) if email else 0)
    return render(page, "login-blind.html", email=email, code=values["code"])


async def key(request: Request) -> Response:
    """The server's public key, so the browser can blind against it."""
    from .web import page_of

    public = page_of(request).app.public_key
    return Response(
        content=(
            '{"n":"%s","e":"%s","modulusLength":%d,"saltLength":48,"hash":"SHA-384"}'
            % (format(public.n, "x").zfill(public.modulus_len * 2), format(public.e, "x").zfill(6), public.modulus_len)
        ),
        media_type="application/json",
    )


async def blind_sign(request: Request) -> Response:
    """Signs a blinded token. Checks a valid code first, then forgets the email."""
    page = page_of(request)
    values = await form_values(request, "email", "code", "blinded")
    email = normalise_email(values["email"])
    if email is None or not code_accepted(page, email, values["code"]):
        _alert_if_paused(page)
        return Response('{"error":"invalid code"}', status_code=400, media_type="application/json")
    blinded = _decode_base64url(values["blinded"])
    if blinded is None:
        return Response('{"error":"bad blinded token"}', status_code=400, media_type="application/json")
    from .blind import BlindError
    from .blind import blind_sign as sign

    try:
        signature = sign(page.app.signing_key, blinded)
    except BlindError:
        return Response('{"error":"signing failed"}', status_code=400, media_type="application/json")
    page.memory.clear_email(email)
    return Response(
        '{"blind_sig":"%s"}' % _encode_base64url(signature), media_type="application/json"
    )


@signed_out_only
async def redeem_page(request: Request) -> Response:
    page = page_of(request)
    return render(page, "redeem.html")


async def redeem_submit(request: Request) -> Response:
    """Verifies an unblinded token, stores its hash and issues a pass."""
    from .blind import verify

    page = page_of(request)
    values = await form_values(request, "token", "prepared", "signature")
    token = _decode_base64url(values["token"])
    prepared = _decode_base64url(values["prepared"])
    signature = _decode_base64url(values["signature"])
    if token is None or len(token) < TOKEN_MIN_BYTES or prepared is None or signature is None:
        return _redeem_failed(page)
    # The browser signed the randomized prepared message (32-byte prefix + token);
    # the server checks the prefix is there and the signature covers the whole thing.
    if not prepared.endswith(token):
        return _redeem_failed(page)
    if not verify(page.app.public_key, signature, prepared):
        return _redeem_failed(page)
    token_hash = sha256_hex(base64.urlsafe_b64encode(token).decode())
    pass_id = new_pass_id()
    if not store.redeem_token(page.conn, token_hash, pass_id):
        return _redeem_failed(page)
    response = redirect("/")
    page.app.sessions.set(response, pass_id)
    return response


def _redeem_failed(page) -> Response:
    return render(page, "redeem.html", status_code=400)


def _decode_base64url(value: str) -> bytes | None:
    if not value:
        return None
    padded = value + "=" * (-len(value) % 4)
    try:
        return base64.urlsafe_b64decode(padded)
    except (binascii.Error, ValueError):
        return None


def _encode_base64url(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode().rstrip("=")


routes = [
    Route("/sign-in", login_page),
    Route("/sign-in", login_submit, methods=["POST"]),
    Route("/sign-in/code", code_page),
    Route("/sign-in/code", code_submit, methods=["POST"]),
    Route("/sign-in/key", key),
    Route("/sign-in/blind-sign", blind_sign, methods=["POST"]),
    Route("/sign-in/redeem", redeem_page),
    Route("/sign-in/redeem", redeem_submit, methods=["POST"]),
]
