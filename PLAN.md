# MAF — Design Plan

*As of 2026-11-22 · status: awaiting sign-off*

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

- Votes or rankings.
- Image or file uploads, DMs, notifications, karma, profiles, editing posts, a mobile app.
- Bans or an admin dashboard.
- Recovery keys or passwords.

## Privacy model

Minerva can see who is a member, because it owns the mail server that receives the code. Nobody can see who wrote what.

| Party | Can see | Can't see |
| --- | --- | --- |
| Minerva | That a student received a code email from MAF's domain | Posts, or which pass belongs to whom |
| AWS SES (sends the code) | The recipient address while sending | Anything on the forum |
| MAF server and admins | Posts, passes, per-thread IDs | Any email, or which email is behind which pass |
| Other students | Posts and per-thread IDs | Anything linking one person's posts across threads |

**Nothing derived from an email is ever written to disk:** no list, no hash, no salted or keyed hash.

Why this keeps the maintainer in the clear: if anyone asks who posted something, the honest answer is "MAF can't know, by design." The code is open source, so anyone can check the design.

**Known limits, stated openly on the site:**

- The code that runs the anonymous step is served by MAF's own server, so users trust it matches the published code.
- The timing of requests and shared IP addresses can leak clues. Logs are off to reduce this.

## Sign-in flow

Sign-up and login are the same steps: enter your email, enter the 6-digit code, and your device gets an anonymous pass.

1. You enter a `@uni.minerva.edu` address. Any other domain is rejected.
2. MAF sends a 6-digit code through AWS SES. The email is deliberately bland: subject "Your code: 482913", no MAF branding. The code expires after 10 minutes and is held in memory only.
3. You enter the code. Your browser then gets a pass signed with a **blind signature**: the server signs it without seeing it, so it can later check the pass is genuine but can't tell whose it is. This is a standard technique (RFC 9474, the method behind Privacy Pass) with existing libraries.
4. The server forgets the email. Your device keeps the pass in a long-lived cookie.

**Switching devices** means doing the same steps again, which gives that device its own pass. There are no cross-device accounts, no passwords and no recovery keys.

**Limiting abuse without remembering anyone.** Each email can request a code only once every 10 minutes. That limit lives in memory alongside the code and is never saved. It stops anyone from flooding a classmate's inbox, and makes collecting extra passes slow. Since there are no votes, extra passes could only add flags, which an admin can undo.

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
- The "How it works" page explains this.

## Posts and pages

It looks like Hacker News but has no votes: text or link posts, nested comments, a search bar, and a sorter for date or views.

- **Posts:** a title plus either a link or text. No images or uploads.
- **Comments:** nested replies, oldest first within a thread.
- **No votes.** Nothing ranks posts by popularity unless you choose to sort by views.
- **Search bar** at the top of every page, searching post titles, post text and comments. It uses the database's built-in full-text search, so it adds no dependencies. Searches are never logged.
- **Sorter** next to the search bar: newest first (default), oldest first, or most viewed. It applies to the post list and to search results.
- **View counts, kept anonymous:** each post shows how many times it's been opened. A pass counts once per post per 24 hours. Which pass opened which post is kept in memory only and wiped daily, so only the total is ever saved and no one's reading history exists.

| Page | What it shows |
| --- | --- |
| Home | Search bar and sorter at the top, the post list (newest first by default), plus the no-naming rule |
| Thread | A post and its comments |
| Submit | New post form |
| How it works | Anonymity, per-thread IDs, rules |
| Sign in | Email and code |
| Admin code | Where an admin enters their code |

## Name filter

Posts that seem to name a person get a warning before they're saved, and the poster decides. There are no lists of names to maintain.

- **Rule:** no naming students or staff. It's shown during sign-in and on the home page.
- **Tool:** Microsoft Presidio, which detects people's names in text. It runs on the same server and only when someone submits, so reading is unaffected. Expect tens of milliseconds per submission, to be measured during the build.
- **On a match** the poster sees: "This looks like it names someone. MAF doesn't allow naming students or staff. If it's a public figure, you can post anyway." with two buttons, **Edit post** and **Post anyway**.
- **No allowlist:** public figures like Ben Nelson, Kant or Elon Musk go through with one extra click. Nothing about Minerva people is stored.
- **Backstop:** if someone clicks Post anyway on a classmate's name, 5 flags hide it.
- **Limits:** it misses some lowercase names and can be fooled on purpose. It discourages naming people; it can't fully stop it.

## Moderation

The community hides posts by flagging them, and three admins can restore or hide posts. There are no bans and no dashboard.

| Action | Who | Effect |
| --- | --- | --- |
| Flag | Anyone, once per post | Hidden from everyone after 5 flags from different passes |
| Restore | Any 1 admin | Visible again, and further flags can't re-hide it |
| Hide | 2 of 3 admins | Hidden from everyone except admins; kept in the database |

- **Admins** are the maintainer and two friends, one admin code each.
- **Votes to hide** count per admin code, not per device, so one admin on two devices counts once.

**Admin sign-up flow**

1. **Setup (once, at deploy):** the maintainer generates 3 starter codes, puts them in the server's settings, and hands one to each admin in person or over an encrypted chat, never by email. The launch post names who the admins are.
2. **Sign in like everyone else:** email code, then an anonymous pass, exactly as for any student.
3. **Enter the starter code** on the Admin code page, which isn't linked from anywhere. MAF then shows a new **personal code** that only that admin's browser sees: "Save this in your password manager. The code you were given no longer works." The device becomes an admin device, and the Restore and Hide buttons appear.
4. **New device:** sign in, then paste the personal code.
5. **Lost or leaked code:** the maintainer issues a fresh starter code and the admin repeats step 3. The old personal code stops working on every device.

**The maintainer never knows anyone's personal code**, so 2-of-3 Hide really means two different people.

**Admin status is kept separate from the admin's pass.** The admin cookie is never written onto the pass. Otherwise anyone who knows which friend holds which code could link that admin's own posts to them. Admins post as anonymously as everyone else. The only thing recorded per admin is the Hide vote, which has to be counted per admin.

Wrong admin-code attempts are rate-limited, and the codes are long enough that guessing them isn't realistic.
- **2 of 3, not 3 of 3**, so one inactive or graduated admin doesn't block hiding something illegal.
- **No dashboard:** admins see Restore and Hide buttons on the posts themselves, and hidden posts appear greyed out for them.
- **Not a one-way door:** switching to admin-only review, where flags only notify admins, is a single setting.
- **Legal position:** in the US, Section 230 generally protects the operator from liability for what users post. Text and links only removes the serious risks of hosted images. The one real duty is acting on illegal content once told about it, which is what Hide is for.

## Infrastructure

Everything runs on AWS using existing credits: one small server, a domain, and Amazon's email service. The only real out-of-pocket cost is about $14 a year for the domain.

| Piece | Choice | Cost |
| --- | --- | --- |
| Server | One EC2 `t4g.small` | A few dollars a month, covered by credits |
| App | Python with server-rendered HTML, SQLite database, managed with uv | Free |
| Domain | Route 53, no "Minerva" in the name | About $14/yr; credits usually don't cover registration |
| DNS | Route 53 hosted zone | $0.50/month |
| Email | AWS SES: verify the domain, then request production access (about a day) | About $0.10 per 1,000 emails |
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
| Hiding | 5 flags auto-hide, admin Restore | Students can act at 3am; abuse is slow and undone with one click |
| Uploads | Text and links only | Avoids hosting illegal images |

## Sign-off

Signing off means this plan is ready to hand to pi for implementation.

- [ ] Maintainer approves the plan
- [ ] Two other admins confirmed
