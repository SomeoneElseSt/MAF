"""In-memory state: login codes, cooldowns, view dedupe and rate limits.

None of this is ever written to disk. It lives in the process and is lost on
restart, which is what the privacy model wants: the server keeps no history of
who logged in or what anyone read.
"""

import math
import secrets
import threading
import time
from dataclasses import dataclass, field

CODE_TTL_SECONDS = 10 * 60
COOLDOWN_SECONDS = 30
VIEW_WINDOW_SECONDS = 24 * 60 * 60
RATE_WINDOW_SECONDS = 60
NEW_TOKEN_SHOW_SECONDS = 60  # how long a just-created API token waits to be shown once
MAX_CODE_ATTEMPTS = 5  # wrong guesses on one address before it has to wait
CODE_LOCK_SECONDS = 30  # the wait, shown on the Continue button
# Site-wide cap on wrong codes. Without it, someone could request codes for many addresses and guess
# 5 times on each; with it, guessing a 6-digit code takes thousands of hours of emails landing in students' inboxes.
SITE_WRONG_CODES_LIMIT = 30
SITE_WRONG_CODES_WINDOW_SECONDS = 60 * 60


def now() -> float:
    return time.monotonic()


@dataclass
class Memory:
    """All volatile server state, guarded by one lock."""

    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)
    codes: dict[str, tuple[str, float]] = field(default_factory=dict)
    code_failures: dict[str, int] = field(default_factory=dict)
    cooldowns: dict[str, float] = field(default_factory=dict)
    viewed: dict[tuple[str, str], float] = field(default_factory=dict)
    new_tokens: dict[str, tuple[str, float]] = field(default_factory=dict)
    last_view_sweep: float = 0.0
    rate: dict[str, list[float]] = field(default_factory=dict)
    wrong_codes: list[float] = field(default_factory=list)
    code_locks: dict[str, float] = field(default_factory=dict)
    pause_alerted_at: float = float("-inf")
    hide_alerted: set[str] = field(default_factory=set)

    # -- login codes -------------------------------------------------------

    def issue_code(self, email: str, ttl: float = CODE_TTL_SECONDS) -> str | None:
        """Stores a fresh 6-digit code for `email`, or returns None during cooldown."""
        with self._lock:
            current = now()
            if self.cooldowns.get(email, 0) > current:
                return None
            code = f"{secrets.randbelow(1_000_000):06d}"
            self.codes[email] = (code, current + ttl)
            self.code_failures.pop(email, None)
            self.cooldowns[email] = current + COOLDOWN_SECONDS
            return code

    def check_code(self, email: str, code: str, consume: bool = True) -> bool:
        """Compares a code. A correct code is consumed unless consume=False (the code page checks it before
        the browser's blind-sign step uses it). Every 5 wrong guesses, the address waits 30 seconds."""
        with self._lock:
            entry = self.codes.get(email)
            if entry is None or self.code_locks.get(email, 0) > now() or self._recent_wrong_codes() >= SITE_WRONG_CODES_LIMIT:
                return False
            stored, expires = entry
            if expires < now():
                self._drop_code(email)
                return False
            if not secrets.compare_digest(stored, code):
                self.wrong_codes.append(now())
                self.code_failures[email] = self.code_failures.get(email, 0) + 1
                if self.code_failures[email] >= MAX_CODE_ATTEMPTS:
                    self.code_failures.pop(email)
                    self.code_locks[email] = now() + CODE_LOCK_SECONDS
                return False
            if consume:
                self._drop_code(email)
            return True

    def _recent_wrong_codes(self) -> int:
        cutoff = now() - SITE_WRONG_CODES_WINDOW_SECONDS
        self.wrong_codes = [t for t in self.wrong_codes if t > cutoff]
        return len(self.wrong_codes)

    def code_lock_left(self, email: str) -> int:
        """Seconds until this address may try a code again (0 when it can)."""
        with self._lock:
            return max(0, math.ceil(self.code_locks.get(email, 0) - now()))

    def code_guessing_paused(self) -> bool:
        with self._lock:
            return self._recent_wrong_codes() >= SITE_WRONG_CODES_LIMIT

    def take_pause_alert(self) -> bool:
        """True once when sign-ins pause, so the maintainer gets one email per hour of guessing, not one per guess."""
        with self._lock:
            current = now()
            if self._recent_wrong_codes() < SITE_WRONG_CODES_LIMIT:
                return False
            if current - self.pause_alerted_at < SITE_WRONG_CODES_WINDOW_SECONDS:
                return False
            self.pause_alerted_at = current
            return True

    def take_hide_alert(self, item_id: str) -> bool:
        """True the first time an item is hidden, so flagging back and forth sends one email, not many."""
        with self._lock:
            if item_id in self.hide_alerted:
                return False
            self.hide_alerted.add(item_id)
            return True

    def code_guessing_minutes_left(self) -> int:
        with self._lock:
            if not self.wrong_codes:
                return 1
            return max(1, round((self.wrong_codes[0] + SITE_WRONG_CODES_WINDOW_SECONDS - now()) / 60))

    def _drop_code(self, email: str) -> None:
        self.codes.pop(email, None)
        self.code_failures.pop(email, None)

    # -- just-created API tokens --------------------------------------------

    def hold_new_token(self, pass_id: str, token: str) -> None:
        """Keeps a new token for the one page load that shows it, so it never goes into a URL or a resubmittable form."""
        with self._lock:
            self.new_tokens[pass_id] = (token, now() + NEW_TOKEN_SHOW_SECONDS)

    def take_new_token(self, pass_id: str) -> str | None:
        with self._lock:
            entry = self.new_tokens.pop(pass_id, None)
        if entry is None or entry[1] < now():
            return None
        return entry[0]

    def cooldown_left(self, email: str) -> int:
        with self._lock:
            return max(0, int(self.cooldowns.get(email, 0) - now()))

    def clear_email(self, email: str) -> None:
        """Forgets an email entirely once its code has been used."""
        with self._lock:
            self._drop_code(email)
            self.cooldowns.pop(email, None)
            self.code_locks.pop(email, None)

    # -- view dedupe -------------------------------------------------------

    def count_view(self, pass_id: str, item_id: str) -> bool:
        """True when this pass may count a view for this item (once per 24 h)."""
        with self._lock:
            current = now()
            self._sweep_views(current)
            key = (pass_id, item_id)
            seen = self.viewed.get(key)
            if seen is not None and seen > current:
                return False
            self.viewed[key] = current + VIEW_WINDOW_SECONDS
            return True

    def _sweep_views(self, current: float) -> None:
        if current - self.last_view_sweep < RATE_WINDOW_SECONDS:
            return
        self.last_view_sweep = current
        self.viewed = {k: v for k, v in self.viewed.items() if v > current}

    # -- rate limits -------------------------------------------------------

    def allow(self, key: str, limit: int, window: float = RATE_WINDOW_SECONDS) -> bool:
        """Sliding-window limiter: at most `limit` hits per `window` for `key`."""
        with self._lock:
            current = now()
            hits = [t for t in self.rate.get(key, []) if t > current - window]
            if len(hits) >= limit:
                self.rate[key] = hits
                return False
            hits.append(current)
            self.rate[key] = hits
            return True

    def retry_after(self, key: str, window: float = RATE_WINDOW_SECONDS) -> int:
        with self._lock:
            hits = self.rate.get(key, [])
            if not hits:
                return 0
            return max(1, int(hits[0] + window - now()))


def reset(memory: Memory) -> None:
    """Clears everything (tests and the 24-hour sweep)."""
    with memory._lock:
        memory.codes.clear()
        memory.cooldowns.clear()
        memory.viewed.clear()
        memory.rate.clear()
