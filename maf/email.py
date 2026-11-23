"""Sending email: AWS SES in production, stdout in local development.

The console backend exists so local development needs no AWS account. It is
refused outright when MAF_ENV=production (checked in settings.load_settings).

Nothing here logs or stores the recipient address: it is passed to SES and
dropped.
"""

from dataclasses import dataclass

from .settings import Settings

CODE_SUBJECT = "Your code: {code}"
CODE_BODY = """Your code is {code}.

It works for 10 minutes. If you didn't ask for it, ignore this email.
"""


@dataclass(frozen=True)
class Email:
    to: str
    subject: str
    body: str


def code_email(to: str, code: str) -> Email:
    """The deliberately plain login email: no MAF branding."""
    return Email(to=to, subject=CODE_SUBJECT.format(code=code), body=CODE_BODY.format(code=code))


def moderation_email(to: str, kind: str, item_id: str, count: int, base_url: str) -> Email:
    label = "Unhide" if kind == "unhide" else "Deletion"
    return Email(
        to=to,
        subject=f"{label} requested for post #{item_id}",
        body=(
            f"{label} requested for post #{item_id} ({count} request{'s' if count != 1 else ''} so far).\n"
            f"{base_url}/item/{item_id}\n"
        ),
    )


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
                "Body": {"Text": {"Data": email.body}},
            },
        )

    def _ses(self):
        if self._client is None:
            import boto3

            self._client = boto3.client("ses", region_name=self._settings.aws_region)
        return self._client
