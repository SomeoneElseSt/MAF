"""The name filter (Presidio) and its warning flow, and the MCP server.

The name-filter tests need the spaCy model; they are skipped without it.
"""


import pytest

from maf import store


@pytest.fixture(scope="module")
def presidio_ready():
    pytest.importorskip("presidio_analyzer")
    import spacy

    try:
        spacy.load("en_core_web_lg")
    except OSError:
        pytest.skip("spaCy model en_core_web_lg is not installed")


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
        spacy_model="en_core_web_lg",
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


def test_minerva_is_not_a_person(filtering_app):
    app, _ = filtering_app
    assert not app.name_filter.finds_name("Does Minerva publish stats on it?")
    assert not app.name_filter.finds_name("minerva is great")
    assert app.name_filter.finds_name("Has Minerva told Priya Raman yet?")


def test_chat_abbreviations_next_to_minerva_are_not_a_person(filtering_app):
    app, _ = filtering_app
    for text in ("Tbf Minerva is easier than most.", "tbf Minerva is easier than most.",
                 "Ngl Minerva is hard.", "Imo Minerva works."):
        assert not app.name_filter.finds_name(text), text
    # The abbreviation no longer hides a real name either ("Tbf Priya Raman" used to read as an organisation).
    assert app.name_filter.finds_name("Tbf Priya Raman said it first.")
    assert app.name_filter.finds_name("lol Jake Peralta is wild")


def test_chat_abbreviations_are_taken_out_as_whole_words_only():
    from maf.namefilter import without_chat_abbreviations

    assert without_chat_abbreviations("Tbf, Minerva is fine").split() == ["Minerva", "is", "fine"]
    assert without_chat_abbreviations("Fred lolled at the frame") == "Fred lolled at the frame"


def test_warning_keeps_the_text_and_offers_post_anyway(filtering_app):
    app, client = filtering_app
    sign_in(client, app)
    body = client.post("/submit", data={"nsfw": "No", "title": "What Ben Nelson got right", "text": "Reading the essays"}).text
    assert "This looks like it names someone" in body
    assert "Reading the essays" in body
    assert "Post anyway" in body and "Edit post" in body


