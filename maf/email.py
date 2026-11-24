"""Sending email: AWS SES in production, stdout in local development.

The console backend exists so local development needs no AWS account. It is
refused outright when MAF_ENV=production (checked in settings.load_settings).

Nothing here logs or stores the recipient address: it is passed to SES and
dropped.
"""

import logging
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from . import azure_email
from .settings import Settings

SEND_WORKERS = 4  # emails go out alongside page requests, a few at a time
log = logging.getLogger("maf.email")

# HTML versions live in templates/email/ and match the site's look; every email also keeps a plain-text body.
_templates = Environment(
    loader=FileSystemLoader(Path(__file__).parent / "templates"),
    autoescape=select_autoescape(["html"]),
)


def _render(name: str, **context) -> str:
    return _templates.get_template(f"email/{name}").render(**context)

CODE_SUBJECT = "Your MAF code: {code}"
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
    subject = f"MAF {label.lower()} requested for post {item_id}"
    link = f"{base_url}/thread/{item_id}"
    tally = f"{count} request{'' if count == 1 else 's'} so far as of {(now or datetime.now(UTC)):%d/%m/%y %H:%M} UTC"
    footer = "Act on it from the server with maf requests."
    return Email(
        to=to,
        subject=subject,
        body=f"{label} requested for post: {item_id}\n{link}\n\n{tally}\n",
        html=_render("moderation.html", subject=subject, label=label, noun="post", item_id=item_id, tally=tally,
                     link=link, footer=footer),
    )


def hidden_reply_email(to: str, item_id: str, thread_id: str, flags: int, base_url: str,
                       now: datetime | None = None) -> Email:
    """Sent once when flags hide a reply, so the maintainer can read it and decide."""
    subject = f"MAF review requested for reply {item_id}"
    link = f"{base_url}/thread/{thread_id}#{item_id}"
    tally = f"Hidden after {flags} flags as of {(now or datetime.now(UTC)):%d/%m/%y %H:%M} UTC"
    footer = f"Read it on the server with maf show {item_id}, then maf unhide or maf nuke."
    return Email(
        to=to,
        subject=subject,
        body=f"Review requested for reply: {item_id}\n{link}\n\n{tally}\n\n{footer}\n",
        html=_render("moderation.html", subject=subject, label="Review", noun="reply", item_id=item_id, tally=tally,
                     link=link, footer=footer),
    )


def sign_in_paused_email(to: str, minutes_left: int, now: datetime | None = None) -> Email:
    """Sent once when wrong codes hit the site-wide cap and sign-ins pause."""
    from .memory import SITE_WRONG_CODES_LIMIT

    sent = now or datetime.now(UTC)
    headline = f"Sign-ins paused: {SITE_WRONG_CODES_LIMIT} wrong codes in the last hour"
    stamp = f"Resumes by {sent + timedelta(minutes=minutes_left):%H:%M} UTC, as of {sent:%d/%m/%y %H:%M} UTC"
    return Email(
        to=to,
        subject=f"MAF sign-ins paused: {SITE_WRONG_CODES_LIMIT} wrong codes in the last hour",
        body=f"{headline}\n{stamp}\n\nTo resume sign-ins early, restart MAF on the server with sudo systemctl restart maf.\n",
        html=_render("paused.html", subject=f"MAF sign-ins paused: {SITE_WRONG_CODES_LIMIT} wrong codes in the last hour", headline=headline, stamp=stamp),
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
        self._workers = ThreadPoolExecutor(max_workers=SEND_WORKERS, thread_name_prefix="email")

    def send_soon(self, email: Email) -> Future:
        """Sends in the background, so the page answers without waiting on the email provider.

        The returned future becomes True once the email is accepted, False if it was refused.
        Console email (local development) prints straight away.
        """
        if self._settings.console_email:
            self.send(email)
            done: Future = Future()
            done.set_result(True)
            return done
        return self._workers.submit(self._send_reporting, email)

    def _send_reporting(self, email: Email) -> bool:
        # Log the kind of failure, never the recipient.
        try:
            self.send(email)
        except Exception as error:  # noqa: BLE001
            log.error("email not sent: %s", type(error).__name__)
            return False
        return True

    def send(self, email: Email) -> None:
        if self._settings.console_email:
            # flushed so the code shows up when stdout is a pipe or a log file
            print(f"[email to {email.to}] {email.subject}\n{email.body}", flush=True)
            return
        if self._settings.email_backend == "azure":
            azure_email.send(self._settings.azure_email_connection, self._settings.email_from,
                             email.to, email.subject, email.body, email.html)
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
