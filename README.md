# MAF

An anonymous forum for Minerva University students, live at [maforum.net](https://maforum.net).

Only `@uni.minerva.edu` accounts may sign in.

Inside, you can make posts, share links, and discuss anonymously.

Have a question? Contact hello@maforum.net.

## Features

- **No profiles or accounts.** You sign in with your Minerva email, but MAF never stores or logs it.
- **A new name in every thread.** Every post and reply appears under a pseudonym unique to that thread, so replies in different threads can't be linked to each other.
- **Posts.** A post can be as simple as a title, such as an open question. Optionally, add a link, up to three hashtags, and text.
- **Hashtags with templates.** #hottakes, #help, #wondering and #confession suggest a template for posting and replying. They're not enforced. #hottakes is highlighted on the main page.
- **Replies.** Reply to the original poster (OP) or to any other reply. Tick "Make only visible to [name]" and only you and that person can read it: it's encrypted in your browser, so not even MAF can see it.
- **Emoji reactions** on posts and replies.
- **Main page.** Pin posts, search by text, browse by hashtag with the # icon, and by date with the range switcher.
- **Drafts.** Unfinished posts and replies are kept in your browser until they're posted.
- **Live updates.** When someone replies or reacts in a thread you have open, or posts while you're on the main page, a banner offers to show it. You only hear about what you're allowed to see. Posts that arrived since your last visit are labelled New.
- **Light and dark mode**, built for accessibility following the [A11Y Project](https://www.a11yproject.com/checklist/) checklist.
- **Moderation by flags.** There are no hard rules, but don't name specific students or staff. If five people flag a post, it becomes unlisted and shows an option to request a permanent deletion or restoration, decided case by case. Replies can be flagged the same way and are hidden until reviewed.

Pinned posts and private replies live in your browser. Sign in on a new device and they won't be there, and you'll appear under a new name in threads you've already posted in. This is to maintain anonymity and avoid profiles.

## Auditing privacy

You can check every privacy claim in this repo. Where to look:

| Claim | Where to check |
|---|---|
| Your email is never stored | `maf/auth.py` handles sign-in; codes live only in memory (`maf/memory.py`). The database schema (`maf/db.py`) has no email column. |
| Your posts can't be traced back to your email | Sign-in uses blind signatures (RFC 9474): the server signs a token without seeing it, then forgets the email. See `maf/blind.py` and `maf/static/login.js`. |
| Your names in different threads can't be linked | Each name comes from a keyed hash of your pass and the thread (`maf/labels.py`). |
| Private replies are unreadable to MAF | They're encrypted in the browser (`maf/static/private.js`); the server only checks their shape and stores the scrambled text (`maf/sealed.py`). Each person has a separate key per thread. |
| No IP addresses or request logs | Access logs are off in the app (`maf/main.py`) and in the web server (`deploy/Caddyfile`). |
| Pins and drafts stay on your device | `maf/static/pins.js` and `maf/static/drafts.js` only use your browser's storage. |
| Emails sent through the provider aren't logged | `maf/email.py` and `maf/azure_email.py` pass the address on and drop it. |

The full design, including what each party can and can't see, is in [SPEC.md](SPEC.md) and [PLAN.md](PLAN.md).

One limit: MAF's server also sends the page's code to your browser, so you're trusting that maforum.net runs the code in this repo. Releases are tagged (`v1.0.x`) so you can match what's deployed.

## Running it locally

```sh
uv sync --all-extras
EMAIL_BACKEND=console MAF_BASE_URL=http://localhost:8000 uv run python -m maf.main
```

Sign in with any `@uni.minerva.edu` address. The code is printed in the terminal (in development, `139145` also works; it never works in production). Run the tests with `uv run pytest`. Deployment is described in [deploy/aws.md](deploy/aws.md).

---

Not affiliated with Minerva University in any official way. MAF is run and maintained as an open student initiative. Licensed under [AGPL-3.0](LICENSE).