def test_confirm_names_posts_anyway(filtering_app):
    app, client = filtering_app
    sign_in(client, app)
    response = client.post(
        "/submit",
        data={"nsfw": "No", "title": "What Ben Nelson got right", "text": "Reading", "confirm_names": "1"},
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
    store.create_api_token(app.conn, sha256_hex(token), pass_id, token[-4:])
    return app, token


def run_mcp(monkeypatch, app, token, calls):
    """Runs the real maf-mcp server in-process, talking to it over a memory pipe.

    The server is started exactly as `maf-mcp` starts it (mcp.run), but its
    HTTP calls go to the in-process app through a patched urlopen.
    """
    import asyncio

    from mcp import ClientSession
    from mcp.shared.memory import create_client_server_memory_streams

    import maf.mcp as mcp_module

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


def test_the_default_spacy_model_is_the_one_the_project_installs():
    from pathlib import Path

    from maf.settings import DEFAULT_SPACY_MODEL

    pyproject = (Path(__file__).parent.parent / "pyproject.toml").read_text()
    assert f'"{DEFAULT_SPACY_MODEL.replace("_", "-")}>=' in pyproject


def test_production_refuses_to_start_without_the_spacy_model(monkeypatch):
    import pytest

    from maf.settings import ConfigError, load_settings

    env = {"MAF_ENV": "production", "EMAIL_BACKEND": "ses", "LABEL_SECRET": "x" * 32, "SESSION_SECRET": "y" * 32,
           "SPACY_MODEL": "en_core_web_not_installed"}
    for name, value in env.items():
        monkeypatch.setenv(name, value)
    with pytest.raises(ConfigError, match="isn't installed"):
        load_settings()


def test_what_is_questions_about_things_are_not_people(filtering_app):
    app, _ = filtering_app
    assert not app.name_filter.finds_name("What is Zavarka? Sounds like canned beans")
    assert not app.name_filter.finds_name("What is Kombucha?")
    assert app.name_filter.finds_name("I saw Priya Raman at lunch.")


def test_nationalities_are_not_people(filtering_app):
    app, _ = filtering_app
    assert not app.name_filter.finds_name("Maybe you mean Kazakh's? Not sure if Eastern European")
    assert not app.name_filter.finds_name("Kazakhs are great")
    assert not app.name_filter.finds_name("Maybe you mean Kazakh? Not sure")


def test_a_name_next_to_a_nationality_is_still_caught(filtering_app):
    app, _ = filtering_app
    assert app.name_filter.finds_name("The Kazakh student Aigerim Bekova said so")
    assert app.name_filter.finds_name("Ask Priya Raman, she's Indian")


def test_nationality_words_match_plurals_and_possessives():
    from maf.demonyms import is_demonym
    assert is_demonym("kazakh") and is_demonym("kazakhs") and is_demonym("kazakh's")
    assert not is_demonym("finn") and not is_demonym("priya")


def test_formatting_cannot_hide_a_name(filtering_app):
    app, _ = filtering_app
    for text in ("I saw **Priya Raman** at lunch", "I saw *Priya Raman* at lunch",
                 "I saw ~~Priya Raman~~ at lunch", "I saw P**riya Ram**an", "[Priya Raman](https://x.com) said so"):
        assert app.name_filter.finds_name(text), text
    assert not app.name_filter.finds_name("**What is Zavarka?** Sounds like *canned beans*")


def test_comment_with_a_name_sent_in_place_comes_back_to_the_warning(filtering_app):
    app, client = filtering_app
    pass_id = sign_in(client, app)
    post = store.create_post(app.conn, pass_id, "Post", "body", None, [])
    response = client.post("/comment", data={"parent_id": post.id, "thread_id": post.id, "text": "Priya Raman told me"},
                           headers={"X-MAF-In-Place": "1"}, follow_redirects=False)
    location = response.json()["location"]
    assert response.status_code == 200 and "&names=comment-form&text=Priya+Raman+told+me" in location
    assert store.comment_count(app.conn, post.id) == 0


def test_a_refused_reply_offers_post_anyway_for_its_box(filtering_app):
    app, client = filtering_app
    pass_id = sign_in(client, app)
    post = store.create_post(app.conn, pass_id, "Post", "body", None, [])
    response = client.post("/comment", data={"parent_id": post.id, "thread_id": post.id, "text": "Priya Raman told me"},
                           follow_redirects=False)
    assert "&names=comment-form&text=Priya+Raman+told+me" in response.headers["location"]
    page = client.get(response.headers["location"]).text
    # The warning sits inside the box it belongs to, with the refused words and a Post anyway for it.
    box = page.split('id="comment-form"')[1].split("</form>")[0]
    assert "name-warning" in box and "Priya Raman told me" in box
    assert 'name="confirm_names" value="1"' in box
    client.post("/comment", data={"parent_id": post.id, "thread_id": post.id, "text": "Priya Raman told me",
                                  "confirm_names": "1"}, follow_redirects=False)
    assert store.comment_count(app.conn, post.id) == 1


def test_a_refused_edit_offers_post_anyway_too(filtering_app):
    app, client = filtering_app
    pass_id = sign_in(client, app)
    post = store.create_post(app.conn, pass_id, "Post", "body", None, [])
    reply = store.create_comment(app.conn, pass_id, post, "hello", None)
    response = client.post("/edit", data={"item_id": reply.id, "thread_id": post.id, "text": "Priya Raman told me"},
                           follow_redirects=False)
    assert f"&names=edit-{reply.id}&text=Priya+Raman+told+me" in response.headers["location"]
    page = client.get(response.headers["location"]).text
    box = page.split(f'id="edit-{reply.id}"')[1].split("</form>")[0]
    assert "name-warning" in box and "Priya Raman told me" in box
    client.post("/edit", data={"item_id": reply.id, "thread_id": post.id, "text": "Priya Raman told me", "confirm_names": "1"})
    assert store.get_item(app.conn, reply.id).edited_at


def test_post_anyway_only_points_at_a_reply_box(filtering_app):
    app, client = filtering_app
    pass_id = sign_in(client, app)
    post = store.create_post(app.conn, pass_id, "Post", "body", None, [])
    page = client.get(f'/thread/{post.id}?notice=x&names="><script>').text
    assert "Post anyway" not in page


def test_a_refused_post_edit_offers_post_anyway_too(filtering_app):
    app, client = filtering_app
    pass_id = sign_in(client, app)
    post = store.create_post(app.conn, pass_id, "Post", "body", None, [])
    response = client.post("/edit", data={"item_id": post.id, "thread_id": post.id, "text": "Priya Raman told me"},
                           follow_redirects=False)
    assert f"&names=edit-{post.id}&text=Priya+Raman+told+me" in response.headers["location"]
    page = client.get(response.headers["location"]).text
    box = page.split(f'id="edit-{post.id}"')[1].split("</form>")[0]
    assert "name-warning" in box and "Priya Raman told me" in box
    client.post("/edit", data={"item_id": post.id, "thread_id": post.id, "text": "Priya Raman told me", "confirm_names": "1"})
    assert store.get_item(app.conn, post.id).edited_at
