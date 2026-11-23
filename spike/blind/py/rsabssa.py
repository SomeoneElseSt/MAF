"""RFC 9474 RSABSSA proof-of-concept for the MAF spike.

Implements Prepare, Blind, BlindSign, Finalize and Verify for the four named
variants using only the standard library plus `cryptography` for the final
RSASSA-PSS verification. Raw RSA private operations use Python integers.
"""

import hashlib
import hmac
import secrets
from dataclasses import dataclass

HASH_NAME = "sha384"
HASH_LEN = 48


@dataclass(frozen=True)
class Variant:
    name: str
    salt_len: int
    randomized: bool


VARIANTS = {
    "RSABSSA-SHA384-PSS-Randomized": Variant("RSABSSA-SHA384-PSS-Randomized", 48, True),
    "RSABSSA-SHA384-PSSZERO-Randomized": Variant("RSABSSA-SHA384-PSSZERO-Randomized", 0, True),
    "RSABSSA-SHA384-PSS-Deterministic": Variant("RSABSSA-SHA384-PSS-Deterministic", 48, False),
    "RSABSSA-SHA384-PSSZERO-Deterministic": Variant("RSABSSA-SHA384-PSSZERO-Deterministic", 0, False),
}


class BlindSignatureError(Exception):
    """A protocol step failed (invalid input, blinding error, invalid signature)."""


def hash_bytes(data: bytes) -> bytes:
    return hashlib.new(HASH_NAME, data).digest()


def mgf1(seed: bytes, length: int) -> bytes:
    """MGF1 with SHA-384, RFC 8017 Appendix B.2.1."""
    output = b""
    counter = 0
    while len(output) < length:
        output += hash_bytes(seed + counter.to_bytes(4, "big"))
        counter += 1
    return output[:length]


def emsa_pss_encode(message: bytes, em_bits: int, salt_len: int, salt: bytes | None = None) -> bytes:
    """EMSA-PSS-ENCODE with SHA-384 and MGF1-SHA-384, RFC 8017 Section 9.1.1."""
    m_hash = hash_bytes(message)
    em_len = -(-em_bits // 8)  # ceil(emBits / 8)
    if em_len < HASH_LEN + salt_len + 2:
        raise BlindSignatureError("message too long")
    if salt is None:
        salt = secrets.token_bytes(salt_len)
    h = hash_bytes(b"\x00" * 8 + m_hash + salt)
    ps = b"\x00" * (em_len - salt_len - HASH_LEN - 2)
    db = ps + b"\x01" + salt
    db_mask = mgf1(h, em_len - HASH_LEN - 1)
    masked_db = bytearray(a ^ b for a, b in zip(db, db_mask))
    unused_bits = 8 * em_len - em_bits
    masked_db[0] &= 0xFF >> unused_bits
    return bytes(masked_db) + h + b"\xbc"


def emsa_pss_verify(message: bytes, encoded: bytes, em_bits: int, salt_len: int) -> bool:
    """EMSA-PSS-VERIFY, RFC 8017 Section 9.1.2. Used by the vector tests."""
    m_hash = hash_bytes(message)
    em_len = -(-em_bits // 8)
    if len(encoded) != em_len or em_len < HASH_LEN + salt_len + 2:
        return False
    if encoded[-1] != 0xBC:
        return False
    masked_db = encoded[: em_len - HASH_LEN - 1]
    h = encoded[em_len - HASH_LEN - 1 : -1]
    unused_bits = 8 * em_len - em_bits
    if masked_db[0] & ~(0xFF >> unused_bits) & 0xFF:
        return False
    db_mask = mgf1(h, em_len - HASH_LEN - 1)
    db = bytearray(a ^ b for a, b in zip(masked_db, db_mask))
    db[0] &= 0xFF >> unused_bits
    ps_len = em_len - HASH_LEN - salt_len - 2
    if any(db[i] for i in range(ps_len)) or db[ps_len] != 0x01:
        return False
    salt = bytes(db[-salt_len:]) if salt_len else b""
    return hmac.compare_digest(h, hash_bytes(b"\x00" * 8 + m_hash + salt))


def int_to_bytes(value: int, length: int) -> bytes:
    return value.to_bytes(length, "big")


def prepare(message: bytes, variant: Variant) -> bytes:
    if not variant.randomized:
        return message
    return secrets.token_bytes(32) + message


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


def blind(public_key: PublicKey, message: bytes, variant: Variant, salt: bytes | None = None):
    """Returns (blinded_msg, inverse) as byte strings of modulus_len. `salt` is for reproducing test vectors only."""
    n = public_key.n
    encoded = emsa_pss_encode(message, n.bit_length() - 1, variant.salt_len, salt)
    m = int.from_bytes(encoded, "big")
    if m >= n:
        raise BlindSignatureError("invalid input")
    while True:
        r = secrets.randbelow(n - 1) + 1
        try:
            inverse = pow(r, -1, n)
        except ValueError:
            continue  # blinding error: retry with a new r
        break
    x = pow(r, public_key.e, n)
    z = (m * x) % n
    return int_to_bytes(z, public_key.modulus_len), int_to_bytes(inverse, public_key.modulus_len)


def blind_sign(private_key: PrivateKey, blinded_msg: bytes, variant: Variant) -> bytes:
    n = private_key.public.n
    m = int.from_bytes(blinded_msg, "big")
    if m >= n:
        raise BlindSignatureError("message representative out of range")
    s = pow(m, private_key.d, n)
    if pow(s, private_key.public.e, n) != m:
        raise BlindSignatureError("signing failure")
    return int_to_bytes(s, private_key.public.modulus_len)


def finalize(public_key: PublicKey, message: bytes, blind_sig: bytes, inverse: bytes, variant: Variant) -> bytes:
    n = public_key.n
    if len(blind_sig) != public_key.modulus_len:
        raise BlindSignatureError("unexpected input size")
    if len(inverse) != public_key.modulus_len:
        raise BlindSignatureError("unexpected input size")
    z = int.from_bytes(blind_sig, "big")
    s = (z * int.from_bytes(inverse, "big")) % n
    sig = int_to_bytes(s, public_key.modulus_len)
    if not verify(public_key, sig, message, variant):
        raise BlindSignatureError("invalid signature")
    return sig


def verify(public_key: PublicKey, signature: bytes, message: bytes, variant: Variant) -> bool:
    """RSASSA-PSS-VERIFY via `cryptography` (lazy import so vector maths needs no deps)."""
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import padding, rsa

    key = rsa.RSAPublicNumbers(public_key.e, public_key.n).public_key()
    pss = padding.PSS(mgf=padding.MGF1(hashes.SHA384()), salt_length=variant.salt_len)
    try:
        key.verify(signature, message, pss, hashes.SHA384())
    except Exception:
        return False
    return True
