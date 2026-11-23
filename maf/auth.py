"""Sign in: email -> code -> blinded token -> /redeem -> pass.

The email is used to send a code and is then forgotten. The server never sees
the token: the browser blinds it, the server signs the blinded value, and the
browser unblinds before redeeming. Nothing derived from the email is stored.
"""

import base64
import binascii

from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import Route

from . import store
from .email import code_email
from .util import new_pass_id, sha256_hex
from .web import form_values, page_of, redirect, render

ALLOWED_DOMAIN = "uni.minerva.edu"
CODE_LENGTH = 6
TOKEN_MIN_BYTES = 32


def normalise_email(raw: str) -> str | None:
    """Lowercases and checks the Minerva domain, else None."""
    email = raw.strip().lower()
    if "@" not in email:
        return None
    local, _, domain = email.rpartition("@")
    if not local or domain != ALLOWED_DOMAIN:
        return None
    return email


async def login_page(request: Request) -> Response:
    page = page_of(request)
    if page.pass_id:
        return redirect("/")
    return render(page, "login.html")


async def login_submit(request: Request) -> Response:
    page = page_of(request)
    values = await form_values(request, "email")
    email = normalise_email(values["email"])
    if email is None:
        return render(page, "login.html", status_code=400,
                      error="Enter your Minerva University email, ending in @uni.minerva.edu.",
                      email=values["email"])
    code = page.memory.issue_code(email)
    if code is None:
        return render(page, "login.html", status_code=429,
                      error="A code was already sent to that address.",
                      cooldown_seconds=max(1, page.memory.cooldown_left(email)),
                      email=values["email"])
    page.app.emailer.send(code_email(email, code))
    # Rendered directly rather than redirected, so the address reaches the code form without going into a URL.
    return render(page, "login-code.html", email=email, cooldown_seconds=page.memory.cooldown_left(email))


async def code_page(request: Request) -> Response:
    page = page_of(request)
    return render(page, "login-code.html")


async def code_submit(request: Request) -> Response:
    page = page_of(request)
    values = await form_values(request, "email", "code")
    email = normalise_email(values["email"])
    if email is None or not page.memory.check_code(email, values["code"], consume=False):
        return render(page, "login-code.html", status_code=400,
                      error="That code didn't match. Check the 6 digits, or ask for a new code.",
                      email=values["email"],
                      cooldown_seconds=page.memory.cooldown_left(email) if email else 0)
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
    if email is None or not page.memory.check_code(email, values["code"]):
        return Response('{"error":"invalid code"}', status_code=400, media_type="application/json")
    blinded = _decode_base64url(values["blinded"])
    if blinded is None:
        return Response('{"error":"bad blinded token"}', status_code=400, media_type="application/json")
    from .blind import BlindError, blind_sign as sign

    try:
        signature = sign(page.app.signing_key, blinded)
    except BlindError:
        return Response('{"error":"signing failed"}', status_code=400, media_type="application/json")
    page.memory.clear_email(email)
    return Response(
        '{"blind_sig":"%s"}' % _encode_base64url(signature), media_type="application/json"
    )


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
    return render(page, "redeem.html", status_code=400,
                  error="That pass couldn't be verified. Sign in again to get a new one.")


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
    Route("/login", login_page),
    Route("/login", login_submit, methods=["POST"]),
    Route("/login/code", code_page),
    Route("/login/code", code_submit, methods=["POST"]),
    Route("/login/blind", key),
    Route("/login/blind-sign", blind_sign, methods=["POST"]),
    Route("/redeem", redeem_page),
    Route("/redeem", redeem_submit, methods=["POST"]),
]
