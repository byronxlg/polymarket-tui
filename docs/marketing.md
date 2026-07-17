# Marketing strategy

Goal: qualified installs from people who already trade or watch prediction
markets - not impressions. Two channels to start (2026-07-17): Polymarket
comment threads and Moltbook. Every message sent is recorded in
`marketing-log.md`; Byron gets Telegram updates with links.

## Principles (non-negotiable)

1. **Disclosed identity.** We post as the project or its builder, never as a
   fake enthusiast. On Moltbook the account IS the project agent; on
   Polymarket comments the account is Byron's own. No sockpuppets, no
   astroturfing, ever.
2. **Value first.** Every message must stand on its own as a useful
   contribution to that thread - an observation about the book, a chart, an
   explanation - with the tool or blog link as the supporting detail, not
   the payload. If the message would be deleted as noise without the link,
   don't send it.
3. **Low volume.** Polymarket: at most 1-2 comments per day, only on threads
   where we genuinely have something to add (typically the day's
   highest-volume events, where our blog analysis already exists). Moltbook:
   respect the platform's rate limits and culture - mostly genuine
   participation, promotional content at most a small fraction of activity.
   Moltbook's own rules ban excessive self-promotion; treat that as the bar
   everywhere.
4. **Never repeat text.** Identical messages across threads are a spam
   signature and read as one. Each message is written for its thread.
5. **Stop on signal.** Downvotes, mod removal, or any warning on a channel:
   stop that channel, log what happened, reassess with Byron before
   resuming.
6. **Log everything.** Every message (or attempted message) goes in
   `marketing-log.md` with timestamp, channel, link, and full text - before
   or immediately after sending, never reconstructed later.

## Channels

### Polymarket comment threads

- Where: comment sections of high-volume markets we have real material for -
  the blog's current-events posts are written about exactly these events.
- What: short market-structure observations (the champion-vs-90-minute gap,
  a notable repricing, book depth). **No project name, no links** - see the
  filter finding below; the comment must stand purely as analysis.
- Recipe (established by the 2026-07-17 comment-filter experiment, logged in
  marketing-log.md): Polymarket's comment API returns 403 "Comment not
  allowed" for any comment containing the string `polymarket-tui` or a URL.
  Pure market-observation comments pass fine, whether posted by hand or
  through the browser automation - the automation itself is not blocked.
  So this channel is **reputation, not referral**: genuine analysis under
  Byron's account builds profile credibility; the only surface that can
  carry a link is the profile bio (edit that with Byron's ok, not the
  comment body).
- Auth: posts from Byron's own account. Each comment individually written
  and genuinely useful; hard cap 1-2/day; never a project mention.

### Moltbook (m/...)

- Identity: the `polymarket-tui` agent, claimed by Byron. The profile says
  what it is: the agent behind a terminal client for Polymarket.
- What: notes on prediction-market structure and what building/running the
  tool surfaces (odd books, resolution quirks, repricings) - the same
  material as the blog, in Moltbook-native form. Intro post first;
  occasional links to posts/tool where they fit the submolt's topic.
- Cadence: within platform rate limits; aim for a few good posts a week,
  not a daily drumbeat, plus genuine engagement (comments/upvotes) on
  others' posts.

## Reporting

Telegram updates to Byron at meaningful checkpoints (first posts on a
channel, account milestones, anything needing his action - e.g. the
Moltbook claim link), each with links to the messages sent since the last
update. Not on a fixed timer; on progress.

## Out of scope for now

Reddit/HN/X posting (accounts and separate norms), paid anything,
DMs/outreach to individuals. Revisit deliberately, not by drift.
