"""Sending email: AWS SES in production, stdout in local development.

The console backend exists so local development needs no AWS account. It is
refused outright when MAF_ENV=production (checked in settings.load_settings).

Nothing here logs or stores the recipient address: it is passed to SES and
dropped.
"""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from .settings import Settings

# HTML versions live in templates/email/ and match the site's look; every email also keeps a plain-text body.
_templates = Environment(
    loader=FileSystemLoader(Path(__file__).parent / "templates"),
    autoescape=select_autoescape(["html"]),
)


def _render(name: str, **context) -> str:
    return _templates.get_template(f"email/{name}").render(**context)

CODE_SUBJECT = "Your code: {code}"
CODE_BODY = """Your code is {code}.

It's valid for 10 minutes. If you didn't ask for a code, ignore this email.
"""


@dataclass(frozen=True)
class Email:
    to: str
    subject: str
    body: str
    html: str = ""


def code_email(to: str, code: str) -> Email:
    """The login email: the code, with the MAF wordmark in the HTML version."""
    subject = CODE_SUBJECT.format(code=code)
    return Email(to=to, subject=subject, body=CODE_BODY.format(code=code),
                 html=_render("code.html", subject=subject, code=code))


def moderation_email(to: str, kind: str, item_id: str, count: int, base_url: str, now: datetime | None = None) -> Email:
    label = "Unhide" if kind == "unhide" else "Deletion"
    subject = f"{label} requested for post {item_id}"
    link = f"{base_url}/thread/{item_id}"
    tally = f"{count} request{'' if count == 1 else 's'} so far as of {(now or datetime.now(UTC)):%d/%m/%y %H:%M} UTC"
    return Email(
        to=to,
        subject=subject,
        body=f"{label} requested for post: {item_id}\n{link}\n\n{tally}\n",
        html=_render("moderation.html", subject=subject, label=label, item_id=item_id, tally=tally, link=link),
    )


def sign_in_paused_email(to: str, minutes_left: int, now: datetime | None = None) -> Email:
    """Sent once when wrong codes hit the site-wide cap and sign-ins pause."""
    from .memory import SITE_WRONG_CODES_LIMIT

    sent = now or datetime.now(UTC)
    headline = f"Sign-ins paused: {SITE_WRONG_CODES_LIMIT} wrong codes in the last hour"
    stamp = f"Resumes by {sent + timedelta(minutes=minutes_left):%H:%M} UTC, as of {sent:%d/%m/%y %H:%M} UTC"
    return Email(
        to=to,
        subject=headline,
        body=f"{headline}\n{stamp}\n",
        html=_render("paused.html", subject=headline, headline=headline, stamp=stamp),
    )


def _body(email: Email) -> dict:
    """SES message body: plain text always, HTML too when the email has it."""
    body = {"Text": {"Data": email.body, "Charset": "UTF-8"}}
    if email.html:
        body["Html"] = {"Data": email.html, "Charset": "UTF-8"}
    return body


class Emailer:
    """Delivers an Email through SES or the console."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._client = None

    def send(self, email: Email) -> None:
        if self._settings.console_email:
            # flushed so the code shows up when stdout is a pipe or a log file
            print(f"[email to {email.to}] {email.subject}\n{email.body}", flush=True)
            return
        self._ses().send_email(
            Source=self._settings.email_from,
            Destination={"ToAddresses": [email.to]},
            Message={
                "Subject": {"Data": email.subject},
                "Body": _body(email),
            },
        )

    def _ses(self):
        if self._client is None:
            import boto3

            self._client = boto3.client("ses", region_name=self._settings.aws_region)
        return self._client
