# MAF — Design Plan

*As of 2026-11-22 · status: signed off*

## Summary

MAF (Minerva Anonymous Forum) is an anonymous forum styled like Hacker News that only Minerva students can read and post on. Nobody can tell who wrote what, including the people who run it.

Today the main channel is one Telegram group shared by every class. Each message notifies about a thousand people under your real name, so people post less and hold back unpopular opinions. MAF gives students a place to exchange ideas without that cost.

You verify once with a `@uni.minerva.edu` email. After that your device holds an anonymous pass. The email is only a gate: it is never stored, and it can't be linked to anything you post.

## Goals and non-goals

v1 is a working forum with real anonymity and as little friction as possible. Growth and polish come after it exists.

**Goals**

- Only `@uni.minerva.edu` holders can read or post.
- Signing in on a new device is exactly as simple as signing up the first time.
- Nobody running MAF can link a person to a post, by design rather than by promise.
- A plain HTML page with as few dependencies as possible, open source.
- The maintainer only builds it, runs the domain and does occasional upkeep.

**Non-goals for v1**

- Votes or rankings (emoji reactions exist, but nothing is sorted by them).
- Image or file uploads, DMs outside a thread, notifications, karma, profiles, editing posts, a mobile app.
- Bans or an admin dashboard.
- Recovery keys or passwords.

## Privacy model

Minerva can see who is a member, because it owns the mail server that receives the code. Nobody can see who wrote what.

| Party | Can see | Can't see |
| --- | --- | --- |
| Minerva | That a student received a code email from MAF's domain | Posts, or which pass belongs to whom |
| AWS SES (sends the code) | The recipient address while sending | Anything on the forum |
| MAF server and maintainer | Posts, passes, per-thread IDs | Any email, or which email is behind which pass |
| Other students | Posts and per-thread IDs | Anything linking one person's posts across threads |

**Nothing derived from an email is ever written to disk:** no list, no hash, no salted or keyed hash.

Why this keeps the maintainer in the clear: if anyone asks who posted something, the honest answer is "MAF can't know, by design." The code is open source, so anyone can check the design.

**Known limits, stated openly on the site:**

- The code that runs the anonymous step is served by MAF's own server, so users trust it matches the published code.
- The timing of requests and shared IP addresses can leak clues. Logs are off to reduce this.

## Sign-in flow

Sign-up and login are the same steps: enter your email, enter the 6-digit code, and your device gets an anonymous pass.

1. You enter a `@uni.minerva.edu` address. Any other domain is rejected.
2. MAF sends a 6-digit code through AWS SES. The email is short: subject "Your code: 482913", with the MAF name at the top in the site's style. The code expires after 10 minutes and is held in memory only.
3. You enter the code. Your browser then gets a pass signed with a **blind signature**: the server signs it without seeing it, so it can later check the pass is genuine but can't tell whose it is. This is a standard technique (RFC 9474, the method behind Privacy Pass) with existing libraries.
4. The server forgets the email. Your device keeps the pass in a long-lived cookie.

**Switching devices** means doing the same steps again, which gives that device its own pass. There are no cross-device accounts, no passwords and no recovery keys.

**Limiting abuse without remembering anyone.** Each email can request a code only once every 10 minutes. That limit lives in memory alongside the code and is never saved. It stops anyone from flooding a classmate's inbox, and makes collecting extra passes slow. Since there are no votes, extra passes could only add flags, which the maintainer can undo.

**Rules:** passes have no creation time stored, and emails and IPs are never logged.

## Per-thread IDs

Each person gets a random two-word name like `quiet-otter` that stays the same within one thread and changes in every other thread.

```
Thread: "Should we move the Berlin rotation to fall?"     OP: amber-fox
  amber-fox (OP)   I think fall works better because…
    quiet-otter    Disagree, the housing situation…
      amber-fox (OP)   Fair, but…

Thread: "Best ramen near the res?"                        OP: tidy-crane
  quiet-otter    Ichiran, obviously   ← a different person
```

- **Within a thread** you can follow who is replying to whom.
- **Across threads** nothing connects your posts, so nobody can build a history or profile of you.
- The thread's author is tagged **OP**.
- Clicking a name opens a pop-up: "Names change per thread so no one can follow you around. There are no profiles, on purpose."
- The User Guide explains this.

## Posts and pages

It looks like Hacker News but has no votes: text or link posts, nested comments, a search bar, and a sorter for date or views.

