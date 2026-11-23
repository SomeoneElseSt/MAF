"""Shared fixtures: a throwaway app on a temp database, with a test client."""

import base64
import secrets
from pathlib import Path

import pytest
from starlette.testclient import TestClient

from maf.main import create_app
from maf.settings import Settings


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        database_path=tmp_path / "test.db",
        label_secret=b"test-label-secret",
        session_secret=b"test-session-secret",
        email_backend="console",
        maintainer_email="maintainer@example.com",
        name_filter_enabled=False,
    )


@pytest.fixture
def starlette_app(settings: Settings):
    return create_app(settings)


@pytest.fixture
def app(starlette_app):
    return starlette_app.state.maf


@pytest.fixture
def client(starlette_app) -> TestClient:
    return TestClient(starlette_app)


@pytest.fixture
def pass_id(app) -> str:
    """A pass already in the database."""
    from maf import store

    return store.create_pass(app.conn)


@pytest.fixture
def signed_in(client: TestClient, app, pass_id: str) -> TestClient:
    """A client whose cookie holds `pass_id`."""
    response = app.sessions.set  # noqa: F841  (documents the mechanism)
    from starlette.responses import Response

    from maf.sessions import COOKIE_NAME

    raw = app.sessions._serializer.dumps(pass_id)
    client.cookies.set(COOKIE_NAME, raw)
    return client


@pytest.fixture
def browser_blind(app):
    """Runs the browser half of the blind-signature flow in Node.

    Returns a helper that blinds a fresh token and, given the server's blind
    signature, finalizes it, exactly as maf/static/login.js does.
    """

    def start() -> dict:
        token = secrets.token_bytes(32)
        return {"token": token}

    return start
