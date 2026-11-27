# MAF

A template for an anonymous forum for your organization: a university, a company, a club. Only people with an email at your domain can sign in, and nobody, including whoever runs it, can tell who wrote what. [Quick setup](#quick-setup) gets your own copy running.

## Features

- **No profiles or accounts.** You sign in with your organization email, but MAF never stores or logs it.
- **A new name in every thread.** Every post and reply appears under a pseudonym unique to that thread, so replies in different threads can't be linked to each other.
- **Posts.** A post can be as simple as a title, such as an open question. Optionally, add a link, up to three hashtags, and text.
- **Hashtags with templates.** #hottakes, #help, #wondering and #confession suggest a template for posting and replying. They're not enforced. #hottakes is highlighted on the main page.
- **Replies.** Reply to the original poster (OP) or to any other reply. Tick "Make only visible to [name]" and only you and that person can read it: it's encrypted in your browser, so not even MAF can see it.
- **Edit and delete your own replies.** Edit rewrites the reply; it's marked "(edited)". Deleting removes the words for good.
- **Edit your own posts.** The same Edit for your own post's text; its title, link and hashtags stay as they were.
- **Hide your own posts.** Hide Post takes it off every list and search; the link still works. Unhide brings it back.
- **Emoji reactions** on posts and replies.
- **Feed.** The Feed button in the header counts new replies and reactions to your posts and replies, and lists them. What you've already seen is remembered in your browser only.
- **Main page.** Pin posts, search by text, browse by hashtag with the # icon, and by date with the range switcher.
- **Markdown.** Posts and replies support bold, italics, `__underline__`, strikethrough, links, lists, quotes and code. Titles support bold, italics, underline and strikethrough.
- **Drafts.** Unfinished posts and replies are kept in your browser until they're posted.
- **Live updates.** When someone replies or reacts in a thread you have open, or posts while you're on the main page, a banner offers to show it. You only hear about what you're allowed to see. Posts that arrived since your last visit are labelled New.
- **Light and dark mode**, built for accessibility following the [A11Y Project](https://www.a11yproject.com/checklist/) checklist.
- **Name check.** Before a post, reply or edit goes up, a language model running on MAF's own server checks it for people's names and asks you to take them out. Nothing is sent to an outside service.
- **Moderation by flags.** There are no hard rules, but don't name specific people. If five people flag a post, it becomes unlisted and shows an option to request a permanent deletion or restoration, decided case by case. Replies can be flagged the same way and are hidden until reviewed. A reply that breaks the rule can be removed, leaving only the reason in its place.

Pinned posts, what you've opened (for the New section) and private replies live in your browser. Sign in on a new device and they won't be there, and you'll appear under a new name in threads you've already posted in. This is to maintain anonymity and avoid profiles.

## Auditing privacy

You can check every privacy claim in this repo. Where to look:

| Claim | Where to check |
|---|---|
| Your email is never stored | `maf/auth.py` handles sign-in; codes live only in memory (`maf/memory.py`). The database schema (`maf/db.py`) has no email column. |
| Your posts can't be traced back to your email | Sign-in uses blind signatures (RFC 9474): the server signs a token without seeing it, then forgets the email. See `maf/blind.py` and `maf/static/login.js`. |
| Your names in different threads can't be linked | Each name comes from a keyed hash of your pass and the thread (`maf/labels.py`). |
| Private replies are unreadable to MAF | They're encrypted in the browser (`maf/static/private.js`); the server only checks their shape and stores the scrambled text (`maf/sealed.py`). Each person has a separate key per thread. |
| On Dates, only a profile's owner sees who replied | Sending your profile is a private reply, encrypted in your browser (`#send-dialog` in `maf/templates/item.html`, `maf/static/private.js`). Private replies are left out for everyone but the two people (`_visible_ids` in `maf/store.py`). Dates posts never show on the front page, hashtags, New or search (`_post_where` in `maf/store.py`). |
| Unmatch, Hide and deleting a profile erase the messages | `close_profile_reply`, `close_sent_profiles` and `delete_own_post` in `maf/store.py`, all through `_secure_delete`. |
| No IP addresses or request logs | Access logs are off in the app (`maf/main.py`) and in the web server (`deploy/Caddyfile`). API use is only tallied per endpoint per day, with no post ids or times (`maf/usage.py`). |
| Pins, drafts and new Dates matches stay on your device | `maf/static/pins.js`, `maf/static/drafts.js` and `maf/static/dates-thread.js` only use your browser's storage. |
| MAF doesn't track when you check your Feed | What you've seen is kept in your browser (`maf/static/bell.js`); the server only lists replies and reactions (`notifications` in `maf/store.py`). |
| The name check stays on MAF's server | It runs [Presidio](https://github.com/microsoft/presidio) with spaCy's `en_core_web_lg` English model on the server itself (`maf/namefilter.py`); no text is sent elsewhere. |
| Deleted and removed words are gone | Deleting overwrites the data on disk (`_secure_delete` in `maf/store.py`). |
| Emails sent through the provider aren't logged | `maf/email.py` and `maf/azure_email.py` pass the address on and drop it. |

The full design, including what each party can and can't see, is in [SPEC.md](SPEC.md) and [PLAN.md](PLAN.md).

One limit: the server also sends the page's code to your browser, so people are trusting that your site runs the code in this repo. Releases are tagged (`v1.0.x`) so anyone can match what's deployed.

## Quick setup

### 1. Try it on your computer (2 minutes)

You need [uv](https://docs.astral.sh/uv/). Then:

```sh
git clone https://github.com/SomeoneElseSt/MAF.git && cd MAF
uv sync --all-extras
MAF_EMAIL_DOMAIN=example.edu EMAIL_BACKEND=console MAF_BASE_URL=http://localhost:8000 uv run python -m maf.main
```

Open http://localhost:8000 and sign in with any `@example.edu` address. The code is printed in the terminal; in development `139145` also works (never in production). Run the tests with `uv run pytest`.

### 2. Make it yours

Everything about your organization is a setting in the server's environment (`/etc/maf/env` once it's online). Unset ones keep the original deployment's values.

| Setting | What it does | Example |
|---|---|---|
| `MAF_EMAIL_DOMAIN` | Only addresses at this domain can sign in | `example.edu` |
| `MAF_COMMUNITY` | Who it's for, as in "An anonymous forum for …" | `Example College students` |
| `MAF_FORUM_NAME` | The full name, shown in link previews | `Example College Anonymous Forum` |
| `MAF_CONTACT_EMAIL` | The contact address shown on the site | `hello@example.edu` |
| `MAF_ORG_TAG` | A suggested hashtag for your organization; the name check never treats it as a person | `example` |
| `MAF_SITE_NAME` | The short name: header, page titles, emails | `MAF` |
| `MAF_EMAIL_KIND` | "Enter your … email" on the sign-in page, e.g. `work` | `university` |
| `MAF_NAMING_RULE` | Show "Please don't name students or staff." under the boxes (`true` or `false`) | `true` |
| `MAF_HASHTAGS_FILE` | A JSON file of hashtags with posting and reply templates; copy `deploy/hashtags.example.json` | built-in |
| `MAF_SOURCE_URL` | Your fork's code, linked in the footer (the AGPL asks you to share your changes) | this repo |
| `MAF_BASE_URL` | Your site's address | `https://forum.example.edu` |
| `MAF_EMAIL_FROM` | The address sign-in codes come from | `DoNotReply@forum.example.edu` |
| `MAINTAINER_EMAIL` | Where moderation requests are emailed | |

For a local try, put them before the run command above, for example `MAF_COMMUNITY="Example College students"`.

Two things are still edited in a fork: your domain in `deploy/Caddyfile`, and `REPO_URL` (your fork) in `deploy/setup.sh`.

### 3. Put it online

- **A server:** any Ubuntu 24.04 machine with 2 GB of memory (the name check's language model needs about 1 GB). A small AWS EC2 instance is enough.
- **A domain** with an A record pointing at the server.
- **An email provider** for sign-in codes: Azure Communication Services or AWS SES. Verify your domain with it and set up SPF, DKIM and DMARC so codes don't land in spam.

Then, on the server:

```sh
curl -O https://raw.githubusercontent.com/YOU/MAF/main/deploy/setup.sh   # from your fork
sudo bash setup.sh         # installs everything, creates /etc/maf/env with fresh secrets
sudo nano /etc/maf/env     # your settings from step 2, and the email provider
sudo systemctl restart maf
```

For the email provider, either keep `EMAIL_BACKEND=ses` (with `AWS_REGION` and an IAM role allowed to send, as in `deploy/aws.md`) or set `EMAIL_BACKEND=azure` and `AZURE_EMAIL_CONNECTION_STRING`.

HTTPS certificates are automatic. To ship updates later, `deploy/release.sh` runs the tests, tags a version and deploys it; point it at your server with `MAF_SERVER`, `MAF_SSH_KEY` and `MAF_SITE`. A full AWS walkthrough is in [deploy/aws.md](deploy/aws.md).

### Moderating

There are no admin pages. You moderate with the `maf` command on the server: `maf requests` and `maf hidden` list what needs a look, then `maf unhide`, `maf remove` or `maf nuke`. `maf nsfw` and `maf sfw` move a post to the NSFW side and back. See the Moderation section of [SPEC.md](SPEC.md).

## Contributing

Open a [GitHub issue](https://github.com/SomeoneElseSt/MAF/issues) describing the problem or idea before you start on a pull request. That way we can agree on it first, and your pull request is much more likely to be reviewed and merged.

---

Originally made for and at Minerva University in San Francisco, California. Licensed under [AGPL-3.0](LICENSE).
