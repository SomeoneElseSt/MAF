"""Python half of the interop test. Two steps, driven by run.sh:

  prepare  reads JS's blinded_A and signs it (direction A), then blinds the same
           message itself as blinded_B (direction B)
  finish   finalizes JS's blind signature of blinded_B and verifies it
"""

import base64
import json
import sys
from pathlib import Path

from rsabssa import VARIANTS, PrivateKey, PublicKey, blind, blind_sign, finalize

VECTORS = Path(__file__).resolve().parent.parent / "vectors"
VARIANT = VARIANTS["RSABSSA-SHA384-PSS-Randomized"]
MESSAGE = b"maf interop: python blind, js sign"
STATE = VECTORS / "interop.json"


def to_int(b64url: str) -> int:
    return int.from_bytes(base64.urlsafe_b64decode(b64url + "=" * (-len(b64url) % 4)), "big")


def load() -> dict:
    return json.loads(STATE.read_text())


def save(state: dict) -> None:
    STATE.write_text(json.dumps(state, indent=1) + "\n")


def keys(state: dict) -> tuple[PublicKey, PrivateKey]:
    pub = state["key"]["public"]
    pk = PublicKey(to_int(pub["n"]), to_int(pub["e"]))
    return pk, PrivateKey(pk, to_int(state["key"]["private"]["d"]))


def prepare() -> int:
    state = load()
    pk, sk = keys(state)
    state["py_blind_sig_A"] = blind_sign(sk, bytes.fromhex(state["js_blinded_A"]), VARIANT).hex()
    blinded_b, inv_b = blind(pk, MESSAGE, VARIANT)
    state["py_blinded_B"] = blinded_b.hex()
    state["py_inv_B"] = inv_b.hex()
    save(state)
    print("python blindSign (A) + blind (B) done")
    return 0


def finish() -> int:
    state = load()
    pk, _ = keys(state)
    sig = finalize(pk, MESSAGE, bytes.fromhex(state["js_blind_sig_B"]), bytes.fromhex(state["py_inv_B"]), VARIANT)
    print("python finalized JS's blind signature of a Python blind and verified it:", sig.hex()[:16] + "...")
    return 0


if __name__ == "__main__":
    step = sys.argv[1] if len(sys.argv) > 1 else ""
    if step == "prepare":
        raise SystemExit(prepare())
    if step == "finish":
        raise SystemExit(finish())
    print("usage: python py/interop.py prepare|finish")
    raise SystemExit(2)
