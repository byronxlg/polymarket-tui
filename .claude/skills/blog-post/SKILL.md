---
name: blog-post
description: Write and publish a new blog post for the polymarket-tui site (site/blog/). Use whenever asked to write a blog post, add SEO/blog content, publish the next post from the queue, or when the daily blog automation runs. Covers the full pipeline - picking the topic from docs/blog-todo.md, writing the datasheet-styled HTML post, and updating the blog index, landing page, RSS feed, sitemap, and the to-do queue.
---

# Writing a blog post

The blog is plain static HTML in `site/`, deployed to GitHub Pages at
`https://byronxlg.github.io/polymarket-tui/` by `.github/workflows/pages.yml`
on merge to main. There is no build step and no generator: publishing a post
means writing one HTML file and keeping five other files in sync by hand.
Miss one and the site quietly rots (a post that exists but is unreachable, a
feed that stops updating), so treat the sync list as part of the post.

A post touches exactly these files:

| File | Change |
|---|---|
| `site/blog/<slug>.html` | the new post (create) |
| `site/blog/index.html` | add a row to the post list, newest first |
| `site/index.html` | landing `#blog` section: add the row, keep only the 3 newest |
| `site/blog/feed.xml` | new `<item>` at the top of the items |
| `site/sitemap.xml` | new `<url>` with `<lastmod>` |
| `docs/blog-todo.md` | record the post under Shipped, with date and path |

## 1. Pick the topic

Posts are **current-events-first**: the best search traffic and the most
interesting reading come from connecting a live news story to what
Polymarket is pricing. The evergreen queue in `docs/blog-todo.md` is the
fallback for quiet days.

Scan from both directions and pick the strongest story:

- **Markets first** - what is the money doing?
  - Trending by money: `curl 'https://gamma-api.polymarket.com/events?order=volume24hr&ascending=false&limit=12&closed=false'` -
    what is everyone trading right now?
  - Big moves: markets whose `oneDayPriceChange` is large. A move of 10c or
    more on a liquid market means news landed.
  - Then WebSearch the story behind the numbers.
- **News first** - what are the headlines, and do markets have a view?
  - WebSearch per domain Polymarket trades - politics, geopolitics, sports,
    crypto, business, entertainment (e.g. "politics news July 17 2026").
    A generic "top news today" query returns homepages, not stories.
  - Map a story to its markets:
    `curl 'https://gamma-api.polymarket.com/public-search?q=<terms>&limit_per_type=5'`.
  - The strong news-first angles: a big story the markets are actively
    repricing, and the quieter twist - a loud headline whose market barely
    moved (the market saw it coming, or does not believe it).

Whichever direction found the story, verify the event's facts with
WebSearch/WebFetch and every number against Gamma/CLOB.

Write the current-events post when there is a genuine story: a liquid market
(roughly $250k+ 24h volume) with a sharp move, or an imminent decision date
(election, verdict, launch, final) the news is already talking about. The
post's job is to connect the event to the numbers: what the market prices
now, how it got there, what the book and spread say about conviction, and
what would move it next.

Fall back to the queue when nothing qualifies. A quiet day gets an evergreen
post, not a forced take on a thin market. Take the **topmost unchecked
topic** (the queue is ordered by value; do not cherry-pick). If the queue is
empty, refill it with 5 new intent-targeted topics, then take the first.

Extra rules for current-events posts:

- Timestamp every number: "as of 2026-07-17 09:00 UTC". Odds move; the post
  must stay honest after they do.
- Report what the market prices, never what "will" happen. No predictions,
  no takes on the outcome - the neutral register of a market report.
- Slug and title name the event the way people search for it, and include
  the year (elections, championships, and verdicts recur).
- Do not re-cover an event written up in the last two weeks unless the
  picture changed materially (a 15c+ move or a resolution). Check the
  Shipped list in `docs/blog-todo.md` first - every post lands there.

## 2. Get the facts right

Posts are educational first, product second - that is what earns search
traffic and trust. Every claim about how Polymarket works must be verifiable:

- Exchange mechanics (ticks, order types, minimums, resolution) are pinned in
  `docs/trading.md` and `docs/api-reference.md`. Read the relevant section
  before writing; never write market mechanics from memory.
- For anything not covered there, probe the live APIs with curl
  (gamma-api.polymarket.com, clob.polymarket.com, data-api.polymarket.com)
  and describe what you observed.
- Every market number in a current-events post (price, move, volume) must be
  fetched at write time, never recalled or estimated - quote what the API
  returned, timestamped. Fetch the numbers you will quote in one tight batch
  and stamp the post with that batch's time: one "as of" moment, not one per
  call.
- API footguns learned from real runs: trust `volume24hr` and `liquidity`;
  treat an event's lifetime `volume` as suspect (it has printed billions).
  `public-search` returns `events` (markets nested inside) plus `profiles` -
  the events are what you want. `clob.polymarket.com/prices-history` takes
  `startTs`/`endTs` (epoch seconds) and `fidelity` (minutes): drill from 6h
  candles down to 10-minute prints to pin an intraday move.
