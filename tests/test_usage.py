"""The API usage log counts requests per endpoint and holds nothing about who made them."""

from maf.usage import UsageLog, read_usage, usage


def test_each_api_request_adds_a_line_with_only_time_and_endpoint(tmp_path):
    path = tmp_path / "usage.log"
    log = UsageLog(path)
    log.record("GET /api/v1/posts")
    log.record("GET /api/v1/posts")
    log.record("GET /api/v1/tags")
    lines = path.read_text().splitlines()
    assert len(lines) == 3
    stamp, _, endpoint = lines[0].partition(" ")
    assert stamp.endswith("Z") and endpoint == "GET /api/v1/posts"
    assert read_usage(path) == {"GET /api/v1/posts": 2, "GET /api/v1/tags": 1}


def test_without_a_path_nothing_is_written(tmp_path):
    UsageLog(None).record("GET /api/v1/posts")
    assert list(tmp_path.iterdir()) == []
    assert "MAF_USAGE_LOG" in usage(None)


def test_usage_prints_a_total_and_one_row_per_endpoint(tmp_path):
    path = tmp_path / "usage.log"
    path.write_text("2026-11-26T10:00:00Z GET /api/v1/posts\n2026-11-26T10:01:00Z GET /api/v1/search\n"
                    "2026-11-26T10:02:00Z GET /api/v1/posts\n")
    printed = usage(path)
    assert printed.splitlines()[0].startswith("3 API requests")
    assert "GET /api/v1/posts" in printed and " 2" in printed
