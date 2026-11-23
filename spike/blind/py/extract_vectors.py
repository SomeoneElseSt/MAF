"""Parses RFC 9474 Appendix A test vectors out of rfc9474.txt into vectors/*.json."""

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RFC = ROOT / "rfc9474.txt"
OUT = ROOT / "vectors"
FIELDS = ("p", "q", "n", "e", "d", "msg", "msg_prefix", "prepared_msg", "salt",
          "encoded_msg", "inv", "blinded_msg", "blind_sig", "sig")
SECTION = re.compile(r"^A\.(\d)\.\s+(RSABSSA-\S+) Test Vector")


def main() -> None:
    lines = RFC.read_text().splitlines()
    OUT.mkdir(exist_ok=True)
    current: dict[str, str] | None = None
    name = ""
    last = ""
    started = False
    for line in lines:
        if line.strip() == "Appendix A.  Test Vectors":
            started = True
            continue
        if not started:
            continue
        match = SECTION.match(line.strip())
        if match:
            if current:
                (OUT / f"{name}.json").write_text(json.dumps(current, indent=1) + "\n")
            name = match.group(2)
            current = {}
            last = ""
            continue
        if current is None:
            continue
        field = re.match(r"^   (\w+) = ?(.*)$", line)
        if field and field.group(1) in FIELDS:
            last = field.group(1)
            current[last] = field.group(2).replace(" ", "")
            continue
        if last and re.match(r"^   [0-9a-f]+$", line):
            current[last] += line.strip()
            continue
        if line.startswith("Acknowledgments"):
            break
        if line.startswith("   ") and not line.strip():
            continue
        if line.strip():
            last = ""
    if current:
        (OUT / f"{name}.json").write_text(json.dumps(current, indent=1) + "\n")
    print("wrote", sorted(p.name for p in OUT.glob("*.json")))


if __name__ == "__main__":
    main()
