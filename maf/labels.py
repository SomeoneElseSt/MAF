"""Per-thread labels: a stable two-word name for one pass inside one thread.

label = wordlist(HMAC(LABEL_SECRET, pass_id || thread_id))

The same pass gets a different name in every thread, so nothing links a person's
posts across threads. The secret is server-side, so labels cannot be recomputed
from anything a reader sees.
"""

import hashlib
import hmac

from .wordlist import ADJECTIVES, ANIMALS

_LABEL_BYTES = 8


class Labeler:
    def __init__(self, secret: bytes) -> None:
        self._secret = secret

    def label(self, pass_id: str, thread_id: str) -> str:
        digest = hmac.new(
            self._secret, f"{pass_id}|{thread_id}".encode(), hashlib.sha256
        ).digest()[:_LABEL_BYTES]
        value = int.from_bytes(digest, "big")
        adjective = ADJECTIVES[value % len(ADJECTIVES)]
        animal = ANIMALS[(value // len(ADJECTIVES)) % len(ANIMALS)]
        return f"{adjective}-{animal}"
