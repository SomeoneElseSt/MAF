# MAF — v1 spec

An anonymous forum for Minerva students, laid out like Hacker News but with **no votes**: every list is ordered newest first. Only people with an `@uni.minerva.edu` email can read or post. Verifying gives the device an anonymous **pass**. Nobody can link a pass back to an email, and that includes the people running the server.

Design plan (source of truth for decisions): [PLAN.md](PLAN.md)

## Who can see what

| Party | Can see | Can't see |
|---|---|---|
| Minerva (owns the mail domain) | That a student received a code email, which means they're a member | Anything else |
| AWS SES | Recipient address when the code is sent | Anything on the forum |
| MAF server / maintainer | Posts, passes, per-thread labels | Any email, or which email is behind which pass |
| Other users | Posts and per-thread labels | Anything that links posts across threads |

**Nothing derived from an email is ever written to disk**: no list, no hash, no salted or keyed hash.

## Stack

- Python 3.12, managed with **uv**
- Starlette (or FastAPI) + Jinja2 for server-rendered HTML, plus one CSS file (port `mockups/style.css`). Client-side JS is small vanilla files only: the blind-signature step at login, the theme toggle, the hashtag menu, inline reply boxes, the (i) info card, the ID pop-up and the submit placeholder. Every page must still work without JS, except login.
- SQLite as a single file
- Name filter: **Presidio** with a spaCy model, running in-process on the same server. Start with `en_core_web_md`, benchmark it, and drop to `sm` if it's too slow.
- Blind signatures (RFC 9474): `blindrsa-ts` in the browser, vendored as a single file rather than loaded from a CDN, plus a Python RFC 9474 library on the server. Confirm the two interoperate before building on them.
- Domain: `maforum.net` (Namecheap, free DNS). AWS: one EC2 `t4g.small`, SES for email, sending via the instance's IAM role
- Caddy for HTTPS, with **access logs off**
- While the app restarts (a release takes about 2 seconds), Caddy holds requests for up to 10 seconds instead of failing. If it's still down after that, Caddy shows a self-contained "under maintenance" page (`deploy/maintenance.html`, status 503) that reloads itself every 5 seconds.

## Login flow (sign-up and login are the same thing)

1. The user enters an `@uni.minerva.edu` email. The server rejects any other domain.
2. **Cooldown:** each email can request one code per 30 seconds. The cooldown lives in memory only. Its job is to keep anyone from flooding a classmate's inbox and to make collecting extra passes slow.
   **Guess limits:** after 5 wrong codes for one address, its Continue button waits 30 seconds ("Wait N seconds", counting down). Site-wide, at most 30 wrong codes are checked per hour; past that, the code page says "MAF is currently under maintenance. Try again in N minutes." and the maintainer gets one email (at most one per hour) saying sign-ins are paused. This stops anyone guessing across many addresses at once. Only plain addresses (`[a-z0-9._+-]+@uni.minerva.edu`) are accepted, so nothing like `Name <x@gmail.com>, y@uni.minerva.edu` reaches SES.
3. The server sends a 6-digit code (Azure Communication Services; SES as fallback) in the background, so the code page shows straight away. The page carries a random one-time token and asks `POST /sign-in/sent` (waiting up to 10 s) whether the email went out; if the provider refused it, a banner reads "We couldn't send your code. Try again?" and the 30-second wait is lifted so Try again resends at once. The token, not the address, identifies the send, so nobody can probe whether an address just asked for a code. The email is short: subject `Your MAF code: 482913`, an HTML version in the site's style (MAF wordmark top left, always light) plus a plain-text fallback. Templates: `maf/templates/email/`. Codes expire after 10 minutes and are held in memory only.
4. The user enters the code. If it matches, the browser generates a random token, blinds it, and sends only the blinded value. The server signs it and forgets the email.
5. The browser unblinds the token and redeems it at `/sign-in/redeem`. The server verifies the signature, stores `sha256(token)` to block reuse, creates a `pass`, and sets a long-lived HttpOnly session cookie.
6. Switching devices means doing this again. There are no cross-device accounts, no recovery key and no cap on passes.

**Rules:** don't store `created_at` on passes, and never log emails or IPs.

## Per-thread labels

