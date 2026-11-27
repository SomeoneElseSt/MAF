# Instructions for coding agents working on MAF

## Hard rule: never read what students write

MAF is an anonymous forum. Nobody building or maintaining it, human or agent, reads students' words.

- **Never read, print, query, copy, summarise or screenshot anything students wrote on the live site**: post titles, post text, links, replies, private replies (even encrypted ones), or hashtags tied to specific posts. This covers the production database (`/var/lib/maf/maf.db`), its backups and EBS snapshots, copies of it, and anything else that holds it.
- **Avoid it, don't just skip it.** When a task touches production data, ask only for what the task needs and never select content columns (`title`, `text`, `url`, `sealed`). Counts and ids are fine, for example `SELECT COUNT(*) FROM item`.
- **Don't run the moderation commands that print content** (`maf show`, `maf requests`, `maf hidden`). Moderation is the maintainer's job. `maf pin`, `maf unpin`, `maf unhide`, `maf dismiss`, `maf remove` and `maf nuke` take an id the maintainer gives you and are fine to run when asked.
- **Don't browse the live site as a signed-in user** to look at threads.
- **Debug with the local test server and its sample data instead.** It behaves like production. See the local development notes.
- **If a task seems to need what students wrote, stop and ask the maintainer.** Don't work around this rule.

## Before changing anything people see: read design/index.html

`design/index.html` is MAF's design system and its development flow. Read its Design system tab (the HTML is plain
text on purpose) before touching templates, CSS, JavaScript or wording. When a change is visible, update its screen in
`design/screens.py`, run `uv run --with playwright python design/screens.py`, and open the Screens tab for the
maintainer's sign-off before releasing.

## Other notes

- Design docs: `PLAN.md` and `SPEC.md`. Privacy claims and where they're implemented: the "Auditing privacy" table in `README.md`.
- Store nothing derived from emails, and no IP addresses or request logs.
