"""API usage counts: how many requests each endpoint got per UTC day, and a command to print them.

Only totals are kept, in a small JSON file: {"2026-11-26": {"GET /api/v1/threads/{id}": 17}}. Endpoints are
the route's pattern, never the address asked for, so no post id is recorded; no times finer than the day,
no token, no pass, no IP and no query string. It's a tally, not a request log. Without MAF_USAGE_LOG nothing
is written and usage() says so.
"""

import json
import threading
from datetime import UTC, datetime
from pathlib import Path


def endpoint_of(method: str, path: str, path_params: dict) -> str:
    """The route's pattern: /api/v1/threads/quiet-river-lantern becomes /api/v1/threads/{id}."""
    for name, value in path_params.items():
        path = path.replace(str(value), "{" + name + "}")
    return f"{method} {path}"


def _read(path: Path) -> dict[str, dict[str, int]]:
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text() or "{}")
    except ValueError:
        return {}
    return data if isinstance(data, dict) else {}


class UsageLog:
    def __init__(self, path: Path | None) -> None:
        self._path = path
        self._lock = threading.Lock()

    @property
    def path(self) -> Path | None:
        return self._path

    def record(self, endpoint: str) -> None:
        if self._path is None:
            return
        day = datetime.now(UTC).strftime("%Y-%m-%d")
        with self._lock:
            counts = _read(self._path)
            today = counts.setdefault(day, {})
            today[endpoint] = today.get(endpoint, 0) + 1
            try:
                self._path.write_text(json.dumps(counts, sort_keys=True))
            except OSError:
                return


def usage(path: Path | None) -> str:
    if path is None or not path.is_file():
        return "No usage counts yet. Set MAF_USAGE_LOG to a writable file path to start counting."
    counts = _read(path)
    rows = [(day, endpoint, n) for day in sorted(counts) for endpoint, n in sorted(counts[day].items(), key=lambda kv: -kv[1])]
    if not rows:
        return f"No API requests counted in {path} yet."
    width = max(len(endpoint) for _, endpoint, _ in rows)
    total = sum(n for _, _, n in rows)
    return "\n".join([f"{total} API requests in {path}", *(f"{day}  {endpoint.ljust(width)}  {n}" for day, endpoint, n in rows)])