- **Posts:** a title plus either a link or text. No images or uploads.
- **Comments:** nested replies, oldest first within a thread.
- **No votes.** Nothing ranks posts by popularity unless you choose to sort by views.
- **Search bar** at the top of every page, searching post titles, post text and comments. It uses the database's built-in full-text search, so it adds no dependencies. Searches are never logged.
- **Sorter** next to the search bar: newest first (default), oldest first, or most viewed. It applies to the post list and to search results.
- **Four days per page.** The home page shows the last 4 days, grouped by day, with ‹ and › arrows beside the date range at the top to step between pages. The date range always matches what's on screen: Newest and Most viewed start at the latest 4 days, Oldest starts at the first 4 days MAF ever had posts, and the arrows step through time from there. Search covers all posts.
- **No IDs in the list.** IDs only appear inside threads, since a random name adds nothing on the front page.
- **View counts, kept anonymous:** each post shows how many times it's been opened. A pass counts once per post per 24 hours. Which pass opened which post is kept in memory only and wiped daily, so only the total is ever saved and no one's reading history exists.
- **Pinned posts.** The maintainer can pin a post (for example a welcome post) with `maf pin`. Pinned posts sit in a "Pinned" group above Today, only under Newest and only on the latest page. Under Oldest and Most viewed they appear in their normal day.
- **Your own pins.** Hovering a post in the list shows a small pin at the right of the row (always visible on phones). Clicking it moves the post into Pinned, under the maintainer's pins, and the pin stays filled so you can click it again to unpin. Pins are saved in your browser only: MAF's server never learns what you pinned, and they don't follow you to another device. They show in the same place as the maintainer's pins, under Newest on the latest page.

## Hashtags

Posts can carry up to 3 hashtags, which make it easy to browse one topic.

- **Adding them:** the submit form has a Hashtags field ("Up to 3, separated by commas."). Anyone can make up a new tag; there's no fixed list.
- **Where they show:** in a post's details after a centered dot, e.g. "2 hours ago, 14 comments, 61 views · #rotations, #berlin". Each tag is a link.
- **Browsing:** a # button inside the search bar opens a list of every tag with its post count, most used first. Picking one, or clicking a tag on a post, shows only posts with that tag, and the search bar shows "#tag".
- **Templates:** once a post has any tag, the Text box suggests a short dash-line outline (what it's about, your claim or question, what kind of conversation you'd like). With no tags it shows an example post instead.

### Tags with templates

Four tags describe what kind of post it is, and each comes with its own guidance. Each one sets the outline in the submit Text box and the "Write a reply" placeholder in its threads; the top "Write a comment" box stays plain. Other tags, such as `#minerva`, `#academics` or a city, are plain free-form topics with the default outline. More templated tags can be added later if they turn out to be needed.

| Tag | For | Submit outline | Reply prompt | Thread banner |
| --- | --- | --- | --- | --- |
| `#hottakes` | Arguing an unpopular opinion | Your take in one sentence; why you think it; the strongest argument against it; what could change your mind | Which part of the take you're responding to; your reason or experience; what would change your mind | "#hottakes etiquette: argue with the take, not the person. Push back as hard as you like, assume the poster means it in good faith, and say what would change your mind." |
| `#help` | Practical help | What you need help with; what you've already tried; your situation (city, deadline, anything that narrows it down); what kind of answer would help most | What worked for you, or who to ask; how sure you are and how recent your experience is | None |
| `#wondering` | Open, low-stakes questions | Your question; why you're curious; your best guess so far | Your answer or a guess; what it's based on | None |
| `#confession` | Something you did or feel | What happened or what you're feeling; how you feel about it now; what you'd like back (to be heard, advice, or company). The outline ends: "Leave out details that could identify you or anyone else." | Respond to the person, not the verdict; share something similar if you have it | "#confession etiquette: respond to the person, not the verdict. Be kind, and don't guess who wrote it or who it's about." |

- **Only `#hottakes` is highlighted** in lists: the row sits on a faint warm (ember) tint and the tag is ember. Banners use the same tint.
- **If a post has two templated tags,** the first one typed sets the templates and banner.

## Private replies

Inside a thread you can reply so only one other person sees it, for example to ask someone about their experience without telling the whole thread.

- **How:** under every comment box, after "Commenting as: calm-badger ·" (or "Replying as:"), a checkbox reads "Make only visible to amber-fox (OP)", naming whoever you're replying to, followed by an (i) that explains it.
- **What people see:** the two of you see the reply marked "Private, only you and quiet-otter". Everyone else sees the thread as if it weren't there. Replies inside a private exchange stay private; the checkbox is ticked and locked.
- **Limits, stated in the (i) card:** a private reply belongs to the pass you posted from, so you only see it on that device. It's stored on the server like any comment, not end-to-end encrypted. Other students can't see or flag it.
- **Left out of** search, comment counts, the developer API and the name filter's flag backstop (there's nobody else to flag it). The name filter still runs before it's saved.

