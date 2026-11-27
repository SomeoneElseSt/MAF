"""Every MAF screen, photographed from made-up sample data, for the Screens tab of design/index.html.

    uv run --with playwright python design/screens.py              all screens (about 2 minutes)
    uv run --with playwright python design/screens.py thread dates only screens whose id contains a word given

First time on a machine: uv run --with playwright playwright install chromium

It makes its own database and server (port 8012) in a temporary folder, so it never touches the live site or
anyone's real words. Writes design/screens/<id>-<variant>.jpg and design/screens.js (both gitignored).

Adding a screen: add a Screen to SCREENS. Who sees it is a persona (me, ana, ben, cai, dee, or anon for signed
out); `path` may use the ids in Sample (e.g. "/thread/{lamp}"); `act` runs after the page loads (open a menu,
fill a form). Screens with stage="empty" are taken before any sample data exists.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
from dataclasses import dataclass, field
from datetime import timedelta
from pathlib import Path
from typing import Callable

from itsdangerous import URLSafeSerializer
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "design" / "screens"
MANIFEST = ROOT / "design" / "screens.js"
PORT = 8012
BASE = f"http://127.0.0.1:{PORT}"
SETTLE_MS = 500  # scripts that run after load (keys, sealed replies, New tags) finish within this
VARIANTS = {
    "desktop-light": {"viewport": {"width": 1280, "height": 900}, "color_scheme": "light"},
    "desktop-dark": {"viewport": {"width": 1280, "height": 900}, "color_scheme": "dark"},
    "phone-light": {"viewport": {"width": 390, "height": 844}, "color_scheme": "light", "is_mobile": True, "has_touch": True},
    "phone-dark": {"viewport": {"width": 390, "height": 844}, "color_scheme": "dark", "is_mobile": True, "has_touch": True},
}
PERSONAS = ("me", "ana", "ben", "cai", "dee", "anon")


@dataclass
class Screen:
    id: str
    group: str
    name: str
    who: str
    path: str
    shows: str  # what the screen is for and what to check, in a sentence or two
    act: Callable | None = None
    stage: str = "full"
    files: list[str] = field(default_factory=list)  # templates, scripts and styles behind it, for agents


# Sample data ------------------------------------------------------------------------------------------------

class Sample(dict):
    """Ids of seeded posts, by short name, for Screen paths."""


def seed_public(conn, people: dict[str, str]) -> Sample:
    """Posts, replies, reactions, flags and moderation states, written straight to the database."""
    from maf import cli, store
    from maf.util import iso, utc_now

    ids = Sample()
    now = utc_now()

    def at(hours: float) -> str:
        return iso(now - timedelta(hours=hours))

    def post(key, who, title, text, tags, hours, url=None, **kw):
        ids[key] = store.create_post(conn, people[who], title, text, url, tags, created_at=at(hours), **kw).id
        return store.get_item(conn, ids[key])

    def reply(who, parent, text, hours):
        return store.create_comment(conn, people[who], parent, text, None, created_at=at(hours))

    welcome = post("welcome", "maintainer", "Welcome to MAF: read this first",
                   "MAF is anonymous: nobody, the maintainer included, can see who wrote what.\n\n"
                   "- Be respectful, and don't name students or staff.\n- Five flags on a post hide it.", ["minerva"], 70)
    store.set_pinned(conn, welcome.id, True)

    study = post("study", "ana", "Best quiet places to study near the Berlin residence?",
                 "The residence gets loud after 9. I've tried:\n\n- the library on the corner (closes at 8)\n"
                 "- the café downstairs (no outlets)\n\nAnywhere open late with **wifi that works**?", ["help"], 3)
    r1 = reply("ben", study, "The university library two stops north is open until midnight on weekdays.", 2.5)
    r2 = reply("ana", r1, "Do they let visitors in without a student card?", 2.2)
    reply("ben", r2, "They did for me last rotation. Bring your passport.", 2.0)
    r3 = reply("cai", study, "> no outlets\n\nThe café on the next block has them under every window seat.", 1.8)
    store.edit_item(conn, r3.id, "> no outlets\n\nThe café on the next block has them under every window seat, and it's open until 11.")
    removed = reply("dee", study, "words that were removed", 1.5)
    store.remove_comment(conn, removed.id, cli.DEFAULT_REMOVE_REASON)
    gone = reply("me", study, "words the author deleted", 1.4)
    reply("ana", gone, "Thanks, trying it tonight.", 1.3)
    store.delete_own_comment(conn, gone.id)
    for who, emoji in (("ben", "👍"), ("cai", "👍"), ("dee", "🙏"), ("me", "👍")):
        store.toggle_reaction(conn, people[who], study.id, emoji)
    store.toggle_reaction(conn, people["ana"], r1.id, "❤️")

    hot = post("hot", "ben", "Hot take: the first-week city tour should be optional",
               "Half of us have lived abroad before. A reading list would do the same job in less time.", ["hottakes"], 5)
    h1 = reply("cai", hot, "Disagree. The tour is where I met most of my friends, not where I learned the city.", 4.5)
    reply("ben", h1, "Fair, though that sounds like a case for a social, not a tour.", 4.2)
    hidden_reply = reply("dee", hot, "words hidden by flags", 4.0)
    for flagger in range(store.FLAGS_TO_HIDE):
        store.add_flag(conn, store.create_pass(conn), hidden_reply.id)
    store.toggle_reaction(conn, people["me"], hot.id, "🔥")
    store.toggle_reaction(conn, people["ana"], hot.id, "🤔")

    lamp = post("lamp", "me", "Anyone selling a desk lamp before rotation?",
                "Moving rooms on Friday and the new one has no ceiling light.", ["help"], 6)
    ids["lamp_reply"] = reply("ana", lamp, "I have one I'm not taking with me. It's yours if you can pick it up.", 5).id
    reply("cai", lamp, f"Someone asked the same last week: {BASE}/thread/{study.id}", 4.8)
    store.toggle_reaction(conn, people["ana"], lamp.id, "👀")

    post("seoul", "cai", "A short guide to Seoul's subway passes", None, ["seoul"], 8,
         url="https://english.visitseoul.net/transportation")

    post("packing", "dee", "What do you wish you'd packed for Buenos Aires?",
         "Arriving in March. Is it still warm enough for summer clothes?", ["wondering"], 27)
    unpacked = post("unpacked", "ana", "Confession: I still haven't unpacked from Taipei",
                    "It's week six. The suitcase is a dresser now.", ["confession"], 30)
    reply("dee", unpacked, "Mine became a bedside table. You're not alone.", 29)

    bike = post("bike", "ben", "Selling my bike, cheap", "Leaving in two weeks.", ["help"], 33)
    for flagger in range(store.FLAGS_TO_HIDE):
        store.add_flag(conn, store.create_pass(conn), bike.id)
    mentioned = post("mentioned", "cai", "About last night's event", "A post the maintainer hid.", ["minerva"], 35)
    store.hide(conn, mentioned.id, cli.DEFAULT_HIDE_REASON)

    gym = post("gym", "ben", "Is the gym membership worth it in Hyderabad?", "Thinking of the one by the residence.",
               ["wondering"], 50)
    store.add_flag(conn, people["me"], gym.id)
    laundry = post("laundry", "me", "Where's the nearest laundromat?", "Asked and answered, so I hid it.", ["help"], 52)
    store.set_author_hidden(conn, laundry.id, True)

    nsfw = post("nsfw", "cai", "How do you handle dating when you move every semester?",
                "Asking for the NSFW side: apps, expectations, all of it.", ["confession"], 4, nsfw=True)
    reply("dee", nsfw, "Be upfront about leaving. It saves everyone time.", 3)

    how = post("how_dates", "maintainer", "How Dates works",
               "Make a profile with Submit on this page. To reply to someone's, you need one of your own.", [], 60,
               board="dates")
    store.set_pinned(conn, how.id, True)
    for item_id in (study.id, hot.id, lamp.id):
        conn.execute("UPDATE item SET views = ? WHERE id = ?", (40 + len(item_id), item_id))
    conn.commit()
    return ids


def seed_private(pages: dict, conn, ids: Sample) -> None:
    """What only works in a browser (encryption keys live there): private replies, profiles, matches, messages."""
    me, ana, ben, cai, dee = (pages[p] for p in ("me", "ana", "ben", "cai", "dee"))

    # A private reply from me to ana on my lamp post. Ana's browser publishes her key when she opens it.
    go(ana, f"/thread/{ids['lamp']}")
    go(me, f"/thread/{ids['lamp']}")
    reply_id = ids["lamp_reply"]
    me.click(f"[aria-controls='reply-{reply_id}']")
    me.check(f"#reply-{reply_id} input[name=private]")
    me.fill(f"#reply-{reply_id} textarea", "Great, can I come by Thursday evening?")
    me.click(f"#reply-{reply_id} button[type=submit]")
    me.wait_for_timeout(SETTLE_MS)

    ids["me_profile"] = make_profile(me, "Berlin", "Woman", "Men", "Coffee, long walks, and bad puns.")
    go(me, f"/dates/thread/{ids['me_profile']}")  # registers my key, as right after posting
    ids["ana_profile"] = make_profile(ana, "Buenos Aires", "Man", "Women")
    ids["ben_profile"] = make_profile(ben, "Tokyo", "Man", "Everyone", "New here, say hi.")
    ids["dee_profile"] = make_profile(dee, "San Francisco", "Non-binary", "Everyone")
    go(ben, f"/dates/thread/{ids['ben_profile']}")

    for sender in (ana, ben, dee):
        send_profile(sender, ids["me_profile"])
    send_profile(me, ids["ben_profile"])

    # I match ana and dee and write first; ana answers; dee unmatches.
    for who in ("ana", "dee"):
        reply_of = sent_reply(conn, ids["me_profile"], pages[who].pass_id)
        go(me, f"/dates/thread/{ids['me_profile']}")
        me.click(f"button.match[data-reply='reply-{reply_of}']")
        me.click("[data-match-yes]")
        me.fill(f"#reply-{reply_of} textarea", "Hi! Coffee this weekend?")
        me.click(f"#reply-{reply_of} button[type=submit]")
        me.wait_for_timeout(SETTLE_MS)
    ana_reply = sent_reply(conn, ids["me_profile"], ana.pass_id)
    message = conn.execute("SELECT id FROM item WHERE parent_id = ?", (ana_reply,)).fetchone()[0]
    go(ana, f"/dates/thread/{ids['me_profile']}")
    ana.click(f"[aria-controls='reply-{message}']")
    ana.fill(f"#reply-{message} textarea", "Saturday works. The place by the river?")
    ana.click(f"#reply-{message} button[type=submit]")
    ana.wait_for_timeout(SETTLE_MS)
    go(dee, f"/dates/thread/{ids['me_profile']}")
    dee.click("button.unmatch")
    dee.click("[data-unmatch-yes]")
    dee.wait_for_timeout(SETTLE_MS)


def make_profile(page, city, gender, interested_in, comment="") -> str:
    go(page, "/dates/submit")
    page.evaluate("""([city, gender, into, comment]) => {
        const set = (n, v) => { document.querySelector(`[name=${n}]`).value = v; };
        set("region", "Europe"); set("gender", gender); set("interested_in", into); set("height", "5′3″–5′9″ (160–175 cm)");
        set("city", city); set("looking_for", "Friend or relationship, depending on how it goes");
        document.querySelector("#comment").value = comment;
    }""", [city, gender, interested_in, comment])
    page.click("button[type=submit]")
    page.wait_for_load_state("load")
    if "/dates/thread/" not in page.url:
        sys.exit(f"A sample profile wasn't saved: {page.locator('main').inner_text()[:300]}")
    return page.url.split("?")[0].split("#")[0].rstrip("/").split("/")[-1]


def send_profile(page, profile_id) -> None:
    go(page, f"/dates/thread/{profile_id}")
    page.click("#reply-with-profile")
    page.click("[data-send-yes]")
    page.wait_for_timeout(SETTLE_MS)


def sent_reply(conn, profile_id, pass_id) -> str:
    return conn.execute("SELECT id FROM item WHERE parent_id = ? AND pass_id = ?", (profile_id, pass_id)).fetchone()[0]


def go(page, path) -> None:
    page.goto(path if path.startswith("file:") else BASE + path, wait_until="load")
    page.wait_for_timeout(SETTLE_MS)


# Acts: what to do on a page before it's photographed ----------------------------------------------------------

def click(selector):
    def act(page):
        page.click(selector)
        page.wait_for_timeout(250)
    return act


def fill_and_send(fields: dict, button="button[type=submit]"):
    def act(page):
        for selector, value in fields.items():
            page.fill(selector, value)
        page.click(button)
        page.wait_for_load_state("load")
        page.wait_for_timeout(SETTLE_MS)
    return act


def with_new_section(page):
    """New lists posts since this browser's last visit: pretend it was a day ago, with nothing opened since."""
    page.evaluate("""() => { localStorage.setItem("maf.new-since", new Date(Date.now() - 864e5).toISOString().slice(0, 19) + "Z");
                             localStorage.removeItem("maf.opened"); }""")
    page.reload(wait_until="load")
    page.wait_for_timeout(SETTLE_MS)


