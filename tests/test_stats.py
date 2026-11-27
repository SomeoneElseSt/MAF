"""`maf stats`: site totals with a delta, and only rows that carry a time get one."""

from datetime import timedelta

from maf import cli, store
from maf.util import iso, utc_now


def make_post(app, pass_id, days_ago=0):
    return store.create_post(app.conn, pass_id, "A post", "text", None, [],
                             created_at=iso(utc_now() - timedelta(days=days_ago)))


def by_name(metrics):
    return {m.name: m for m in metrics}


def test_totals_count_posts_and_replies(app, pass_id):
    old = make_post(app, pass_id, days_ago=2)
    store.create_comment(app.conn, pass_id, old, "A reply", None,
                         created_at=iso(utc_now() - timedelta(days=2)))
    make_post(app, pass_id)
    metrics = by_name(store.site_stats(app.conn, iso(utc_now() - timedelta(hours=12))))
    assert metrics["posts"].total == 2 and metrics["replies"].total == 1
    assert metrics["posts"].recent == 1 and metrics["replies"].recent == 0


def test_rows_without_a_time_have_no_delta(app, pass_id):
    make_post(app, pass_id)
    metrics = by_name(store.site_stats(app.conn, iso(utc_now() - timedelta(hours=12))))
    assert metrics["passes"].recent is None
    assert metrics["passes"].total == 1


def test_private_replies_are_counted_apart(app, pass_id):
    post = make_post(app, pass_id)
    other = store.create_pass(app.conn)
    store.create_comment(app.conn, pass_id, post, "Public", None)
    store.create_comment(app.conn, pass_id, post, "Private", other)
    metrics = by_name(store.site_stats(app.conn, iso(utc_now() - timedelta(hours=12))))
    assert metrics["replies"].total == 1 and metrics["private replies"].total == 1


def test_the_command_prints_a_table_with_a_delta_column(app, pass_id, capsys):
    make_post(app, pass_id)
    assert cli.cmd_stats(app.conn, None) == 0
    out = capsys.readouterr().out
    assert "metric" in out and "last 12h" in out
    assert "posts" in out and "passes" in out
