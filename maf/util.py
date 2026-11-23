"""Small shared helpers: IDs, times, hashing and HTML escaping."""

import hashlib
import secrets
from datetime import UTC, date, datetime, timedelta

from .wordlist import ADJECTIVES, THINGS

# Unambiguous base32 alphabet (no i, l, o, u), so pass ids read cleanly.
ID_ALPHABET = "0123456789abcdefghjkmnpqrstvwxyz"
PASS_ID_LENGTH = 16


def _random_id(length: int) -> str:
    raw = secrets.token_bytes(length)
    return "".join(ID_ALPHABET[b % len(ID_ALPHABET)] for b in raw)[:length]


def new_item_id() -> str:
    """adjective-thing-thing, e.g. quiet-river-lantern (256 x 256 x 255 ids)."""
    adjective = secrets.choice(ADJECTIVES)
    first, second = secrets.SystemRandom().sample(THINGS, 2)
    return f"{adjective}-{first}-{second}"


def new_pass_id() -> str:
    return _random_id(PASS_ID_LENGTH)


def sha256_hex(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def utc_now() -> datetime:
    return datetime.now(UTC)


def iso(dt: datetime) -> str:
    """Timestamps are stored as UTC ISO-8601 with a Z suffix."""
    return dt.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_iso(value: str) -> datetime:
    return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)


def today() -> date:
    return utc_now().date()


def parse_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def day_start(day: date) -> datetime:
    return datetime(day.year, day.month, day.day, tzinfo=UTC)


def day_range(start: date, end: date) -> tuple[str, str]:
    """ISO bounds of the days start..end inclusive, as [start, end+1 day)."""
    return iso(day_start(start)), iso(day_start(end + timedelta(days=1)))


def escape(value: str | None) -> str:
    if not value:
        return ""
    return (
        value.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#x27;")
    )