def nsfw_warning(page):
    page.evaluate("() => localStorage.removeItem('maf.nsfw-warned')")
    click(".nsfw-toggle")(page)


def hottakes_tag(page):
    page.fill("#tags", "hottakes")
    page.dispatch_event("#tags", "input")
    page.click("#title")
    page.wait_for_timeout(250)


SCREENS = [
    # Front page
    Screen("home", "Front page", "Front page", "me", "/",
           "Pinned, then New (posts since your last visit), then each day. #hottakes rows sit on the ember wash.",
           with_new_section, files=["list.html", "_rows.html", "new.js", "pins.js"]),
    Screen("home-empty", "Front page", "Front page, no posts", "me", "/",
           "Empty state: sort bar and dates stay; 'No posts yet.' centred in small grey sans.", stage="empty",
           files=["list.html"]),
    Screen("home-nsfw", "Front page", "NSFW side", "me", "/?side=nsfw&next=/",
           "The NSFW side: warm tint on every surface, the NSFW word in ember.", files=["list.html", "nsfw.js"]),
    Screen("nsfw-warning", "Front page", "NSFW warning", "me", "/",
           "First time NSFW is turned on in a browser, a centred pop-up asks first.", nsfw_warning, files=["base.html", "nsfw.js"]),
    Screen("tag", "Front page", "One hashtag", "me", "/?tag=help", "Posts with one hashtag.", files=["list.html"]),
    Screen("tags", "Front page", "All hashtags", "me", "/tags", "Every hashtag with its post count.", files=["tags.html"]),
    Screen("hashtag-menu", "Front page", "Hashtag menu", "me", "/",
           "The # in the search box opens a scrolling list as wide as the box.", click(".tag-toggle"), files=["tags.js"]),
    Screen("search", "Front page", "Search results", "me", "/search?q=study", "Matching posts first, then matching replies.",
           files=["list.html"]),
    Screen("search-none", "Front page", "Search, nothing found", "me", "/search?q=xylophone", "Empty search.",
           files=["list.html"]),
    Screen("bell", "Front page", "Feed menu", "me", "/",
           "Feed opens a list of replies and reactions to you; new ones say New. The count never changes the header's width.",
           click(".bell"), files=["base.html", "bell.js"]),
    Screen("feed", "Front page", "Feed page", "me", "/notifications", "The same list as a page (no JavaScript, or a phone).",
           files=["notifications.html"]),
    Screen("feed-empty", "Front page", "Feed, nothing yet", "me", "/notifications", "Empty Feed.", stage="empty",
           files=["notifications.html"]),

    # Threads
    Screen("thread", "Threads", "A thread", "me", "/thread/{study}",
           "Markdown, nested replies, an edited reply with a quote, a removed reply, a deleted one with an answer, reactions.",
           files=["item.html", "replies.js", "reactions.js", "markdown.js"]),
    Screen("thread-reply", "Threads", "Reply box open", "me", "/thread/{study}",
           "Reply opens a box under the reply, indented one step, with 'Replying as' under it.",
           click("li.comment .reply-toggle"), files=["item.html", "replies.js"]),
    Screen("emoji-picker", "Threads", "Emoji picker", "me", "/thread/{study}", "The smiley opens the 24 emoji.",
           click(".post-reactions .react-add"), files=["reactions.js"]),
    Screen("id-popup", "Threads", "ID pop-up", "me", "/thread/{study}",
           "Clicking a name explains that names are per thread and can't be followed.", click(".post-head .id"),
           files=["ids.js"]),
    Screen("thread-own", "Threads", "Your own post", "me", "/thread/{lamp}",
           "Edit and Hide Post on your own post; a private reply you sent ('Only visible to'); a reply that links a thread shows as a card.",
           files=["item.html", "private.js", "embed.py"]),
    Screen("thread-edit", "Threads", "Editing your post", "me", "/thread/{lamp}",
           "Edit swaps the text for a box in place.", click(".post-head [data-edit]"), files=["item.html", "replies.js"]),
    Screen("thread-private-to-you", "Threads", "A private reply to you", "ana", "/thread/{lamp}",
           "The person a private reply is for reads it; nobody else (the server included) can.", files=["private.js"]),
    Screen("thread-hottakes", "Threads", "#hottakes thread", "me", "/thread/{hot}",
           "The etiquette banner in the tag's ember; a reply in review after 5 flags.", files=["item.html", "housetags.py"]),
    Screen("thread-confession", "Threads", "#confession thread", "me", "/thread/{unpacked}",
           "A house tag's etiquette banner.", files=["housetags.py"]),
    Screen("thread-link", "Threads", "Link post", "me", "/thread/{seoul}", "A post with a link and no text.",
           files=["item.html"]),
    Screen("thread-flagged", "Threads", "You flagged it", "me", "/thread/{gym}",
           "Flagged in blood red, with how flags work and where to write when it's urgent.", files=["item.html"]),
    Screen("thread-hidden-flags", "Threads", "Hidden by 5 flags", "me", "/thread/{bike}",
           "Faded, with Request unhide and Request deletion.", files=["item.html"]),
    Screen("thread-hidden-maintainer", "Threads", "Hidden by the maintainer", "me", "/thread/{mentioned}",
           "The reason the maintainer gave, in place of the flags line.", files=["item.html", "cli.py"]),
    Screen("thread-hidden-author", "Threads", "Hidden by its author", "me", "/thread/{laundry}",
           "Only the author sees the note; the link still works for everyone. Unhide Post brings it back.",
           files=["item.html", "post.py"]),
    Screen("thread-nsfw", "Threads", "NSFW thread", "me", "/thread/{nsfw}", "An NSFW post keeps the tint on its own page.",
           files=["item.html"]),

    # Posting
    Screen("submit", "Posting", "Submit", "me", "/submit", "Title, link, hashtags, Is NSFW?, text with an example outline.",
           files=["submit.html", "submit.js", "_nsfw_field.html"]),
    Screen("submit-hottakes", "Posting", "Submit with #hottakes", "me", "/submit",
           "A house tag swaps the text box's outline for its own.", hottakes_tag, files=["submit.js", "housetags.py"]),
    Screen("submit-errors", "Posting", "Submit, missing answers", "me", "/submit",
           "Errors are one plain line each, under the field, in ink.", click("form button[type=submit]"),
           files=["submit.html"]),
    Screen("submit-names", "Posting", "Name warning", "me", "/submit",
           "When a post seems to name someone: the warning, with Edit and Post anyway.",
           fill_and_send({"#title": "Did anyone keep Maria Gonzalez's notes from Tuesday?", "#text": "Asking for the seminar."}),
           files=["submit-warning.html", "namefilter.py"]),

    # Dates
    Screen("dates", "Dates", "Dates", "me", "/dates", "The Dates page: rose tint, pinned How Dates works, profiles.",
           files=["list.html", "new.js"]),
    Screen("dates-empty", "Dates", "Dates, no profiles", "me", "/dates", "Empty Dates.", stage="empty", files=["list.html"]),
    Screen("dates-form", "Dates", "Make a profile", "cai", "/dates/submit", "The profile form: drop-downs and a comment.",
           files=["dates-submit.html", "_choice_field.html", "dates-form.js"]),
    Screen("dates-edit", "Dates", "Edit your profile", "me", "/dates/edit", "The same form, filled, with Delete.",
           files=["dates-submit.html"]),
    Screen("dates-delete", "Dates", "Delete profile pop-up", "me", "/dates/edit", "Deleting asks first.",
           click("[data-opens=delete-dialog]"), files=["dates-submit.html", "dates-thread.js"]),
    Screen("dates-own", "Dates", "Your profile and replies", "me", "/dates/thread/{me_profile}",
           "Profiles sent to you, a match with messages, a match that ended, Match on the others.",
           files=["item.html", "dates-thread.js", "private.js"]),
    Screen("dates-match", "Dates", "Match pop-up", "me", "/dates/thread/{me_profile}", "Match asks first.",
           click("button.match"), files=["item.html", "dates-thread.js"]),
    Screen("dates-other", "Dates", "Someone else's profile", "ana", "/dates/thread/{ben_profile}",
           "Reply with profile, and nothing of anyone else's replies.", files=["item.html"]),
    Screen("dates-send", "Dates", "Send your profile pop-up", "ana", "/dates/thread/{ben_profile}",
           "Sending your profile asks first.", click("#reply-with-profile"), files=["item.html", "dates-thread.js"]),
    Screen("dates-need-profile", "Dates", "No profile yet", "cai", "/dates/thread/{ben_profile}",
           "Without a profile, Reply with profile opens a notice under it.", click("#reply-with-profile"),
           files=["item.html", "dates-thread.js"]),
    Screen("dates-replied", "Dates", "Profile sent", "me", "/dates/thread/{ben_profile}",
           "After sending: a greyed Replied, and your sent profile with Delete.", files=["item.html"]),
    Screen("dates-matched", "Dates", "Matched, as the sender", "ana", "/dates/thread/{me_profile}",
           "Your sent profile and the messages after the match.", files=["item.html", "private.js"]),
    Screen("dates-ended", "Dates", "Match ended", "dee", "/dates/thread/{me_profile}",
           "After an unmatch: only a greyed Match ended.", files=["item.html"]),
    Screen("dates-pinned", "Dates", "How Dates works", "me", "/dates/thread/{how_dates}",
           "A pinned Dates post has normal comments.", files=["item.html"]),

    # Signing in and the rest
    Screen("sign-in", "Sign in and pages", "Sign in", "anon", "/sign-in", "Email first.", files=["login.html", "login.js"]),
    Screen("sign-in-error", "Sign in and pages", "Sign in, bad email", "anon", "/sign-in", "A wrong email.",
           fill_and_send({"input[name=email]": "not-an-email"}), files=["login.html"]),
    Screen("sign-in-code", "Sign in and pages", "Enter the code", "anon", "/sign-in/code", "The 6-digit code.",
           files=["login-code.html", "countdown.js"]),
    Screen("sign-in-code-error", "Sign in and pages", "Code, wrong", "anon", "/sign-in/code", "A code that doesn't match.",
           fill_and_send({"input[name=code]": "000000"}), files=["login-code.html"]),
    Screen("about", "Sign in and pages", "About", "anon", "/about", "About, signed out.", files=["about.html"]),
    Screen("privacy", "Sign in and pages", "Privacy", "anon", "/privacy", "What's stored and who can see it.",
           files=["privacy.html"]),
    Screen("guide", "Sign in and pages", "User Guide", "me", "/guide", "The five things to know.", files=["guide.html"]),
    Screen("guide-data", "Sign in and pages", "Use this data", "me", "/guide/use-this-data",
           "Tokens and code samples with Copy.", files=["guide-data.html", "copy.js"]),
    Screen("not-found", "Sign in and pages", "Not found", "me", "/thread/no-such-post", "A missing page.",
           files=["error.html"]),
    Screen("maintenance", "Sign in and pages", "Under maintenance", "anon", "file://" + str(ROOT / "deploy/maintenance.html"),
           "What Caddy shows while the app is down.", files=["deploy/maintenance.html"]),
]


