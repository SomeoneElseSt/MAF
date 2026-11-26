"""API usage: daily totals per endpoint pattern. Nothing about who asked or which post."""

import json

from maf.usage import UsageLog, endpoint_of, usage


def test_requests_add_up_per_day_and_endpoint(tmp_path):
    path = tmp_path / "usage.json"
    log = UsageLog(path)
    log.record("GET /api/v1/posts")
    log.record("GET /api/v1/posts")
    log.record("GET /api/v1/threads/{id}")
    (day, counts), = json.loads(path.read_text()).items()
    assert len(day) == 10 and counts == {"GET /api/v1/posts": 2, "GET /api/v1/threads/{id}": 1}


def test_a_threads_id_is_never_recorded():
    assert endpoint_of("GET", "/api/v1/threads/quiet-river-lantern", {"id": "quiet-river-lantern"}) == "GET /api/v1/threads/{id}"


def test_the_api_counts_by_pattern(app, client, tmp_path):
    app.usage = UsageLog(tmp_path / "usage.json")
    client.get("/api/v1/threads/some-post-id")
    stored = (tmp_path / "usage.json").read_text()
    assert "some-post-id" not in stored and "GET /api/v1/threads/{id}" in stored


def test_without_a_path_nothing_is_written(tmp_path):
    UsageLog(None).record("GET /api/v1/posts")
    assert list(tmp_path.iterdir()) == []
    assert "MAF_USAGE_LOG" in usage(None)


def test_usage_prints_a_total_and_a_row_per_day_and_endpoint(tmp_path):
    path = tmp_path / "usage.json"
    path.write_text(json.dumps({"2026-11-26": {"GET /api/v1/posts": 41, "GET /api/v1/threads/{id}": 17}}))
    lines = usage(path).splitlines()
    assert lines[0].startswith("58 API requests")
    assert lines[1].split() == ["2026-11-26", "GET", "/api/v1/posts", "41"]