| Page | What it shows |
| --- | --- |
| Home | Submit, the search bar with its # button, a Dark/Light toggle and the sorter at the top, then pinned posts (Newest only) and four days of posts |
| Thread | A post and its comments; hidden posts show a banner with Request unhide and Request deletion; #hottakes threads show the etiquette banner |
| Submit | New post form |
| About | What MAF is and why it exists |
| User Guide | Anonymity, per-thread IDs, the rule, flags; links to Use this data |
| Use this data | How to read the forum from an AI agent (MCP), the command line or curl |
| Sign in | Email and code |

## Reactions

Posts and comments can get emoji reactions, picked from a small fixed set.

- **Where:** under a post's text, and in each comment's action line after Reply and Flag. Each reaction shows the emoji and a count; your own sit on a soft grey tint. Clicking one adds or removes yours, and a small smiley opens a picker of 24 emoji, including 👍, 👎 and 😡.
- **Not on the front page.** Nothing is sorted or ranked by reactions.
- **Private replies** can have reactions too; only the two people see them.
- **Known trade-off:** extra passes can inflate counts, so reactions can act a bit like votes. That's accepted.

## Name filter

Posts that seem to name a person get a warning before they're saved, and the poster decides. There are no lists of names to maintain.

- **Rule:** no naming students or staff. It's shown on the submit page and in the User Guide.
- **Tool:** Microsoft Presidio, which detects people's names in text. It runs on the same server and only when someone submits, so reading is unaffected. Expect tens of milliseconds per submission, to be measured during the build.
- **On a match** the poster sees: "This looks like it names someone. MAF doesn't allow naming students or staff. If it's a public figure, you can post anyway." with two buttons, **Edit post** and **Post anyway**.
- **No allowlist:** public figures like Ben Nelson, Kant or Elon Musk go through with one extra click. Nothing about Minerva people is stored.
- **Backstop:** if someone clicks Post anyway on a classmate's name, 5 flags hide it.
- **Limits:** it misses some lowercase names and can be fooled on purpose. It discourages naming people; it can't fully stop it.

## Moderation

The community hides posts by flagging them. Anyone can then ask the maintainer to unhide or remove a hidden post, and the maintainer acts with a small command-line tool on the server. There are no admins, no bans and no dashboard.

| Action | Who | Effect |
| --- | --- | --- |
| Flag | Anyone, once per post | Hidden from the main page and search after 5 flags from different passes |
| Request unhide | Anyone, once per hidden post | Emails the maintainer right away |
| Request deletion | Anyone, once per hidden post | Emails the maintainer right away |
| Unhide | Maintainer, via `maf unhide` | Visible again, and flags can never hide it again |
| Nuke | Maintainer, via `maf nuke` | Deleted from the database; the link stops working |

- **Hidden posts stay reachable by their direct link.** The post is faded and shows a banner, "Five people flagged this post, so it's been unlisted. You can still read it here and ask for it to come back or be removed permanently.", with two buttons: **Request unhide** and **Request deletion**.
- **Requests are anonymous.** Only the post ID and a count are saved, with no record of who asked.
- **Notification:** every request sends the maintainer an email through SES right away, for example "Unhide requested for post #123 (4 requests so far)." It names no one. This can be batched later if traffic gets heavy.
- **The `maf` command-line tool** runs on the server over SSH, so there's no raw SQL:

  | Command | What it does |
  | --- | --- |
  | `maf requests` | Lists open requests: post ID, title, unhide or nuke, how many |
  | `maf hidden` | Lists hidden posts |
  | `maf show <id>` | Prints a post with its flag and request counts |
  | `maf unhide <id>` | Makes it visible again; flags can never hide it again |
  | `maf nuke <id>` | Deletes the post and its comments, after a yes/no confirmation |
  | `maf dismiss <id>` | Clears its requests without changing anything |
  | `maf pin <id>` / `maf unpin <id>` | Pins a post above Today under Newest, or unpins it |
- **No admins:** there are no admin codes, roles or buttons, so nothing about moderation can be linked to anyone.
- **Legal position:** in the US, Section 230 generally protects the operator from liability for what users post. Text and links only removes the serious risks of hosted images. The one real duty is acting on illegal content once told about it, which is what Nuke is for.

