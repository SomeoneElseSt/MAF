"""The Azure email sender: connection string, request signing and message shape (no network)."""

import base64
import hashlib
import hmac
import json

import pytest

from maf import azure_email
from maf.settings import ConfigError, load_settings

KEY = base64.b64encode(b"k" * 32).decode()
CONNECTION = f"endpoint=https://maf-comm.unitedstates.communication.azure.com/;accesskey={KEY}"


def test_connection_string_gives_host_and_key():
    host, key = azure_email.parse_connection_string(CONNECTION)
    assert host == "maf-comm.unitedstates.communication.azure.com"
    assert key == b"k" * 32
    with pytest.raises(azure_email.AzureEmailError):
        azure_email.parse_connection_string("endpoint=https://x.example/")


def test_requests_are_signed_the_way_azure_documents():
    body = b'{"a": 1}'
    date = "Mon, 23 Nov 2026 22:00:00 GMT"
    headers = azure_email.signed_headers("h.example", b"secret", body, date)
    content_hash = base64.b64encode(hashlib.sha256(body).digest()).decode()
    expected = base64.b64encode(hmac.new(
        b"secret", f"POST\n/emails:send?api-version=2023-03-31\n{date};h.example;{content_hash}".encode(),
        hashlib.sha256).digest()).decode()
    assert headers["x-ms-content-sha256"] == content_hash
    assert headers["Authorization"] == f"HMAC-SHA256 SignedHeaders=x-ms-date;host;x-ms-content-sha256&Signature={expected}"


def test_message_has_text_html_and_no_tracking():
    message = json.loads(azure_email.message_body("DoNotReply@maforum.net", "s@uni.minerva.edu", "Subj", "Text", "<p>Hi</p>"))
    assert message["recipients"] == {"to": [{"address": "s@uni.minerva.edu"}]}
    assert message["content"] == {"subject": "Subj", "plainText": "Text", "html": "<p>Hi</p>"}
    assert message["userEngagementTrackingDisabled"] is True


def test_azure_backend_needs_its_connection_string():
    with pytest.raises(ConfigError):
        load_settings({"EMAIL_BACKEND": "azure"})
    assert load_settings({"EMAIL_BACKEND": "azure", "AZURE_EMAIL_CONNECTION_STRING": CONNECTION}).email_backend == "azure"
    with pytest.raises(ConfigError):
        load_settings({"EMAIL_BACKEND": "sendgrid"})
