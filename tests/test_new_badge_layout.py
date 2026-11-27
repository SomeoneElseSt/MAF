"""Browser layout regression; run with `uv run --with playwright pytest tests/test_new_badge_layout.py`.

Install a Playwright Chromium browser, or set CHROME_BIN to an existing executable.
"""

import os
from pathlib import Path

import pytest


CSS = Path(__file__).resolve().parents[1] / "maf/static/style.css"


def test_new_comments_badge_wraps_whole_but_stays_inline_when_it_fits():
    playwright = pytest.importorskip("playwright.sync_api")
    with playwright.sync_playwright() as p:
        browser = p.chromium.launch(
            executable_path=os.environ.get("CHROME_BIN"),
            args=["--disable-extensions"],
        )
        page = browser.new_page(viewport={"width": 390, "height": 844}, is_mobile=True)
        page.set_content("""<!doctype html><meta name="viewport" content="width=device-width, initial-scale=1">
            <ol class="list"><li><div class="meta" id="narrow"><span class="counts">12 comments · #synthetic</span><span class="new-tag">New comments</span></div></li>
            <li><div class="meta" id="wide"><span class="counts">12 comments · #synthetic</span><span class="new-tag">New comments</span></div></li>
            <li><div class="meta" id="tiny"><span class="counts">x</span><span class="new-tag">New comments</span></div></li></ol>""")
        page.add_style_tag(content=CSS.read_text())
        layout = page.evaluate("""() => {
            const narrow = document.querySelector('#narrow');
            const wide = document.querySelector('#wide');
            const badge = narrow.querySelector('.new-tag');
            const counts = narrow.querySelector('.counts');
            const firstWord = document.createRange();
            firstWord.setStart(badge.firstChild, 0); firstWord.setEnd(badge.firstChild, 3);
            // Enough room for 'New', but not for the complete badge.
            narrow.style.width = Math.ceil(counts.getBoundingClientRect().width + firstWord.getBoundingClientRect().width + 12) + 'px';
            wide.style.width = '340px';
            const tiny = document.querySelector('#tiny');
            tiny.style.width = '50px';
            function measure(row) {
                const label = row.querySelector('.new-tag');
                const text = document.createRange(); text.selectNodeContents(label);
                const prefix = row.querySelector('.counts').getBoundingClientRect();
                const fragments = [...text.getClientRects()].map(r => ({top:r.top, left:r.left}));
                return {fragments, prefixTop:prefix.top, prefixLeft:prefix.left,
                        parentRight:row.getBoundingClientRect().right, badgeRight:label.getBoundingClientRect().right};
            }
            return {narrow:measure(narrow), wide:measure(wide), tiny:measure(tiny)};
        }""")
        browser.close()

    narrow, wide = layout["narrow"], layout["wide"]
    assert len(narrow["fragments"]) == 1, f"badge split across lines: {narrow}"
    assert narrow["fragments"][0]["top"] > narrow["prefixTop"] + 10, narrow
    assert narrow["badgeRight"] <= narrow["parentRight"], narrow
    assert len(wide["fragments"]) == 1, wide
    assert abs(wide["fragments"][0]["top"] - wide["prefixTop"]) < 5, wide
    assert wide["fragments"][0]["left"] > wide["prefixLeft"], wide
    assert wide["badgeRight"] <= wide["parentRight"], wide
    # Even a container narrower than the badge must not split the words.
    assert len(layout["tiny"]["fragments"]) == 1, layout["tiny"]
