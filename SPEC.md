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
- Starlette (or FastAPI) + Jinja2 for server-rendered HTML, plus one CSS file. The only client-side JS is the blind-signature step at login.
- SQLite as a single file
- Name filter: **Presidio** with a spaCy model, running in-process on the same server. Start with `en_core_web_md`, benchmark it, and drop to `sm` if it's too slow.
- Blind signatures (RFC 9474): `blindrsa-ts` in the browser, vendored as a single file rather than loaded from a CDN, plus a Python RFC 9474 library on the server. Confirm the two interoperate before building on them.
- Domain: `maforum.net` (Namecheap, free DNS). AWS: one EC2 `t4g.small`, SES for email, sending via the instance's IAM role
- Caddy for HTTPS, with **access logs off**

## Login flow (sign-up and login are the same thing)

1. The user enters an `@uni.minerva.edu` email. The server rejects any other domain.
2. **Cooldown:** each email can request one code per 10 minutes. The cooldown lives in memory only, next to the code, and expires with it. Its job is to keep anyone from flooding a classmate's inbox and to make collecting extra passes slow.
3. The server sends a 6-digit code through SES. The email is neutral: subject `Your code: 482913`, no MAF branding in the body. Codes expire after 10 minutes and are held in memory only.
4. The user enters the code. If it matches, the browser generates a random token, blinds it, and sends only the blinded value. The server signs it and forgets the email.
5. The browser unblinds the token and redeems it at `/redeem`. The server verifies the signature, stores `sha256(token)` to block reuse, creates a `pass`, and sets a long-lived HttpOnly session cookie.
6. Switching devices means doing this again. There are no cross-device accounts, no recovery key and no cap on passes.

**Rules:** don't store `created_at` on passes, and never log emails or IPs.

## Per-thread labels

- `label = wordlist(HMAC(LABEL_SECRET, pass_id || thread_id))` gives a name like `quiet-otter` from about 256 adjectives × 256 animals.
- The thread's author is tagged **OP** in that thread.
- Clicking a label opens a pop-up: *"Names change per thread so no one can follow you around. There are no profiles, on purpose."*
- `/how-it-works` explains this.

## Content

- **Post:** title + (URL **or** text). Text and links only; no uploads or images.
- **Comments:** nested.
- **No votes.** Comments within a thread are ordered by `created_at`.
- **Search bar** at the top of every page. Uses SQLite's built-in FTS5 full-text index over post titles, post text and comments, so there's no extra dependency. Hidden items are excluded. Search queries are never logged.
- **Sorter** next to the search bar, applied to the post list and to search results: `newest` (default), `oldest`, `most viewed`. Passed as a query param (`?sort=new|old|views`).
- **View counts:** each post has a `views` counter shown next to it. Opening a post adds 1, once per pass per 24 hours. The dedupe set `(pass_id, item_id)` lives **in memory only** and is cleared every 24 hours and on restart. Only the counter is written to disk, so no reading history is stored for any pass.
- **Week pages:** `/` shows posts from the 7 days ending today, grouped under day headings (Today, Yesterday, then e.g. Thursday 19 November). `?week=YYYY-MM-DD` shows the 7 days ending on that date, with Previous week / Next week links. `sort` applies within the week. Search results span all time, 30 per page.
- **List rows show no IDs:** title, link host, then plain-language metadata ("2 hours ago, 14 comments, 61 views").
- **Pages:** `/` (week of posts with search bar and sorter, plus the no-naming rule), `/item/<id>`, `/submit`, `/how-it-works`, `/login`

## Name filter

- Run Presidio `PERSON` detection on titles, bodies and comments **before** saving.
- If it finds a name above the score threshold (configurable), don't save. Re-render the form with the text intact and the warning: *"This looks like it names someone. MAF doesn't allow naming students or staff. If it's a public figure, you can post anyway."* plus two buttons: **Edit post** (back to editing) and **Post anyway** (resubmits with `confirm_names=1`, which skips the check).
- No allowlist and no stored list of names.
- The rule appears in the login flow and on the home page.

## Moderation

No admin roles, codes or buttons. Moderation is community flags plus the maintainer using the `maf` CLI over SSH.

- **Flag:** any pass, once per item. At 5 flags from distinct passes the item is `hidden`: excluded from `/`, from search and from comment trees, unless `restored = 1`.
- **Hidden items stay reachable** at `/item/<id>`, with a banner, "Hidden after community flags.", and two buttons: **Request unhide** and **Request nuke ☢️**.
- **Requests:** once per pass per item per kind. Stored as `moderation_request(pass_id, item_id, kind)` for deduplication only. On each new request, immediately send an SES email to `MAINTAINER_EMAIL`, for example `Unhide requested for post #123 (4 requests so far) <link>`. No pass or identity goes in the email.
- **`maf` CLI** (maintainer, run on the server over SSH: `ssh maf-server maf <command>`). It's a console script in the same uv project (`[project.scripts] maf = "maf.cli:main"`), built with stdlib `argparse` and `sqlite3` on the same database file, with no extra dependencies. It reuses the app's own data functions so the logic isn't written twice.

  | Command | Effect |
  |---|---|
  | `maf requests` | Table of items with open `moderation_request` rows: id, title or first 60 chars, kind, count |
  | `maf hidden` | Table of items with `hidden = 1` |
  | `maf show <id>` | Prints the item's title, URL or text, flags, hidden/restored state and request counts |
  | `maf unhide <id>` | Sets `hidden = 0, restored = 1` and clears its requests. Once `restored = 1`, flags never hide it again |
  | `maf nuke <id>` | Prints the item, asks `Delete post #<id> and its N comments? [y/N]`, then deletes the item (and, for a post, its whole thread) along with its flags and requests. FTS rows go via triggers. `/item/<id>` then returns 404 |
  | `maf dismiss <id>` | Clears its requests without changing anything |

  An unknown id prints `No item #<id>` and exits non-zero.
- **No bans.**

## Data model (sketch)

```
pass(id)
redeemed_token(token_hash PK)
item(id, parent_id NULL, thread_id, pass_id, title NULL, url NULL, text NULL, created_at, views, flags, hidden, restored)
item_fts  -- FTS5 virtual table over item(title, text), kept in sync with triggers
flag(pass_id, item_id, PK both)
moderation_request(pass_id, item_id, kind, PK all)  -- kind: unhide | nuke
```

In memory only, never persisted: `pending_code(email → code, expires_at)`, `cooldown(email → expires_at)`, `viewed(pass_id, item_id)` (cleared every 24 h).

## Privacy checklist

- Caddy access logs off, Uvicorn access log off, and no IPs in the app
- No analytics and no third-party scripts or fonts
- SES event publishing / CloudWatch delivery logs **off**
- Posting rate limits keyed by pass, never by IP
- The "How it works" page states the guarantee precisely: anonymous passes, with known limits (timing, shared IPs, and that MAF's server delivers the page's code)

## Out of scope for v1

Votes, uploads/images, DMs, notifications, karma, profiles, editing, mobile app.

## Deploy

1. Domain `maforum.net` is registered (Namecheap). Add an A record pointing to the EC2 instance.
2. SES: domain verified with Easy DKIM (3 CNAMEs in Namecheap), DMARC TXT `_dmarc` = `v=DMARC1; p=none;`, production access requested.
3. EC2 `t4g.small` with Caddy + a systemd service running the app.
4. Secrets in env: `LABEL_SECRET`, the RSA signing key, SES credentials, `MAINTAINER_EMAIL`.
