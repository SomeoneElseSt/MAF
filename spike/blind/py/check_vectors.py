"""Checks the spike's RSABSSA implementation against every RFC 9474 Appendix A vector."""

import json
from pathlib import Path

from rsabssa import (
    VARIANTS,
    PrivateKey,
    PublicKey,
    blind,
    blind_sign,
    emsa_pss_encode,
    emsa_pss_verify,
    finalize,
    verify,
)

VECTORS = Path(__file__).resolve().parent.parent / "vectors"


def h(value: str) -> bytes:
    return bytes.fromhex(value)


def check_one(name: str, v: dict) -> list[str]:
    failures = []
    variant = VARIANTS[name]
    pk = PublicKey(int(v["n"], 16), int(v["e"], 16))
    sk = PrivateKey(pk, int(v["d"], 16))
    prepared = h(v["prepared_msg"])
    em_bits = pk.n.bit_length() - 1

    encoded = emsa_pss_encode(prepared, em_bits, variant.salt_len, h(v["salt"]))
    if encoded != h(v["encoded_msg"]):
        failures.append("emsa_pss_encode")
    if not emsa_pss_verify(prepared, h(v["encoded_msg"]), em_bits, variant.salt_len):
        failures.append("emsa_pss_verify")

    # `r` is random, so recover the vector's r from its inv and reproduce blinded_msg exactly.
    vector_inv = int(v["inv"], 16)
    r = pow(vector_inv, -1, pk.n)
    m = int.from_bytes(h(v["encoded_msg"]), "big")
    blinded = (m * pow(r, pk.e, pk.n)) % pk.n
    if blinded.to_bytes(pk.modulus_len, "big") != h(v["blinded_msg"]):
        failures.append("blind (blinded_msg)")
    if (r * vector_inv) % pk.n != 1:
        failures.append("inv is the inverse of r")

    blind_sig = blind_sign(sk, h(v["blinded_msg"]), variant)
    if blind_sig != h(v["blind_sig"]):
        failures.append("blind_sign")

    sig = finalize(pk, prepared, h(v["blind_sig"]), h(v["inv"]), variant)
    if sig != h(v["sig"]):
        failures.append("finalize")
    if not verify(pk, sig, prepared, variant):
        failures.append("verify")
    return failures


def main() -> int:
    bad = 0
    for path in sorted(VECTORS.glob("RSABSSA-*.json")):
        name = path.stem
        failures = check_one(name, json.loads(path.read_text()))
        status = "ok" if not failures else "FAIL: " + ", ".join(failures)
        print(f"{name:42} {status}")
        bad += bool(failures)
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
