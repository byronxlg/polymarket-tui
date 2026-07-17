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
| `docs/blog-todo.md` | move the topic from Queue to Shipped, with date and path |

## 1. Pick the topic

Take the **topmost unchecked topic** in `docs/blog-todo.md`. The queue is
ordered by value, so do not cherry-pick lower entries. If the queue is empty,
first refill it: add 5 new topics that target real search intent (what would
someone type into Google that this post answers?), then take the first.

## 2. Get the facts right

Posts are educational first, product second - that is what earns search
traffic and trust. Every claim about how Polymarket works must be verifiable:

- Exchange mechanics (ticks, order types, minimums, resolution) are pinned in
  `docs/trading.md` and `docs/api-reference.md`. Read the relevant section
  before writing; never write market mechanics from memory.
- For anything not covered there, probe the live APIs with curl
  (gamma-api.polymarket.com, clob.polymarket.com, data-api.polymarket.com)
  and describe what you observed.
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
  restructure). Prices in cents ("33c"). Explain jargon on first use.
- One `<pre>` example rendering something terminal-shaped is on-brand and
  breaks up the text; use the `.g`/`.r`/`.c` spans for green/red/faint.
- polymarket-tui appears where it is genuinely the answer (usually the final
  numbered section plus the install CTA), never as the opening pitch.
- End the disclaimer line in `post-foot`: not affiliated with Polymarket, not
  financial advice.

## 4. Sync the five files

- `site/blog/index.html`: new `post-row` at the **top** of `.post-list`
  (date, dots, title).
- `site/index.html`: same row shape at the top of the `#blog` section's
  `.posts`; delete the oldest row if there are now more than 3.
- `site/blog/feed.xml`: new `<item>` first, `pubDate` in RFC 822 format
  (`Fri, 17 Jul 2026 09:00:00 +0000`), `guid` = the canonical URL.
- `site/sitemap.xml`: new `<url>` with `<loc>` and `<lastmod>` (YYYY-MM-DD).
- `docs/blog-todo.md`: check the topic off, move it to Shipped with the date
  and file path.

## 5. Verify before shipping

- Serve the site and click through: `python3 -m http.server -d site 8000`,
  then check `/blog/`, the new post, and the landing `#blog` section render
  and cross-link correctly. In a headless run, at minimum fetch each page
  with curl and confirm 200s and that the new links appear where expected.
- Grep the new slug across `site/` - it must appear in the post file name,
  blog index, landing page, feed, and sitemap. Same spelling everywhere.
- Confirm the date is today's real date in all five places (page, feed,
  sitemap, todo, JSON-LD).

## 6. Ship

Branch `blog/<slug>`, commit everything as `Blog: <title>`, push, and open a
PR with a one-paragraph description of the topic and target search intent.
Do not merge; a human reviews every post. In the GitHub Actions run, `gh` is
already authenticated via `GITHUB_TOKEN`.
