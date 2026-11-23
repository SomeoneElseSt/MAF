"""Static files carry a content hash in their URL so browsers refetch them after an update."""

import hashlib
import re

from maf.web import STATIC_HASH_LENGTH, make_static_url


def file_hash(path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:STATIC_HASH_LENGTH]


def test_login_page_links_stylesheet_with_content_hash(client, settings):
    html = client.get("/login").text
    match = re.search(r'href="/static/style\.css\?v=([0-9a-f]+)"', html)
    assert match, "style.css must be linked with a ?v= query string"
    assert match.group(1) == file_hash(settings.static_dir / "style.css")


def test_every_static_url_in_a_page_is_versioned(client):
    html = client.get("/login").text
    urls = re.findall(r'(?:href|src)="(/static/[^"]*)"', html)
    assert urls
    assert all("?v=" in url for url in urls), urls


def test_versioned_url_still_serves_the_file(client, settings):
    response = client.get("/static/style.css?v=anything")
    assert response.status_code == 200
    assert response.content == (settings.static_dir / "style.css").read_bytes()


def test_hash_changes_with_file_content(tmp_path):
    (tmp_path / "a.css").write_text("body {}")
    before = make_static_url(tmp_path)("a.css")
    (tmp_path / "a.css").write_text("body { color: red }")
    after = make_static_url(tmp_path)("a.css")
    assert before != after


def test_unknown_static_file_gets_a_plain_url(tmp_path):
    assert make_static_url(tmp_path)("missing.js") == "/static/missing.js"
