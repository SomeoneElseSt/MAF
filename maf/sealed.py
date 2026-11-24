"""Checks the shape of sealed private replies and per-thread public keys.

Private replies are encrypted in the browser (maf/static/private.js) with a key both
people can derive: ECDH P-256 between their per-thread key pairs, then HKDF and AES-GCM.
The server can't decrypt them. It only checks that what it stores looks like a sealed
reply between the right two keys, so nothing readable is ever stored by mistake.
"""

import base64
import binascii
import json

PUBLIC_KEY_BYTES = 65  # an uncompressed P-256 point: 0x04, then x and y
UNCOMPRESSED_POINT = 0x04
IV_BYTES = 12
MAX_SEALED_CHARS = 40_000
SEALED_VERSION = 1
SEALED_FIELDS = {"v", "iv", "ct", "from", "to"}


def _decode(value: object) -> bytes | None:
    if not isinstance(value, str) or not value:
        return None
    padded = value + "=" * (-len(value) % 4)
    try:
        return base64.urlsafe_b64decode(padded.encode("ascii"))
    except (binascii.Error, UnicodeEncodeError, ValueError):
        return None


def valid_public_key(value: object) -> bool:
    raw = _decode(value)
    return raw is not None and len(raw) == PUBLIC_KEY_BYTES and raw[0] == UNCOMPRESSED_POINT


def parse_sealed(raw: str) -> dict | None:
    """The sealed reply as a dict, or None if it isn't one."""
    if not raw or len(raw) > MAX_SEALED_CHARS:
        return None
    try:
        sealed = json.loads(raw)
    except ValueError:
        return None
    if not isinstance(sealed, dict) or set(sealed) != SEALED_FIELDS or sealed["v"] != SEALED_VERSION:
        return None
    iv = _decode(sealed["iv"])
    if iv is None or len(iv) != IV_BYTES or not _decode(sealed["ct"]):
        return None
    if not valid_public_key(sealed["from"]) or not valid_public_key(sealed["to"]):
        return None
    return sealed
