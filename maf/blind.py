"""RFC 9474 RSABSSA-SHA384-PSS-Randomized on the server.

The server holds one RSA key. It signs blinded tokens at login without seeing
the token, and later checks a redeemed token against the public key. The
implementation follows the spike in spike/blind (validated against the RFC's
test vectors).
"""

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding, rsa

SALT_LEN = 48
HASH_NAME = "sha384"


class BlindError(Exception):
    """A blind signature step failed."""


@dataclass(frozen=True)
class PublicKey:
    n: int
    e: int

    @property
    def modulus_len(self) -> int:
        return (self.n.bit_length() + 7) // 8


@dataclass(frozen=True)
class PrivateKey:
    public: PublicKey
    d: int


def _hash(data: bytes) -> bytes:
    return hashlib.new(HASH_NAME, data).digest()


def _mgf1(seed: bytes, length: int) -> bytes:
    output = b""
    counter = 0
    while len(output) < length:
        output += _hash(seed + counter.to_bytes(4, "big"))
        counter += 1
    return output[:length]


def verify(public_key: PublicKey, signature: bytes, message: bytes) -> bool:
    """RSASSA-PSS-VERIFY with SHA-384, MGF1-SHA-384 and a 48-byte salt."""
    key = rsa.RSAPublicNumbers(public_key.e, public_key.n).public_key()
    pss = padding.PSS(mgf=padding.MGF1(hashes.SHA384()), salt_length=SALT_LEN)
    try:
        key.verify(signature, message, pss, hashes.SHA384())
    except Exception:
        return False
    return True


def blind_sign(private_key: PrivateKey, blinded_msg: bytes) -> bytes:
    """Applies the RSA private operation to a blinded message (RFC 9474 §4.3)."""
    n = private_key.public.n
    m = int.from_bytes(blinded_msg, "big")
    if m >= n:
        raise BlindError("message representative out of range")
    s = pow(m, private_key.d, n)
    if pow(s, private_key.public.e, n) != m:
        raise BlindError("signing failure")
    return s.to_bytes(private_key.public.modulus_len, "big")


def generate_key(path: Path, bits: int = 2048) -> None:
    """Creates the signing key file once, readable only by its owner."""
    if path.exists():
        raise BlindError(f"key already exists at {path}")
    key = rsa.generate_private_key(public_exponent=65537, key_size=bits)
    numbers = key.private_numbers()
    payload = {
        "n": numbers.public_numbers.n,
        "e": numbers.public_numbers.e,
        "d": numbers.d,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload))
    path.chmod(0o600)


def load_key(path: Path) -> PrivateKey:
    payload = json.loads(Path(path).read_text())
    public = PublicKey(int(payload["n"]), int(payload["e"]))
    return PrivateKey(public, int(payload["d"]))
