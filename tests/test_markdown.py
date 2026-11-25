"""Markdown in posts, replies and edits."""

from maf.markdown import render


def test_basic_formatting():
    html = render("**bold** *it* ~~gone~~ `code`")
    assert "<strong>bold</strong>" in html and "<em>it</em>" in html
    assert "<s>gone</s>" in html and "<code>code</code>" in html


def test_single_line_breaks_stay():
    assert render("one\ntwo") == "<p>one<br />\ntwo</p>\n"


def test_raw_html_is_shown_as_text():
    assert "<script>" not in render("<script>alert(1)</script>")
    assert "&lt;script&gt;" in render("<script>alert(1)</script>")


def test_no_headings_so_hashtags_and_hash_lines_stay_text():
    assert render("# not a heading #hottakes") == "<p># not a heading #hottakes</p>\n"


def test_no_images_and_no_script_links():
    assert "<img" not in render("![x](https://example.com/a.png)")
    assert "<a" not in render("[x](javascript:alert(1))")


def test_links_open_in_a_new_tab_without_referrer():
    html = render("see https://example.com")
    assert 'href="https://example.com"' in html
    assert 'target="_blank"' in html and 'rel="nofollow noopener noreferrer"' in html


def test_edit_label_goes_in_the_first_paragraph():
    assert render("fixed", "Edit #2:") == "<p>Edit #2: fixed</p>\n"
    assert render("- a", "Edit #1:").startswith("<p>Edit #1:</p><ul>")


def test_reply_markdown_shows_on_the_thread(signed_in, app):
    signed_in.post("/submit", data={"title": "Md", "text": "**strong post**", "tags": "help"})
    post = app.conn.execute("SELECT id FROM item WHERE title = 'Md'").fetchone()
    signed_in.post("/comment", data={"parent_id": post["id"], "thread_id": post["id"], "text": "> quoted"})
    page = signed_in.get(f"/thread/{post['id']}").text
    assert "<strong>strong post</strong>" in page
    assert "<blockquote>\n<p>quoted</p>\n</blockquote>" in page


def test_underline_uses_double_underscores_and_bold_stays_stars():
    assert render("__under__ **bold**") == "<p><u>under</u> <strong>bold</strong></p>\n"


def test_titles_get_only_bold_italics_underline_and_strikethrough():
    from maf.markdown import title
    assert title("**b** *i* __u__ ~~s~~") == "<strong>b</strong> <em>i</em> <u>u</u> <s>s</s>"
    assert title("`code` [x](https://e.com) <b>hi</b> # tag") == "`code` [x](https://e.com) &lt;b&gt;hi&lt;/b&gt; # tag"


def test_plain_drops_the_symbols():
    from maf.markdown import plain
    assert plain("**Big** news: __really__ ~~not~~") == "Big news: really not"
    assert plain("Tom & Jerry <3") == "Tom & Jerry <3"


def test_title_markdown_on_the_thread_and_plain_in_the_tab(signed_in, app):
    signed_in.post("/submit", data={"title": "A **bold** title", "tags": "help"})
    post = app.conn.execute("SELECT id FROM item WHERE title = 'A **bold** title'").fetchone()
    page = signed_in.get(f"/thread/{post['id']}").text
    assert "<h1>A <strong>bold</strong> title</h1>" in page
    assert "<title>A bold title · MAF</title>" in page
    assert "<strong>bold</strong>" in signed_in.get("/").text
