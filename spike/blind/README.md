# Blind-signature spike (RFC 9474)

Goal: prove that a token blinded and finalised in the browser library
(`@cloudflare/blindrsa-ts`) is signed by a Python RFC 9474 implementation on the
server, and the other way round.

**Result: interop works both ways.** No Python library on PyPI implements RSABSSA
(the RFC 9474 blind RSA scheme), so the spike implements
`RSABSSA-SHA384-PSS-Randomized` on top of the standard library and `cryptography`
for the final PSS check, and validates it against the RFC's published test vectors.

## Versions

| Piece | Version |
| --- | --- |
| `@cloudflare/blindrsa-ts` (the `blindrsa-ts` library) | 0.4.6 |
| Node.js (runs the JS half under `webcrypto`) | 26.x |
| Python | 3.12 (via `uv run --python 3.12`) |
| `cryptography` (PSS verify only) | whatever `uv` resolves, currently 46.x |

The variant used for interop is `RSABSSA-SHA384-PSS-Randomized` (SHA-384, MGF1-SHA384,
48-byte salt, randomised message preparation), with a 2048-bit key and `e = 65537`.

## What runs

`run.sh` runs three groups of checks:

1. **Python against the RFC vectors** (`py/check_vectors.py`). For all four named variants it
   reproduces `encoded_msg`, `blind_sig`, `finalize` and the final signature `sig` from
   Appendix A, and verifies the PSS encoding. The vectors' `blinded_msg` is reproduced by
   recovering their random `r` from `inv`.
2. **JS verifies an RFC signature** (`js/vector-check.mjs`). The JS library's `verify` accepts
   the RFC's published `sig` for the deterministic PSS variant.
3. **Interop between the two** (`js/interop.mjs`, `py/interop.py`), both directions, with a
   freshly generated key each run:
   - *JS blinds → Python signs → JS finalizes*: the JS `finalize` verifies the signature.
   - *Python blinds → JS signs → Python finalizes*: the Python `finalize` verifies the signature.

## How to rerun

```sh
cd spike/blind
npm install        # once, installs @cloudflare/blindrsa-ts 0.4.6
./run.sh
```

`run.sh` needs `uv` and Node. It re-extracts the test vectors from `rfc9474.txt`
(checked in) into `vectors/`, then runs every check. A successful run ends with
`== all spike checks passed`.

## Files

| File | Purpose |
| --- | --- |
| `py/rsabssa.py` | Prepare, Blind, BlindSign, Finalize, Verify for the four variants |
| `py/check_vectors.py` | RFC 9474 Appendix A vectors against the Python code |
| `py/extract_vectors.py` | Parses `rfc9474.txt` into `vectors/*.json` |
| `py/interop.py` | Python half of the interop test |
| `js/vector-check.mjs` | JS library verifies an RFC signature |
| `js/interop.mjs` | JS half of the interop test |
| `rfc9474.txt` | The RFC, for its test vectors |

## Notes for the real app

- The server only needs BlindSign and the public key; it never sees the token.
- `cryptography` is needed for the client-side style verification, but the server-side
  app can also verify in Python when a pass is redeemed, which is what the spike's
  `verify` does. The raw private-key operation uses Python's `pow`; a production
  deployment should keep the RSA key in an HSM or at least a separate file with tight
  permissions, since `pow` is not constant-time (RFC 9474 Section 7.1).
- The browser side vendors `blindrsa-ts` as a single file (see `maf/static/`).
