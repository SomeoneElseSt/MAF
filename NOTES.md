# Build notes

Status of the v1 build against [SPEC.md](SPEC.md), on branch `build`.

## What's done

- **Blind-signature spike** (`spike/blind/`): `@cloudflare/blindrsa-ts` 0.4.6 (JS) and a
  Python `RSABSSA-SHA384-PSS-Randomized` implementation interoperate in both directions.
  No PyPI library implements RSABSSA, so the Python side is built on `cryptography` and
  checked against all four RFC 9474 Appendix A test vectors. See `spike/blind/README.md`.
- **Sign-in**: `@uni.minerva.edu` only; 6-digit code emailed through SES (console backend in
  dev); 10-minute code and cooldown, in memory only; blind signature; `/sign-in/redeem` verifies the
  token, stores `sha256(token)` and issues a pass with a long-lived HttpOnly cookie.
- **Threads**: posts (title + URL or text), nested comments, per-thread labels with OP tags,
  private replies, reactions (24 emoji, per-pass rate limit), flags that hide at 5,
  moderation requests that email the maintainer, view counts deduped per pass per day in memory.
- **Lists**: four-day pages with day headings, ‹ › arrows, `new`/`old`/`views` sorting,
  maintainer pins above Today, personal pins in the browser, hashtags with the # menu,
  `#tag` filtering, FTS5 search (queries never logged), the hidden- and private-item exclusions.
- **House tags**: `HOUSE_TAGS` config drives the submit and reply placeholders, the etiquette
  banner and the #hottakes highlight.
- **Name filter**: Presidio with `en_core_web_lg` (about 1 ms per submission; md made too many mistakes), with
  the Edit post / Post anyway warning.
- **Moderation**: the `maf` CLI (`requests`, `hidden`, `show`, `unhide`, `nuke`, `dismiss`,
  `pin`, `unpin`) over SSH.
- **Developer access**: read-only bearer-token API at `/api/v1` (60 requests per minute per
  token), token creation and revocation on `/guide/use-this-data`, and `maf-mcp` with `list_posts`,
  `get_thread` and `search`.
- **Templates**: plain Jinja pages in `maf/templates/` using the mockups' structure and class
  names, with `mockups/style.css` and the mockup JS in `maf/static/`.
- **Tests**: 106 pytest tests, covering each SPEC section including the privacy rules.

## What's not done

- **Visual polish**: the templates are plain and functional; restyling from the mockups is
  the maintainer's next step, as agreed.
- **Accessibility audit**: the structure follows the SPEC's rules (landmarks, skip link,
  labels, `aria-*` state, one `h1`, `<caption>`-ready tables), but no pass has been done
  against the full A11Y Project checklist in a browser yet.
- **Deployment**: `deploy/` has the setup and update scripts, the systemd unit, the Caddyfile and the AWS steps (`deploy/aws.md`). Not yet tried on a real server.
- **Email deliverability**: SES domain verification, DKIM and DMARC records are setup steps,
  not code.

## How to run it locally

```sh
uv sync --all-groups --extra mcp      # installs everything, including the spaCy model
uv run maf-mcp                       # (optional) the MCP server, needs MAF_TOKEN and MAF_URL

# run the app: development defaults need no configuration
EMAIL_BACKEND=console uv run python -m maf.main
```

Then open <http://127.0.0.1:8000>. With `EMAIL_BACKEND=console` the login code is printed to
the terminal instead of emailed. Locally you can also type `139145` ("minerv" as alphabet positions) as the code for any
@uni.minerva.edu address; it only works with the console backend, which production refuses to start with.

Environment variables (all optional in development):

| Variable | Meaning |
| --- | --- |
| `MAF_ENV` | `development` (default) or `production` |
| `MAF_DATABASE` | SQLite file path (default `maf.db`) |
| `LABEL_SECRET` | HMAC secret for per-thread labels |
| `SESSION_SECRET` | Secret that signs the pass cookie |
| `MAF_SIGNING_KEY` | Path to the RSA blind-signature key (required in production) |
| `EMAIL_BACKEND` | `ses` (default), `azure`, or `console` (dev only) |
| `MAF_EMAIL_FROM` | Sender address (with Azure, `DoNotReply@maforum.net` unless more senders are approved) |
| `AWS_REGION` | SES region |
| `AZURE_EMAIL_CONNECTION_STRING` | Azure Communication Services connection string, when `EMAIL_BACKEND=azure` |
| `MAINTAINER_EMAIL` | Where moderation requests go |
| `MAF_BASE_URL` | Public base URL, used in links and by `main` for host/port |
| `NAME_FILTER_THRESHOLD`, `NAME_FILTER_ENABLED`, `SPACY_MODEL` | Name filter tuning |

The RSA signing key is generated at `maf.db.key` on first local run; in production set
`MAF_SIGNING_KEY` to a file with mode 0600.

## How to run the tests

```sh
uv run pytest
```

The name-filter tests need the spaCy model, which `uv sync` installs. The MCP tests run the
real `maf-mcp` server in-process.

## Decisions made during build

- **The signed message is the randomized prepared message.** RSABSSA-SHA384-PSS-Randomized
  prepends 32 random bytes before signing. The browser redeems with `token`, `prepared` and
  `signature`; the server checks the signature over `prepared`, that `prepared` ends with
  `token`, and stores `sha256(token)`.
- **The pass is the session.** There is no separate session record: the cookie holds the
  pass id, signed with `SESSION_SECRET`.
- **Codes are consumed at blind-sign, not at redeem.** The `/sign-in/redeem` step needs no code.
- **Search results show the matching item.** A comment hit shows the comment's text (linking
  to it in its thread) with the thread's title, not the post's title.
- **Day boundaries are UTC.** Posts group by UTC day, matching how `created_at` is stored.
- **API tokens store `last4`.** So their owner can tell them apart; auth uses only the hash.
- **`?tag=` is served from `/`.** The API's `tag` parameter returns 30 posts per page with a
  `page` parameter, the same as the site.
- **Private items are excluded from the API entirely**, including as the root of a thread.
- **`maf nuke` deletes the item's FTS rows explicitly**, because contentless FTS5 cannot be
  deleted from a trigger.
- **The name filter is on by default** and skipped with `confirm_names=1`, as the SPEC says.

## Open questions for the maintainer

1. **Token redemption and a second code entry.** `/sign-in/redeem` needs no code, but the browser
   blind-signs right after the code is checked, so a user who reloads loses it. Is re-entering
   the code (as now) acceptable, or should the code stay valid for redemption too?
2. **Source Code link.** The footer points at `https://github.com/` as a placeholder; give me
   the real repository URL.
3. **Contact address.** `/about` and `/guide` don't mention one. Should they show an address
   for takedown requests, alongside the moderation-request flow?
4. **Personal pins on search and tag pages.** The SPEC only describes pins on the 4-day list;
   should `/search` and `/?tag=` rows get pin buttons too?
5. **View counts on the API.** `GET /api/v1/posts` does not count as a view; only opening
   `/thread/<id>` on the site does. Keep that?
