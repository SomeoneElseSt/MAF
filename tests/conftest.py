"""Shared fixtures: a throwaway app on a temp database, with a test client."""

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
        dates_open=True,
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
    """A pass already in the database (the signed-in viewer)."""
    from maf import store

    return store.create_pass(app.conn)


@pytest.fixture
def viewer(client: TestClient, app) -> dict:
    """A fresh pass, signed in, returned as {"pass_id": ..., "client": ...}."""
    from maf import store

    pass_id = store.create_pass(app.conn)
    return {"pass_id": pass_id, "client": sign_in_as(client, app, pass_id)}


def sign_in_as(client: TestClient, app, pass_id: str) -> TestClient:
    """Sets the session cookie to an existing pass."""
    from maf.sessions import COOKIE_NAME

    client.cookies.set(COOKIE_NAME, app.sessions._serializer.dumps(pass_id))
    return client


@pytest.fixture
def signed_in(client: TestClient, app, pass_id: str) -> TestClient:
    """A client whose cookie holds `pass_id`."""
    return sign_in_as(client, app, pass_id)
