"""Display helpers shared by templates: relative times, day headings, ranges."""

from datetime import date, datetime, timedelta

from markupsafe import Markup

from .util import parse_iso, today

DAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
MONTH_NAMES = [
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
]


def _plural(n: int, word: str) -> str:
    return f"{n} {word}{'' if n == 1 else 's'}"


def relative_time(created_at: str, now: datetime | None = None) -> Markup:
    """Plain-language age in a <time>, so the browser can redo the day-based ones ('Yesterday') in its own
    time zone (localdays.js): '2 hours ago', 'Yesterday', 'Friday 20 November'."""
    return Markup('<time class="rel" datetime="{}">{}</time>').format(created_at, _age(created_at, now))


def _age(created_at: str, now: datetime | None = None) -> str:
    moment = parse_iso(created_at)
    current = now or datetime.now(moment.tzinfo)
    seconds = max(0, int((current - moment).total_seconds()))
    if seconds < 60:
        return "just now"
    if seconds < 3600:
        return f"{_plural(seconds // 60, 'minute')} ago"
    if seconds < 86400:
        return f"{_plural(seconds // 3600, 'hour')} ago"
    days = (current.date() - moment.date()).days
    if days == 1:
        return "Yesterday"
    if days < 7:
        return f"{days} days ago"
    return day_label(moment.date())


def day_label(day: date) -> str:
    """'Today', 'Yesterday', or 'Thursday 19 November'."""
    delta = (today() - day).days
    if delta == 0:
        return "Today"
    if delta == 1:
        return "Yesterday"
    return f"{DAY_NAMES[day.weekday()]} {day.day} {MONTH_NAMES[day.month - 1]}"


def short_date(day: date) -> str:
    return f"{day.day} {MONTH_NAMES[day.month - 1][:3]}"


def range_label(start: date, end: date) -> str:
    """'19 to 22 November', or '28 October to 1 November' across months."""
    if start.month == end.month:
        return f"{start.day} to {end.day} {MONTH_NAMES[end.month - 1]}"
    return f"{short_date(start)} to {short_date(end)}"


def four_day_window(end: date) -> tuple[date, date]:
    return end - timedelta(days=3), end


def metadata(item, comment_count: int | None = None, include_time: bool = True, score: int | None = None) -> Markup:
    """The plain-language details line: '5 points, 2 hours ago, 14 comments, 61 views'."""
    # A negative score isn't shown, so a post that was voted down isn't marked out for it.
    parts = [] if score is None or score < 0 else [_plural(score, "point")]
    if include_time:
        parts.append(relative_time(item.created_at))
    if comment_count is not None:
        parts.append(_plural(comment_count, "comment"))
    parts.append(_plural(item.views, "view"))
    return Markup(", ").join(parts)


def host(url: str | None) -> str:
    if not url:
        return ""
    from urllib.parse import urlsplit

    return urlsplit(url).hostname or ""
