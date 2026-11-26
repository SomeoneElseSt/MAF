"""Boards: /dating/ is its own front page, separate from the main one."""

import pytest

from maf import boards, cli, store


def post(app, pass_id, title, board=boards.MAIN, tags=()):
    return store.create_post(app.conn, pass_id, title, "text", None, list(tags), board=board)


def test_each_front_page_lists_only_its_own_board(viewer, app):
    main = post(app, viewer["pass_id"], "Main board post")
    dating = post(app, viewer["pass_id"], "Dating board post", board="dating")
    client = viewer["client"]
    front = client.get("/").text
    assert main.id in front and dating.id not in front
    page = client.get("/dating/").text
    assert dating.id in page and main.id not in page
    assert "on-board board-dating" in page and "on-board" not in front


def test_dating_without_slash_redirects(viewer):
    response = viewer["client"].get("/dating", follow_redirects=False)
    assert response.status_code in (301, 307, 308) and response.headers["location"].endswith("/dating/")


def test_tags_pinned_and_new_stay_on_their_board(viewer, app):
    other = store.create_pass(app.conn)
    dating = post(app, other, "Tagged dating", board="dating", tags=["help"])
    main = post(app, other, "Tagged main", tags=["help"])
    store.set_pinned(app.conn, dating.id, True)
    client = viewer["client"]
    assert dating.id not in client.get("/?tag=help").text
    assert dating.id in client.get("/dating/?tag=help").text
    assert dating.id not in client.get("/").text  # pinned on /dating/, not on the front page
    assert dating.id in client.get("/dating/").text
    assert store.tag_counts(app.conn) == [("help", 1)]
    since = "2000-01-01T00:00:00Z"
    assert [p.id for p in store.new_activity(app.conn, viewer["pass_id"], since)] == [main.id]
    assert dating.id in client.get(f"/new-activity?since={since}&board=dating").text


def test_submit_picks_the_board(viewer, app):
    client = viewer["client"]
    assert 'value="dating" checked' in client.get("/submit?board=dating").text
    assert 'value="main" checked' in client.get("/submit").text
    client.post("/submit", data={"title": "Coffee?", "board": "dating"}, follow_redirects=False)
    client.post("/submit", data={"title": "Library hours", "board": "nonsense"}, follow_redirects=False)
    made = {p.title: p.board for p in store.search(app.conn, "coffee") + store.search(app.conn, "library")}
    assert made == {"Coffee?": "dating", "Library hours": "main"}


def test_replies_follow_their_post_and_search_covers_every_board(viewer, app):
    dating = post(app, viewer["pass_id"], "Picnic plans", board="dating")
    reply = store.create_comment(app.conn, viewer["pass_id"], dating, "picnic sounds good", None)
    assert reply.board == "dating"
    page = viewer["client"].get("/search?q=picnic").text
    assert dating.id in page and 'class="board-badge board-dating"' in page
    thread = viewer["client"].get(f"/thread/{dating.id}").text
    assert 'class="board-badge board-dating" href="/dating/"' in thread


def test_set_board_moves_the_whole_thread(app, pass_id):
    first = post(app, pass_id, "Was on main")
    reply = store.create_comment(app.conn, pass_id, first, "a reply", None)
    assert store.set_board(app.conn, first.id, "dating")
    assert store.get_item(app.conn, first.id).board == "dating"
    assert store.get_item(app.conn, reply.id).board == "dating"
    assert not store.set_board(app.conn, reply.id, "main")  # only posts move, replies go with them
    with pytest.raises(ValueError):
        store.set_board(app.conn, first.id, "nowhere")


def test_cli_moves_posts_and_prints_only_ids(app, pass_id, capsys):
    first = post(app, pass_id, "Secret title one")
    second = post(app, pass_id, "Secret title two")
    args = cli.build_parser().parse_args(["board", "dating", first.id, second.id, "no-such-post"])
    assert cli.cmd_board(app.conn, args) == 1
    out = capsys.readouterr().out
    assert "Secret" not in out
    assert f"Moved {first.id} to /dating/." in out and "No post no-such-post" in out
    assert {store.get_item(app.conn, i).board for i in (first.id, second.id)} == {"dating"}


def test_existing_posts_start_on_main(app, pass_id):
    assert post(app, pass_id, "Old post").board == boards.MAIN