## Accessibility

MAF should pass everything on the [A11Y Project checklist](https://www.a11yproject.com/checklist/) (WCAG 2.2 A and AA) in both themes. That covers working fully by keyboard, making sense to screen readers, enough contrast, usable at 200% zoom and on a phone, and never using colour alone to carry meaning. SPEC.md lists the specifics.

## Use this data (developer access)

Students can read MAF from their own tools: an AI agent through MCP, a terminal, or plain curl. The User Guide links to a "Use this data" page that explains how.

- **Read-only.** Agents and scripts can list, read and search posts. Posting stays in the browser, where the name warning and the rule are shown.
- **Students only, like the site.** Signed in on the Use this data page, you click **Create token** and get a read token, shown once. It belongs to your anonymous pass, so it reveals nothing about who you are. You can revoke it on the same page.
- **What it returns** is the same as the site: posts, comments and per-thread IDs. Hidden posts are left out, and nuked posts are gone.
- **Three ways to use it**, all documented on the page with copy-paste examples:
  - **MCP server** for agents like Claude Code or Cursor, with tools to list a week's posts, read a thread and search.
  - **curl** against a small JSON API.
  - **The same API from any script.**
- **Rate-limited** per token, so one script can't slow the site down.
- **Trade-off to accept:** posts can leave the students-only wall this way, for example into an AI provider's systems. That was already possible by copying and pasting, so the token adds convenience, not a new hole. The page says so plainly.

## Infrastructure

Everything runs on AWS using existing credits: one small server, a domain, and Amazon's email service. The only real out-of-pocket cost is about $15 a year for the domain.

| Piece | Choice | Cost |
| --- | --- | --- |
| Server | One EC2 `t4g.small` | A few dollars a month, covered by credits |
| App | Python with server-rendered HTML, SQLite database, managed with uv | Free |
| Domain | `maforum.net`, registered at Namecheap with domain privacy on | $12.48 first year, about $15/yr after |
| DNS | Namecheap's free DNS (server address, SES DKIM and DMARC records) | Free |
| Email | AWS SES for login codes and moderation requests: verify the domain, then request production access (about a day) | About $0.10 per 1,000 emails |
| HTTPS | Caddy | Free |

**Privacy checklist**

- [ ] Web server and app access logs turned off
- [ ] No IP addresses stored anywhere
- [ ] SES delivery logging and event publishing off
- [ ] No analytics and no third-party scripts or fonts
- [ ] Rate limits keyed by pass, never by IP

## Decisions made

| Decision | Chosen | Why |
| --- | --- | --- |
| Login method | Email code via AWS SES | Google sign-in would show the app in Minerva's admin console |
| Limiting extra passes | No cap; 10-minute in-memory cooldown | Any record that catches repeat sign-ups lets the operator check membership |
| Votes | None | Removes the main thing extra passes could abuse |
| Ordering | Newest (default), oldest, or most viewed | Recency first; views are an opt-in sort |
| View counts | Total only; per-pass dedupe in memory for 24 h | Counts stay honest without storing reading history |
| Search | Built-in SQLite full-text search, queries not logged | No extra dependency, nothing about readers saved |
| Hiding | 5 flags hide from the main page; Request unhide / nuke emails the maintainer | Students can act at 3am; no admin system to build or trust |
| Uploads | Text and links only | Avoids hosting illegal images |
| Developer access | Read-only API + MCP server with per-pass read tokens | Dev-friendly without opening posting to scripts or breaking the students-only gate |
| Pinning | Maintainer pins via `maf pin`; anyone pins for themselves in their browser; shown under Newest only | A welcome post without admins, and saved threads without the server knowing what anyone saved |
| Hashtags | Up to 3 free-form tags per post, browsed from a # button in the search bar | Topic browsing without the maintainer curating categories |
| Reactions | 24 fixed emoji on posts and comments, counts shown only in threads | Light feedback without a ranking; inflated counts are accepted |
| Templated tags | The four kinds of post (#hottakes, #help, #wondering, #confession) get submit and reply outlines; topics like #minerva are plain tags; only #hottakes is highlighted | Shapes the kinds of post that most need it; start small and add more once real posts show the need |
| Private replies | Checkbox per reply, visible to the two people only, tied to the pass | Lets people follow up one-to-one without leaving the thread or adding DMs |

## Sign-off

Signing off means this plan is ready to hand to pi for implementation.

- [x] Maintainer approves the plan
