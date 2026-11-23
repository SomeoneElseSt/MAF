#!/usr/bin/env bash
# Reruns the whole spike: RFC vectors (Python), RFC signature check (JS), then interop both ways.
set -euo pipefail
cd "$(dirname "$0")"
PY="uv run --no-project --python 3.12 --with cryptography python"

echo "== 1. Python RSABSSA against the RFC 9474 Appendix A vectors"
$PY py/extract_vectors.py >/dev/null
$PY py/check_vectors.py

echo "== 2. JS library verifies an RFC 9474 published signature"
node js/vector-check.mjs

echo "== 3. Interop: JS blinds, Python blind-signs, JS finalizes; and Python blinds, JS blind-signs, Python finalizes"
rm -f vectors/interop.json
node js/interop.mjs blind
$PY py/interop.py prepare
node js/interop.mjs sign
node js/interop.mjs verify
$PY py/interop.py finish
echo "== all spike checks passed"
