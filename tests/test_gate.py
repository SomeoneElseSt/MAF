"""Only students can read MAF: a signed-out visitor sees no forum content anywhere."""

import pytest
from starlette.routing import Mount, Route
from starlette.testclient import TestClient

from maf import store
from maf.main import PUBLIC_PATHS

SECRET_TITLE = "Secret students-only title"
SECRET_TEXT = "Secret students-only body"
SECRET_COMMENT = "Secret students-only comment"
SECRET_TAG = "secrettag"
SECRETS = (SECRET_TITLE, SECRET_TEXT, SECRET_COMMENT, SECRET_TAG)


@pytest.fixture
def seeded(app, pass_id):
    post = store.create_post(app.conn, pass_id, SECRET_TITLE, SECRET_TEXT, None, [SECRET_TAG])
    comment = store.create_comment(app.conn, store.create_pass(app.conn), post, SECRET_COMMENT, None)
    return {"post": post, "comment": comment}


@pytest.fixture
def stranger(starlette_app) -> TestClient:
    return TestClient(starlette_app)


def every_route(starlette_app, seeded) -> list[tuple[str, str]]:
    """(method, path) for every route the app serves, with real ids filled in."""
    found = []
    for route in starlette_app.routes:
        if isinstance(route, Mount):
            continue
        assert isinstance(route, Route)
        path = route.path.replace("{id}", seeded["post"].id)
        found.extend((method, path) for method in sorted(route.methods - {"HEAD"}))
    return found


def assert_no_secrets(text: str) -> None:
    for secret in SECRETS:
        assert secret not in text


def test_every_route_shows_a_stranger_nothing(starlette_app, stranger, seeded):
    routes = every_route(starlette_app, seeded)
    assert len(routes) > 20, "route discovery found too few routes"
    for method, path in routes:
        response = stranger.request(method, path, follow_redirects=False,
                                    data={"item_id": seeded["post"].id, "parent_id": seeded["post"].id})
        assert_no_secrets(response.text)
        if path.startswith("/api/"):
            assert response.status_code == 401, (method, path)
            continue
        if path in PUBLIC_PATHS:
            continue
        assert response.status_code == 303, (method, path)
        assert response.headers["location"] == "/login", (method, path)


def test_public_pages_leak_nothing_and_have_no_search(stranger, seeded):
    for path in ("/login", "/about", "/guide"):
        page = stranger.get(path)
        assert page.status_code == 200
        assert_no_secrets(page.text)
        assert 'id="tag-data"' not in page.text
        assert 'role="search"' not in page.text


def test_query_strings_and_unknown_paths_are_gated_too(stranger, seeded):
    for path in (f"/?q={SECRET_TITLE}", f"/?tag={SECRET_TAG}", "/search?q=Secret", "/no-such-page",
                 f"/item/{seeded['comment'].id}", "/static/../item/x"):
        response = stranger.get(path, follow_redirects=False)
        assert_no_secrets(response.text)
        assert response.status_code in (303, 404), path


def test_a_forged_cookie_is_treated_as_signed_out(stranger, seeded):
    from maf.sessions import COOKIE_NAME

    stranger.cookies.set(COOKIE_NAME, "not-a-real-signed-pass")
    response = stranger.get("/", follow_redirects=False)
    assert response.status_code == 303
    assert_no_secrets(response.text)


def test_flags_reactions_and_comments_from_strangers_change_nothing(app, stranger, seeded):
    post_id = seeded["post"].id
    stranger.post("/flag", data={"item_id": post_id})
    stranger.post("/react", data={"item_id": post_id, "emoji": "👍"})
    stranger.post("/comment", data={"parent_id": post_id, "text": "drive-by"})
    assert store.get_item(app.conn, post_id).flags == 0
    assert app.conn.execute("SELECT COUNT(*) FROM reaction").fetchone()[0] == 0
    assert app.conn.execute("SELECT COUNT(*) FROM item WHERE text = 'drive-by'").fetchone()[0] == 0


def test_signed_in_students_still_see_everything(signed_in, seeded):
    home = signed_in.get("/").text
    assert SECRET_TITLE in home
    assert SECRET_TAG in home
    thread = signed_in.get(f"/item/{seeded['post'].id}").text
    assert SECRET_COMMENT in thread


def test_sign_out_shows_only_when_signed_in_and_signs_you_out(starlette_app, signed_in):
    from maf.sessions import COOKIE_NAME

    assert "Sign Out" in signed_in.get("/").text
    assert "Sign Out" not in TestClient(starlette_app).get("/about").text
    response = signed_in.post("/logout", follow_redirects=False)
    assert response.status_code == 303
    cleared = response.headers["set-cookie"]
    assert cleared.startswith(f"{COOKIE_NAME}=") and ("Max-Age=0" in cleared or "expires=Thu, 01 Jan 1970" in cleared)