# Running it ---------------------------------------------------------------------------------------------------

def start_server(db_path: Path) -> subprocess.Popen:
    env = {**os.environ, "MAF_DATABASE": str(db_path), "MAF_BASE_URL": BASE, "EMAIL_BACKEND": "console", "MAF_ENV": "development"}
    server = subprocess.Popen([sys.executable, "-m", "maf.main"], cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(100):
        try:
            urllib.request.urlopen(BASE + "/about", timeout=1)
            return server
        except OSError:
            time.sleep(0.2)
    server.kill()
    sys.exit(f"The server didn't start on port {PORT}. Is something else using it?")


def persona_context(p, folder: Path, cookie: str | None, variant: dict):
    context = p.chromium.launch_persistent_context(str(folder), headless=True, device_scale_factor=2, **variant)
    if cookie:
        context.add_cookies([{"name": "maf_pass", "value": cookie, "url": BASE}])
    return context


def shoot(page, screen: Screen, ids: Sample, variant_name: str, errors: dict) -> str:
    go(page, screen.path.format(**ids))
    if screen.act:
        screen.act(page)
    name = f"{screen.id}-{variant_name}.jpg"
    page.screenshot(path=str(OUT / name), full_page=True, type="jpeg", quality=72)
    if "side=nsfw" in screen.path:
        go(page, "/?side=main&next=/")
    return name


def run_stage(p, stage: str, screens: list[Screen], folders: dict, cookies: dict, ids: Sample, shots: dict, errors: dict):
    for variant_name, variant in VARIANTS.items():
        for who in PERSONAS:
            mine = [s for s in screens if s.who == who and s.stage == stage]
            if not mine:
                continue
            context = persona_context(p, folders[who], cookies.get(who), variant)
            page = context.new_page()
            current = {"id": ""}
            page.on("pageerror", lambda e: errors.setdefault(current["id"], set()).add(f"page error: {e}"[:200]))
            page.on("console", lambda m: m.type == "error" and errors.setdefault(current["id"], set()).add(m.text[:200]))
            for screen in mine:
                current["id"] = screen.id
                try:
                    shots.setdefault(screen.id, {})[variant_name] = shoot(page, screen, ids, variant_name, errors)
                except Exception as error:  # a broken screen is reported, and the rest still get taken
                    errors.setdefault(screen.id, set()).add(f"couldn't take it: {str(error).splitlines()[0][:160]}")
            context.close()
        print(f"  {stage}: {variant_name} done")


def main() -> None:
    from maf import db, store
    from maf.settings import load_settings

    wanted = sys.argv[1:]
    screens = [s for s in SCREENS if not wanted or any(w in s.id for w in wanted)]
    work = Path(tempfile.mkdtemp(prefix="maf-screens-"))
    OUT.mkdir(parents=True, exist_ok=True)
    if not wanted:
        for old in OUT.glob("*.jpg"):
            old.unlink()
    conn = db.connect(work / "screens.db")
    db.migrate(conn)
    signer = URLSafeSerializer(load_settings({}).session_secret, salt="maf-pass")
    people = {who: store.create_pass(conn) for who in (*PERSONAS[:-1], "maintainer")}
    cookies = {who: signer.dumps(pass_id) for who, pass_id in people.items()}
    folders = {who: work / who for who in PERSONAS}
    server = start_server(work / "screens.db")
    shots, errors, ids = {}, {}, Sample()
    started = time.time()
    try:
        with sync_playwright() as p:
            run_stage(p, "empty", screens, folders, cookies, ids, shots, errors)
            ids.update(seed_public(conn, people))
            contexts = {who: persona_context(p, folders[who], cookies[who], VARIANTS["desktop-light"]) for who in PERSONAS[:-1]}
            pages = {}
            for who, context in contexts.items():
                pages[who] = context.new_page()
                pages[who].pass_id = people[who]
            seed_private(pages, conn, ids)
            for context in contexts.values():
                context.close()
            run_stage(p, "full", screens, folders, cookies, ids, shots, errors)
    finally:
        server.terminate()
        conn.close()
        shutil.rmtree(work, ignore_errors=True)
    write_manifest(screens, shots, errors, wanted)
    print(f"{sum(len(v) for v in shots.values())} shots of {len(screens)} screens in {time.time() - started:.0f}s")
    for screen_id, problems in errors.items():
        for problem in sorted(problems):
            print(f"  {screen_id}: {problem}")


def write_manifest(screens: list[Screen], shots: dict, errors: dict, partial: list[str]) -> None:
    """design/screens.js: what the Screens tab shows. A partial run keeps the other screens' entries."""
    previous = {}
    if partial and MANIFEST.exists():
        previous = {s["id"]: s for s in json.loads(MANIFEST.read_text().split("=", 1)[1].rstrip().rstrip(";"))["screens"]}
    for screen in screens:
        previous[screen.id] = {
            "id": screen.id, "group": screen.group, "name": screen.name, "who": screen.who,
            "path": screen.path if screen.path.startswith("file:") else screen.path, "shows": screen.shows,
            "files": screen.files, "shots": shots.get(screen.id, {}), "errors": sorted(errors.get(screen.id, [])),
        }
    order = [s.id for s in SCREENS]
    data = {"taken": time.strftime("%Y-%m-%d %H:%M"), "variants": list(VARIANTS),
            "screens": sorted(previous.values(), key=lambda s: order.index(s["id"]) if s["id"] in order else len(order))}
    MANIFEST.write_text("// Written by design/screens.py. Don't edit by hand.\nwindow.MAF_SCREENS = " + json.dumps(data, ensure_ascii=False, indent=1) + ";\n")


if __name__ == "__main__":
    main()