- `label = wordlist(HMAC(LABEL_SECRET, pass_id || thread_id))` gives a name like `quiet-otter` from about 256 adjectives × 256 animals.
- The thread's author is tagged **OP** in that thread.
- Clicking a label opens a pop-up: *"Names are unique per thread to maintain anonymity."*
- The User Guide (`/guide`) explains this.

## Content

- **Post:** a title, plus an optional URL and/or text (a title alone is a post). Text and links only; no uploads or images.
- **Comments:** nested.
- **No votes.** Comments within a thread are ordered by `created_at`.
- **Search bar** at the top of every page. Uses SQLite's built-in FTS5 full-text index over post titles, post text and comments, so there's no extra dependency. Hidden items are excluded. Search queries are never logged.
- **Sorter** next to the search bar, applied to the post list and to search results: `newest` (default), `oldest`, `most viewed`. Passed as a query param (`?sort=new|old|views`).
- **View counts:** each post has a `views` counter shown next to it. Opening a post adds 1, once per pass per 24 hours. The dedupe set `(pass_id, item_id)` lives **in memory only** and is cleared every 24 hours and on restart. Only the counter is written to disk, so no reading history is stored for any pass.
- **Four-day pages:** `/` shows posts from the 4 days ending today, grouped under day headings (Today, Yesterday, then e.g. Thursday 19 November). `?before=YYYY-MM-DD` shows the 4 days ending the day before that date, with ‹ / › arrows beside the date range at the top (no bottom pager). `sort` applies within those 4 days. Switching sort resets the page: `new` and `views` open the latest 4 days, `old` opens the earliest 4 days that have posts (`?after=YYYY-MM-DD` for later pages in that mode), so the range label always matches the posts shown. Search results span all time, 30 per page.
- **List rows show no IDs:** title, link host, then plain-language metadata ("2 hours ago, 14 comments, 61 views"), then ` · #tag1, #tag2` if the post has tags.
- **Pinned:** posts with `pinned = 1` render in a "Pinned" group above Today, only when `sort=new` and on the latest page (no `before`). They aren't repeated in their day group there. Under `old` and `views` they appear in their normal day. Set with `maf pin` / `maf unpin`.
- **Personal pins (client-side only):** each list row gets a pin button at its right, shown on hover or focus and always on touch screens (`@media (hover: none)`), `aria-pressed` with label "Pin to top" / "Unpin". Clicking saves the post to `localStorage["maf.pins"]` as `{id, title, host, tags}` (newest first) and moves the row into Pinned after the maintainer's pins; unpinning moves it back to its day. Pinned posts not on the current page render from the stored snapshot, linking to `/thread/<id>`. Changes are announced in an `aria-live` region. Nothing about pins is sent to the server. Wrap storage access in try/catch; with storage unavailable the button does nothing and the page still works. See `mockups/pins.js`.
- **Live updates (thread page):** each signed-in thread page opens `GET /thread/<id>/events` (Server-Sent Events, `maf/live.py`). A new reply or reaction pings everyone watching that thread; the ping carries no content. The page then fetches the thread as its own viewer and compares: new replies it can see, and reaction counts that went up on items it already shows. If any, a banner (`.notice.live-replies`, sticky) says "1 new reply. Show?" / "2 new reactions. Show?" / "1 new reply and 2 new reactions. Show?" with Show underlined; Show reloads the page (drafts are kept), labels each new reply "New" in its details line until the next reload, rings each reaction chip that went up (fading over 2.5 s), and scrolls smoothly to the first of them (no animation under reduced motion). Watchers live in memory in the one app process; nothing about who watches is stored or logged.
- **Live front page:** `/` opens `GET /events`; a new post pings everyone there, and each page re-fetches its own URL and counts posts it doesn't show yet. The banner reads "1 new post. Show?"; Show reloads and scrolls to the first new post. On the plain front page (no tag/before/after), posts created after `localStorage["maf.seen"]` (the newest post time this browser has shown there) get a "New" label in their details line, whether you came back via Show or opened the page later; the label is gone on the next visit. Rows carry `data-created` for this. Nothing about visits is sent to the server.
- **Text boxes grow** with their content (`maf/static/grow.js`), never below their min-height.
- **Drafts (client-side only, `maf/static/drafts.js`):** unfinished posts and comment/reply boxes are saved to `localStorage["maf.drafts"]` as you type, keyed `submit` or `comment:<parent_id>`, and restored into empty fields on load (a restored inline reply box opens). A draft is cleared when its form lands on a `/thread/` page with no `notice` within 60 seconds of submitting; drafts older than 7 days are dropped. Nothing is sent to the server. Storage access is wrapped in try/catch.
- **Header:** brand, Submit, the search box (with the # button) and the Dark/Light text toggle to its right. **Footer on every page:** About, User Guide, Source Code, pinned to the bottom of short pages.
- **Empty state:** when there are no posts at all, `/` keeps the sort row and shows "No posts yet." near the top.
- **Pages:** `/` (four days of posts with search bar and sorter), `/thread/<id>`, `/submit`, `/about`, `/guide` (User Guide), `/guide/use-this-data` (Use this data), `/sign-in`

## Hashtags

- **Input:** the submit form's Hashtags field, "Up to 3, separated by commas." Normalise each tag: strip a leading `#`, lowercase, keep `[a-z0-9-]`, 1–24 characters, dedupe. More than 3 re-renders the form with an error on that field. Tags are free-form; there's no fixed list. Clicking into the field drops down suggested tags (the house tags and #minerva); picking one adds it. The list skips tags already in the box, narrows as you type, and hides once there are 3.
- **Storage:** `item_tag(item_id, tag)`, posts only (comments have no tags).
- **Display:** after the metadata, separated by a centered dot: `· #rotations, #berlin`. Each tag links to `/?tag=<tag>`.
- **Filter:** `/?tag=<tag>` lists posts with that tag across all time, 30 per page, with `sort` applied (like search). The search box shows `#<tag>`. Typing `#tag` into search does the same.
- **# menu:** a button inside the search box opens a scrollable list of every tag on visible posts with its post count, most used first, then alphabetical. Up/down chevrons with fades show when there's more to scroll. Without JS the button links to `/tags`, a plain list of the same.
- **Submit placeholder** for Text: no tags → an example post ("Every rotation I spend the first few weeks feeling lost…"). Any tags → the default dash outline. `#hottakes` among them → the hot-take outline. Wording is in `mockups/submit.html`.
- **House tags:** tags with their own rules live in one config dict, so new ones need no code changes:
  `HOUSE_TAGS = {"<tag>": {"submit_template": [...], "reply_placeholder": "...", "etiquette": "..." | None, "highlight": bool}}`.
  v1 has four, worded exactly as in PLAN.md's "Tags with templates" table: `hottakes` (highlight, etiquette), `help`, `wondering`, `confession` (etiquette, and the submit template ends with "Leave out details that could identify you or anyone else."). Topic tags such as `minerva` are plain tags with no entry.
  - The submit Text placeholder uses the first house tag in the Hashtags field, else the default outline if any tag is present, else the example post.
  - On the thread page, the post's first house tag picks the etiquette banner (`.notice.etiquette`) and the inline "Write a reply" placeholder (`Write a reply. Ideally:` then dash lines), with a taller box. The top "Write a comment" box stays plain.
  - `highlight: true` (only `hottakes`) gives list rows class `hot`: a faint ember wash (`--hot-wash`) and the tag in `--hot`.

## Private replies

- **UI:** under every comment and reply box, the help line reads `Commenting as: <id> · [ ] Make only visible to <recipient> (i)`. For the top-level box the recipient is the OP, labelled `(OP)`; for a reply it's the parent comment's author. The (i) opens a card: only you and that person can see it, it belongs to the device you posted from, other students can't see or flag it, and it's stored on the server like any comment.
- **Storage:** `item.private_to` holds the recipient's `pass_id` (NULL for public). The author is `item.pass_id`. The reply is stored only encrypted, in `item.sealed`; `item.text` stays NULL.
- **Encryption (in the browser, `maf/static/private.js`):** each pass has a separate ECDH P-256 key pair per thread, kept in that browser's IndexedDB with a non-extractable private key. The public half is stored in `thread_key(pass_id, thread_id, public_key)`. Per-thread keys mean a key never links someone's threads. A reply is encrypted with AES-GCM under a key both people derive (ECDH between their two thread keys, then HKDF-SHA256 with the thread id as salt; the thread id is also the AES-GCM associated data). `sealed` is JSON `{v: 1, iv, ct, from, to}` with base64url values; `from`/`to` are the two public keys, so either side can decrypt.
- **Key registration:** the thread page asks for a key only from people who've already written in that thread (`POST /thread-key`, refused otherwise), so the server never learns which threads someone reads. A first-time private sender's key is saved from the `from` field of their reply.
- **Server checks** (`maf/sealed.py`): the sealed JSON has exactly those fields, a 12-byte IV and valid public keys; `to` must equal the recipient's registered key and `from` the sender's (if registered). Otherwise nothing is saved. Any plain `text` sent with a private reply is dropped. No JavaScript means no private replies: the toggle stays hidden.
- **Limit:** the server also serves `private.js`, so a compromised server could ship code that copies replies before encrypting. Encryption protects the stored database and backups. The User Guide says this.
- **Visibility:** a private item is rendered only for its author's pass and the `private_to` pass, with ` · Private, only you and <other id> (i)` in its metadata. For everyone else it and its descendants are absent. Replies to a private item are forced private to the other party; the checkbox shows ticked and disabled.
- **Excluded from:** search/FTS, `comment_count`, the API and MCP, the tag menu counts, and the name filter (the server can't read them). Private items have no Flag button.
- **Can't reply privately to yourself:** the checkbox is hidden when the recipient is your own pass (e.g. the OP replying to the post).

## Reactions

- **Set:** a fixed list of 24 emoji (see `PICKER_EMOJI` in `mockups/reactions.js`): 👍 👎 ❤️ 😂 😮 😢 😡 🔥 🎉 🤔 👀 🙏 💯 🙌 😅 🫠 💀 🤝 👏 🫶 😬 🙃 ✅ ❤️‍🔥. The server rejects anything else.
- **Storage:** `reaction(pass_id, item_id, emoji, PK all)`, used to dedupe and to show which ones are yours. Counts are computed with `GROUP BY`. No timestamps.
- **UI (thread page only):** post reactions in a row under the post body; comment reactions in the `.actions` line after Reply and Flag. Each is a `button.react` with `aria-pressed` for yours; `.react-add` opens the picker (`role="dialog"`, Escape and outside click close it and return focus). Without JS, each reaction is a small form that POSTs `/react` with `item_id` and `emoji`, and the picker is a `<details>` list.
- **Rules:** any pass, once per emoji per item, toggled. Private items: only the two parties can react or see reactions. Hidden posts keep their reactions. Not shown in lists, not used for sorting, included in the API item response as `{emoji: count}`.
- **Rate limit:** 60 reaction toggles per minute per pass, in memory.

## Name filter

- Run Presidio `PERSON` detection on titles, bodies and comments **before** saving.
- If it finds a name above the score threshold (configurable), don't save. Re-render the form with the text intact and the warning: *"This looks like it names someone. MAF doesn't allow naming students or staff."* plus two buttons: **Edit post** (back to editing) and **Post anyway** (resubmits with `confirm_names=1`, which skips the check).
- No stored list of names. A short list of words the model mistakes for names but never are on MAF (`NOT_PEOPLE` in `maf/namefilter.py`: "Minerva") is skipped.
- The rule appears on `/submit` and `/guide`.

## Moderation

No admin roles, codes or buttons. Moderation is community flags plus the maintainer using the `maf` CLI over SSH.

- **Flag:** any pass, once per item. Clicking again unflags (the button shows a blood-red "Flagged" with the note "5 flags hide a post. Urgent? Email hello@maforum.net."). Unflagging below 5 unhides the item. At 5 flags from distinct passes the item is `hidden`: excluded from `/`, from search and from comment trees, unless `restored = 1`.
- **Flagged comments:** at 5 flags a comment's name, text and actions are replaced, for everyone, by "Original reply is in review after 5 flags." in the meta style; its replies stay. The first time a comment is hidden, the maintainer gets one email (same layout as the request emails): subject `MAF review requested for reply <id>`, a link to it in its thread, "Hidden after 5 flags as of DD/MM/YY HH:MM UTC", and "Read it on the server with maf show <id>, then maf unhide or maf nuke." Flagging back and forth doesn't send more (tracked in memory). The Flagged note under a comment says "5 flags hide a comment."
- **Hidden items stay reachable** at `/thread/<id>`, faded, with a banner, "Five people flagged this post, so it's been unlisted. You can still read it here and ask for it to come back or be removed permanently.", and two buttons: **Request unhide** and **Request deletion**.
- **Requests:** once per pass per item per kind. Stored as `moderation_request(pass_id, item_id, kind)` for deduplication only. On each new request, immediately send an SES email to `MAINTAINER_EMAIL`, for example `Unhide requested for post #123 (4 requests so far) <link>`. No pass or identity goes in the email.
- **`maf` CLI** (maintainer, run on the server over SSH: `ssh maf-server maf <command>`). It's a console script in the same uv project (`[project.scripts] maf = "maf.cli:main"`), built with stdlib `argparse` and `sqlite3` on the same database file, with no extra dependencies. It reuses the app's own data functions so the logic isn't written twice.

  | Command | Effect |
  |---|---|
  | `maf requests` | Table of items with open `moderation_request` rows: id, title or first 60 chars, kind, count |
  | `maf hidden` | Table of items with `hidden = 1` |
  | `maf show <id>` | Prints the item's title, URL or text, flags, hidden/restored state and request counts |
  | `maf unhide <id>` | Sets `hidden = 0, restored = 1` and clears its requests. Once `restored = 1`, flags never hide it again |
  | `maf nuke <id>` | Prints the item, asks `Delete post #<id> and its N comments? [y/N]`, then deletes the item (and, for a post, its whole thread) along with its flags and requests. FTS rows go via triggers. `/thread/<id>` then returns 404 |
  | `maf remove <id> [--reason TEXT] [--yes]` | Comments only. Deletes the comment's text (and any sealed copy) for good, removes it from search, drops its reactions and requests, and stores the reason (default "Removed because it named someone."), which shows in its place in the meta style. Replies stay. Uses `secure_delete` and a WAL checkpoint so the words don't linger in the database file; older backups still have them. Never prints the comment |
  | `maf dismiss <id>` | Clears its requests without changing anything |
  | `maf pin <id>` | Sets `pinned = 1` on a post (not a comment). Pinned posts show above Today under Newest |
  | `maf unpin <id>` | Sets `pinned = 0` |

  An unknown id prints `No item #<id>` and exits non-zero.
- **No bans.**

## Developer access (read-only API + MCP)

- **Tokens:** on `/guide/use-this-data`, a signed-in pass can create a read token: 32 random bytes, base64url, shown once. A pass can hold at most 5; at 5 the create button is greyed out. Store `api_token(token_hash PK, pass_id)` with `sha256(token)`. The page lists the pass's tokens by their last 4 characters, each with a Revoke button. No creation time is stored.
- **Auth:** `Authorization: Bearer <token>`. Tokens are read-only and can't post, comment, flag or request.
- **Rate limit:** 60 requests per minute per token, kept in memory. Over the limit returns `429` with `Retry-After`.
- **Endpoints** (JSON; hidden items excluded, same as the site):

  | Endpoint | Returns |
  |---|---|
  | `GET /api/v1/posts?before=YYYY-MM-DD&sort=new\|old\|views&tag=...` | Four days of posts (or, with `tag`, that tag's posts 30 per page): `id, title, url, text_preview, created_at, comment_count, views, tags, pinned` |
  | `GET /api/v1/tags` | Every tag with its post count |
  | `GET /api/v1/threads/<id>` | A post with its comment tree; each item carries its per-thread `author_id` and an `op` flag |
  | `GET /api/v1/search?q=...&page=N` | Matching posts and comments, 30 per page |

- **MCP server:** a small stdio server in the same repo (`maf/mcp.py`, console script `maf-mcp`) with three tools, `list_posts(before?, sort?)`, `get_thread(id)` and `search(query, page?)`, which wrap the API. It's configured with `MAF_TOKEN` and `MAF_URL`. Use the official MCP Python SDK; it's the only extra dependency and runs on the user's machine, not the server. The file declares its dependency inline (PEP 723), so `uv run <raw GitHub URL of maf/mcp.py>` runs it without cloning.
- **`/guide/use-this-data` page:** how to create a token, then `curl` examples for each endpoint, a script example, and an MCP config snippet, in that order. Code blocks wrap and have a Copy button.

## Data model (sketch)

```
pass(id)
redeemed_token(token_hash PK)
item(id, parent_id NULL, thread_id, pass_id, title NULL, url NULL, text NULL, created_at, views, flags, hidden, restored, pinned, private_to NULL, sealed NULL)  -- id: three words, adjective-thing-thing (e.g. quiet-river-lantern), picked at random and re-picked until unused
thread_key(pass_id, thread_id, public_key, PK(pass_id, thread_id))  -- per-thread public keys for encrypted private replies
item_tag(item_id, tag, PK both)  -- index on tag
item_fts  -- FTS5 virtual table over item(title, text) for public items only, kept in sync with triggers
flag(pass_id, item_id, PK both)
reaction(pass_id, item_id, emoji, PK all)
moderation_request(pass_id, item_id, kind, PK all)  -- kind: unhide | nuke
api_token(token_hash PK, pass_id)
```

In memory only, never persisted: `pending_code(email → code, expires_at)`, `cooldown(email → expires_at)`, `viewed(pass_id, item_id)` (cleared every 24 h).

## Privacy checklist

- Caddy access logs off, Uvicorn access log off, and no IPs in the app
- No analytics and no third-party scripts or fonts
- SES event publishing / CloudWatch delivery logs **off**
- Posting rate limits keyed by pass, never by IP
- The User Guide states the guarantee precisely: anonymous passes, with known limits (timing, shared IPs, and that MAF's server delivers the page's code)

## Accessibility

Target: everything on the [A11Y Project checklist](https://www.a11yproject.com/checklist/) (WCAG 2.2 A and AA), in both light and dark themes. Check every page against it before launch.

- **Structure:** `lang="en"`, a unique `<title>` per page, one `h1`, no skipped heading levels, `header`/`nav`/`main`/`footer` landmarks, and a "Skip to content" link that appears on focus. Lists are `ol`/`ul`; tables have `th scope` and a `caption`.
- **Keyboard:** every control is a real `<a href>` or `<button>`, reachable in visual order, with a visible `:focus-visible` outline. No `autofocus` and no positive `tabindex`. The # menu, info card and ID pop-up open with Enter/Space, close with Escape, and return focus to the button that opened them. The # menu is navigable with arrow keys. The ID pop-up uses `<dialog>`.
- **State for screen readers:** `aria-expanded` on the # button, (i) buttons and Reply toggles; `aria-current` on the active sort; `aria-pressed` or an accessible label on the Dark/Light toggle; disabled arrows are `aria-disabled`. Private replies say "Private" in text, and #hottakes rows say "#hottakes" in text, so neither relies on colour.
- **Forms:** every field has a `<label for>`; help text and errors are linked with `aria-describedby`. Errors (including the name warning and "more than 3 hashtags") are listed above the form, each linking to its field. `autocomplete="email"` on login and `autocomplete="one-time-code"` with `inputmode="numeric"` on the code field. Placeholders are hints only, never the sole label.
- **Contrast:** body and meta text at least 4.5:1, including on `--tint` and `--hot-wash`; input borders, the checkbox and icons at least 3:1. Custom `::selection` colours must pass too.
- **Zoom and reflow:** never disable zoom; no horizontal scroll at 320 px wide or at 200% text size; any orientation works.
- **Targets:** tappable controls at least 24×24 px (the (i), arrows, Flag and Reply need padding to reach it).
- **Motion:** only small transitions, all off under `prefers-reduced-motion`.
- **Links:** links in text are underlined or otherwise distinct from plain text without colour, and the Source Code link says if it opens a new tab.
- **Session:** passes don't expire, so there's no timeout to extend. The 10-minute login code is the exception, and the code page says so, and "Go Back" returns to the email step to request another.

## Out of scope for v1

Votes, uploads/images, DMs outside threads, notifications, karma, profiles, editing, mobile app.

## Deploy

1. Domain `maforum.net` is registered (Namecheap). Add an A record pointing to the EC2 instance.
2. SES: domain verified with Easy DKIM (3 CNAMEs in Namecheap), DMARC TXT `_dmarc` = `v=DMARC1; p=none;`, production access requested.
3. EC2 `t4g.small` with Caddy + a systemd service running the app.
4. Secrets in env: `LABEL_SECRET`, the RSA signing key, SES credentials, `MAINTAINER_EMAIL`.
