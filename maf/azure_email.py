"""Sending through Azure Communication Services Email, over its REST API (no SDK).

Configured with AZURE_EMAIL_CONNECTION_STRING ("endpoint=https://….communication.azure.com/;accesskey=…").
Requests are signed with the access key (HMAC-SHA256), as Azure's REST docs describe. The recipient is
passed to Azure and dropped; nothing is logged or stored.
"""

import base64
import hashlib
import hmac
import json
import urllib.request
from email.utils import formatdate
from urllib.parse import urlparse

API_PATH = "/emails:send?api-version=2023-03-31"
REQUEST_TIMEOUT = 15


class AzureEmailError(Exception):
    """Azure refused or failed to accept the email."""


def parse_connection_string(connection: str) -> tuple[str, bytes]:
    """Returns (endpoint host, access key bytes)."""
    parts = dict(part.split("=", 1) for part in connection.split(";") if "=" in part)
    host = urlparse(parts.get("endpoint", "")).netloc
    if not host or not parts.get("accesskey"):
        raise AzureEmailError("AZURE_EMAIL_CONNECTION_STRING needs endpoint=… and accesskey=…")
    return host, base64.b64decode(parts["accesskey"])


def signed_headers(host: str, key: bytes, body: bytes, date: str) -> dict[str, str]:
    content_hash = base64.b64encode(hashlib.sha256(body).digest()).decode()
    to_sign = f"POST\n{API_PATH}\n{date};{host};{content_hash}"
    signature = base64.b64encode(hmac.new(key, to_sign.encode(), hashlib.sha256).digest()).decode()
    return {
        "Content-Type": "application/json",
        "x-ms-date": date,
        "x-ms-content-sha256": content_hash,
        "Authorization": f"HMAC-SHA256 SignedHeaders=x-ms-date;host;x-ms-content-sha256&Signature={signature}",
    }


def message_body(sender: str, to: str, subject: str, text: str, html: str | None) -> bytes:
    content = {"subject": subject, "plainText": text}
    if html:
        content["html"] = html
    message = {
        "senderAddress": sender,
        "recipients": {"to": [{"address": to}]},
        "content": content,
        "userEngagementTrackingDisabled": True,  # no tracking pixels or rewritten links
    }
    return json.dumps(message).encode()


def send(connection: str, sender: str, to: str, subject: str, text: str, html: str | None) -> None:
    host, key = parse_connection_string(connection)
    body = message_body(sender, to, subject, text, html)
    headers = signed_headers(host, key, body, formatdate(usegmt=True))
    request = urllib.request.Request(f"https://{host}{API_PATH}", data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT) as response:
            if response.status != 202:
                raise AzureEmailError(f"Azure answered {response.status}")
    except urllib.error.HTTPError as error:
        # Only the status: Azure's error text can quote the recipient, and that would end up in the log.
        raise AzureEmailError(f"Azure answered {error.code}") from None
