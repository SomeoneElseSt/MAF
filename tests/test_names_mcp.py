"""The name filter (Presidio) and its warning flow, and the MCP server.

The name-filter tests need the spaCy model; they are skipped without it.
"""

import json

import pytest

from maf import store


@pytest.fixture(scope="module")
def presidio_ready():
    pytest.importorskip("presidio_analyzer")
    import spacy

    try:
        spacy.load("en_core_web_md")
    except OSError:
        pytest.skip("spaCy model en_core_web_md is not installed")


@pytest.fixture
def filtering_app(tmp_path, presidio_ready):
    from starlette.testclient import TestClient

    from maf.main import create_app
    from maf.settings import Settings

    settings = Settings(
        database_path=tmp_path / "names.db",
        label_secret=b"l",
        session_secret=b"s",
        email_backend="console",
        name_filter_enabled=True,
        spacy_model="en_core_web_md",
    )
    starlette = create_app(settings)
    return starlette.state.maf, TestClient(starlette)


def sign_in(client, app):
    from maf.sessions import COOKIE_NAME

    pass_id = store.create_pass(app.conn)
    client.cookies.set(COOKIE_NAME, app.sessions._serializer.dumps(pass_id))
    return pass_id


def test_a_name_is_detected(filtering_app):
    app, _ = filtering_app
    assert app.name_filter.finds_name("I sat next to Priya Raman in seminar today")


def test_ordinary_text_is_not(filtering_app):
    app, _ = filtering_app
    assert not app.name_filter.finds_name("Should we move the Berlin rotation to fall?")


def test_warning_keeps_the_text_and_offers_post_anyway(filtering_app):
    app, client = filtering_app
    sign_in(client, app)
    body = client.post("/submit", data={"title": "What Ben Nelson got right", "text": "Reading the essays"}).text
    assert "This looks like it names someone" in body
    assert "Reading the essays" in body
    assert "Post anyway" in body and "Edit post" in body


def test_confirm_names_posts_anyway(filtering_app):
    app, client = filtering_app
    sign_in(client, app)
    response = client.post(
        "/submit",
        data={"title": "What Ben Nelson got right", "text": "Reading", "confirm_names": "1"},
        follow_redirects=False,
    )
    assert response.status_code == 303


def test_comment_with_a_name_is_refused(filtering_app):
    app, client = filtering_app
    pass_id = sign_in(client, app)
    post = store.create_post(app.conn, pass_id, "Post", "body", None, [])
    client.post("/comment", data={"parent_id": post.id, "text": "Priya Raman told me"}, follow_redirects=False)
    assert store.comment_count(app.conn, post.id) == 0


# -- MCP -----------------------------------------------------------------


@pytest.fixture
def api_site(tmp_path, monkeypatch):
    """A live MAF app plus a token, for the MCP server to call over HTTP."""
    import uvicorn
    from starlette.testclient import TestClient

    from maf import store
    from maf.main import create_app
    from maf.settings import Settings
    from maf.util import sha256_hex

    settings = Settings(database_path=tmp_path / "mcp.db", label_secret=b"l", session_secret=b"s",
                        email_backend="console", name_filter_enabled=False)
    starlette = create_app(settings)
    app = starlette.state.maf
    app.http = TestClient(starlette)
    pass_id = store.create_pass(app.conn)
    store.create_post(app.conn, pass_id, "MCP visible post", "body about otters", None, ["berlin"])
    token = "mcp-test-token"
    store.create_api_token(app.conn, sha256_hex(token), pass_id)
    return app, token


def run_mcp(monkeypatch, app, token, calls):
    """Runs the real maf-mcp server in-process, talking to it over a memory pipe.

    The server is started exactly as `maf-mcp` starts it (mcp.run), but its
    HTTP calls go to the in-process app through a patched urlopen.
    """
    import asyncio
    import os

    import anyio
    from mcp import ClientSession
    from mcp.shared.memory import create_client_server_memory_streams

    import maf.mcp as mcp_module
    from starlette.testclient import TestClient

    client = app.http

    class FakeResponse:
        def __init__(self, response):
            self._response = response

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def read(self):
            return self._response.content

    def fake_urlopen(request, timeout):
        path = request.full_url.replace("http://testserver", "")
        response = client.get(path, headers={"Authorization": request.get_header("Authorization")})
        if response.status_code >= 400:
            raise mcp_module.urllib.error.HTTPError(path, response.status_code, "", {}, None)
        return FakeResponse(response)

    monkeypatch.setattr(mcp_module.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setenv("MAF_TOKEN", token)
    monkeypatch.setenv("MAF_URL", "http://testserver")

    async def main():
        async with create_client_server_memory_streams() as ((client_read, client_write), (server_read, server_write)):
            server_task = asyncio.create_task(mcp_module.serve(server_read, server_write))
            try:
                async with ClientSession(client_read, client_write) as session:
                    await session.initialize()
                    return await calls(session)
            finally:
                server_task.cancel()

    return asyncio.run(main())


@pytest.mark.parametrize("expected", ["list_posts", "get_thread", "search"])
def test_mcp_exposes_the_three_tools(api_site, monkeypatch, expected):
    app, token = api_site

    async def calls(session):
        return [tool.name for tool in (await session.list_tools()).tools]

    assert expected in run_mcp(monkeypatch, app, token, calls)


def test_mcp_list_posts_returns_json(api_site, monkeypatch):
    app, token = api_site

    async def calls(session):
        result = await session.call_tool("list_posts", {"sort": "new"})
        return result.content[0].text

    text = run_mcp(monkeypatch, app, token, calls)
    assert "MCP visible post" in text


def test_mcp_without_a_token_says_so(api_site, monkeypatch):
    app, token = api_site

    async def calls(session):
        result = await session.call_tool("list_posts", {})
        return result.content[0].text

    assert "MAF_TOKEN" in run_mcp(monkeypatch, app, "", calls)