- App behaviour (keys, dry-run, screens) comes from the README and
  `docs/user-journeys.md`, not from guessing.

If a claim cannot be verified, cut it. A wrong fact in an SEO post is worse
than no post.

## 3. Write the post

Use the newest existing post in `site/blog/` as the structural reference and
match it exactly (nav, crumbs, `post-meta`, `article` with numbered
`sec-label` sections, `post-foot`, footer). All styling comes from
`site/assets/blog.css` - do not add inline styles or new CSS unless the post
genuinely needs a new element, and then add it to blog.css so later posts get
it too.

Head requirements (search engines read these; the reference post shows the
exact shape):

- `<title>`: post title, ideally under 60 chars, suffixed
  `— polymarket-tui blog`
- `<meta name="description">`: 140-160 chars, states what the reader learns
- `<link rel="canonical">` and `og:url`: the full
  `https://byronxlg.github.io/polymarket-tui/blog/<slug>.html` URL
- `og:type` article, `og:title`, `og:description`, `og:image` (reuse
  `assets/og.png`), `article:published_time`
- JSON-LD `BlogPosting` with the same headline, description, and date

Content rules:

- 800-1400 words. Long enough to actually teach the topic, short enough that
  every section pulls weight.
- Slug: lowercase, hyphenated, keyword-bearing (`how-to-read-a-polymarket-
  order-book`, not `post-2` or `order-books`).
- The title is what people search for; write it as the question or task the
  reader has, not a clever headline.
- Voice: plain, precise, user-facing. No emojis, no em dashes (use hyphens or
  restructure) - the `<title>` suffix's em dash is the one sanctioned
  exception, a site-wide brand convention. Prices in cents ("33c"). Explain
  jargon on first use.
- `post-meta` conventions: read time is the body word count divided by 200,
  rounded ("5 min read"); the tag is "market report" for current-events
  posts, "markets 101" for evergreen ones; the last crumb is a short kebab
  tag for the topic ("world-cup-final").
- One `<pre>` example rendering something terminal-shaped is on-brand and
  breaks up the text; use the `.g`/`.r`/`.c` spans for green/red/faint.
- polymarket-tui appears where it is genuinely the answer (usually the final
  numbered section plus the install CTA), never as the opening pitch.
- End the disclaimer line in `post-foot`: not affiliated with Polymarket, not
  financial advice.

## 4. Sync the five companion files

- `site/blog/index.html`: new `post-row` at the **top** of `.post-list`
  (date, dots, title).
- `site/index.html`: same row shape at the top of the `#blog` section's
  `.posts`; delete the oldest row if there are now more than 3.
- `site/blog/feed.xml`: new `<item>` first, `pubDate` in RFC 822 format
  (`Fri, 17 Jul 2026 09:00:00 +0000`), `guid` = the canonical URL. Use the
  actual publish time in UTC; if an existing item shares the date, the new
  pubDate must be strictly later, so newest-first stays true for readers.
- `site/sitemap.xml`: new `<url>` with `<loc>` and `<lastmod>` (YYYY-MM-DD).
- `docs/blog-todo.md`: add a Shipped line with the date and file path. For a
  fallback post, also check the topic off the Queue. A current-events post's
  Shipped line must name the event, not just the title, so the repeat check
  can match it: `- [x] <title> (event: <event>, <event-date>) - <pub-date>,
  <path>`.

## 5. Verify before shipping

- Serve the site and click through: `python3 -m http.server -d site 8000`,
  then check `/blog/`, the new post, and the landing `#blog` section render
  and cross-link correctly. In a headless run, fetch each page with curl and
  grep the served output for the new slug - a 200 alone proves the file
  exists, not that the links are right. Kill the server when done.
- Grep the new slug across `site/` - it must appear in the post file name,
  blog index, landing page, feed, and sitemap. Same spelling everywhere.
- Confirm the date is today's real date in all five places (page, feed,
  sitemap, todo, JSON-LD).

## 6. Ship

Branch `blog/<slug>`, commit everything as `Blog: <title>`, push, and open a
PR with a one-paragraph description of the topic and target search intent.
The PR is the audit trail and revert point, not a review gate: if its diff
is only the post plus its sync files, squash-merge it yourself
(`gh pr merge --squash --delete-branch`) - Byron authorized unattended
merges for post-only PRs (2026-07-17). If the diff touches anything else
(workflow, skill, app code), leave the PR open for review instead.

After merging from the GitHub Actions run, dispatch the site deploy with
`gh workflow run pages.yml`: pushes made with `GITHUB_TOKEN` do not trigger
it on their own. A merge done interactively (a human's `gh` auth) triggers
it automatically. In the Actions run, `gh` is already authenticated via
`GITHUB_TOKEN`.
