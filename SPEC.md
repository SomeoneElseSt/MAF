# MAF — v1 spec

An anonymous forum for Minerva students, laid out like Hacker News but with **no votes**: every list is ordered newest first. Only people with an `@uni.minerva.edu` email can read or post. Verifying gives the device an anonymous **pass**. Nobody can link a pass back to an email, and that includes the people running the server.

Design plan (source of truth for decisions): [PLAN.md](PLAN.md)

## Who can see what

| Party | Can see | Can't see |
|---|---|---|
| Minerva (owns the mail domain) | That a student received a code email, which means they're a member | Anything else |
| AWS SES | Recipient address when the code is sent | Anything on the forum |
| MAF server / admins | Posts, passes, per-thread labels | Any email, or which email is behind which pass |
| Other users | Posts and per-thread labels | Anything that links posts across threads |

**Nothing derived from an email is ever written to disk**: no list, no hash, no salted or keyed hash.

## Stack

- Python 3.12, managed with **uv**
- Starlette (or FastAPI) + Jinja2 for server-rendered HTML, plus one CSS file. The only client-side JS is the blind-signature step at login.
- SQLite as a single file
- Name filter: **Presidio** with a spaCy model, running in-process on the same server. Start with `en_core_web_md`, benchmark it, and drop to `sm` if it's too slow.
- Blind signatures (RFC 9474): `blindrsa-ts` in the browser, vendored as a single file rather than loaded from a CDN, plus a Python RFC 9474 library on the server. Confirm the two interoperate before building on them.
- AWS: one EC2 `t4g.small`, Route 53 for the domain and DNS, SES for email
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
- **Search bar** at the top of every page. Uses SQLite's built-in FTS5 full-text index over post titles, post text and comments, so there's no extra dependency. Hidden items are excluded for non-admins. Search queries are never logged.
- **Sorter** next to the search bar, applied to the post list and to search results: `newest` (default), `oldest`, `most viewed`. Passed as a query param (`?sort=new|old|views`).
- **View counts:** each post has a `views` counter shown next to it. Opening a post adds 1, once per pass per 24 hours. The dedupe set `(pass_id, item_id)` lives **in memory only** and is cleared every 24 hours and on restart. Only the counter is written to disk, so no reading history is stored for any pass.
- **Pages:** `/` (post list with search bar and sorter, plus the no-naming rule), `/item/<id>`, `/submit`, `/how-it-works`, `/login`, `/admin-code`

## Name filter

- Run Presidio `PERSON` detection on titles, bodies and comments **before** saving.
- If it finds a name above the score threshold, reject the submission with: *"This looks like it names someone. MAF doesn't allow naming people. Please rephrase."* The threshold is configurable.
- `allowlist.txt` holds public figures and thinkers (Kant, etc.) who are allowed through.
- The rule appears in the login flow and on the home page.

## Moderation

| Action | Who | Effect |
|---|---|---|
| Flag | Any pass, once per item | 5 flags from distinct passes → hidden from everyone |
| Restore | Any 1 admin | Visible again; further flags can't re-hide it |
| Hide | 2 of 3 admins | Hidden from non-admins, kept in the database |

- **Setting:** `FLAGS_AUTO_HIDE` (default `true`). When set to `false`, flags only surface items to admins and never hide on their own. Switching is a setting change, not a migration.
- **Admin codes:** 3 codes in env (`ADMIN_CODES`). Entering one at `/admin-code` marks the current pass as an admin and stores which code was used.
- **Counting admin votes:** dedupe by *admin code*, not by pass, so one admin on two devices counts once.
- **Interface:** no dashboard. Admins see Restore/Hide buttons inline, and hidden items appear greyed out for them.
- **No bans.**

## Data model (sketch)

```
pass(id, is_admin, admin_code_id NULL)
redeemed_token(token_hash PK)
item(id, parent_id NULL, thread_id, pass_id, title NULL, url NULL, text NULL, created_at, views, flags, hidden_by_flags, restored, hidden_by_admin)
item_fts  -- FTS5 virtual table over item(title, text), kept in sync with triggers
flag(pass_id, item_id, PK both)
admin_hide_vote(admin_code_id, item_id, PK both)
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

1. Register a domain on Route 53 (no "Minerva" in the name).
2. SES: verify the domain (DKIM records), then request production access.
3. EC2 `t4g.small` with Caddy + a systemd service running the app.
4. Secrets in env: `LABEL_SECRET`, `ADMIN_CODES`, the RSA signing key, SES credentials.
