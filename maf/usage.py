"""API usage counts: one line per API request in a log file, and a command to total them.

The line holds only the time and the endpoint. No token, no pass, no IP and no
query string, so the file can't say who read what. Without MAF_USAGE_LOG nothing
is written and usage() says so.
"""

import threading
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path


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
        stamp = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
        with self._lock:
            try:
                with self._path.open("a") as log:
                    log.write(f"{stamp} {endpoint}\n")
            except OSError:
                return


def read_usage(path: Path) -> Counter:
    """Counts per endpoint. Skips lines that don't look like one of ours."""
    counts: Counter = Counter()
    for line in path.read_text().splitlines():
        _, _, endpoint = line.partition(" ")
        if endpoint.partition(" ")[2].startswith("/api/"):
            counts[endpoint] += 1
    return counts


def usage(path: Path | None) -> str:
    if path is None or not path.is_file():
        return "No usage log yet. Set MAF_USAGE_LOG to a writable file path to start one."
    counts = read_usage(path)
    if not counts:
        return f"No API requests in {path} yet."
    total = sum(counts.values())
    width = max(len(endpoint) for endpoint in counts)
    rows = [f"{endpoint.ljust(width)}  {count}" for endpoint, count in counts.most_common()]
    return "\n".join([f"{total} API requests in {path}", *rows])
