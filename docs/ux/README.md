# Landing page redesign: decisions

The owner decides; each answer is recorded here verbatim with its date, then what it means for
the build. Order is big to small. Nothing goes live without a yes in words.

Page: https://polymarket-tui.botsmith.dev/ (`site/index.html`).

| # | Decision | Status |
|---|----------|--------|
| 1 | Who the page is for and what they want | set |
| 2 | Which published design system it follows | set |
| 3 | The page itself: two different directions built with real content (what stays, what goes, in what order); pick one | set |
| 4 | Blog pages take the same colours and type (small, batched: not asked) | proposed |
| 5 | Try the built page on a phone: yes, or what feels wrong | proposed |
| 6 | Go live | proposed |

## As now (2026-11-26, WebKit, 390px wide)

- 6015px tall (about 7 screens), 646 words, one type weight, mostly grey.
- The install command is about 6 screens down and wraps mid-word.
- The video's native controls sit on top of the picture.
- A paragraph under the video explains the video.
- The blog strip shows three posts from early October 2026; the daily post stopped 2026-10-03.

## 1. Who the page is for

Options sent 2026-11-26:

- A. Someone who already trades on Polymarket and works in a terminal. They want to see it is
  real and copy one install line; they know they got it when the app is running.
- B. A terminal tinkerer from GitHub or Hacker News who has never used Polymarket.
- C. A casual Polymarket user who has never opened a terminal.

Answer (Byron, 2026-11-26, Claude Code session): "A"

What it means for the build:

- The reader knows Polymarket, order books, YES/NO and limit orders. The page does not explain
  them.
- The reader knows a terminal, `brew` and `uv`. The page does not explain installing.
- The one thing they do here is copy an install line. It belongs on the first screen, at phone
  width, on one line.
- The proof it is real is the recording of a real session, not prose about it.
- Every other section is judged by whether it gets this person to a running app sooner or
  more surely.

## 2. Design system

Shown 2026-11-26 as one picture: the first screen at 390px as now and in GitHub Primer, IBM
Carbon and Vercel Geist (same words, same recording). The first ask was three text descriptions;
Byron: "When asking for visual decisions youre gonna need to show me".

Answer (Byron, 2026-11-26, Claude Code session): "A" (GitHub Primer)

What it means for the build: `guide.md` maps every element on the page to a named Primer
pattern, with its states and Primer's writing rules. Nothing on the page is styled by taste; an
element with no Primer pattern is raised as a question, not invented.

Plan documents: `landing.md` (brief, control states, paths), `guide.md` (tokens and patterns),
`words.md` (every word the page may show).

## 3. The page

Shown 2026-11-26 as whole-page WebKit captures at 390px: as now (7 screens, 646 words), A short
(2 screens, 112 words: install line, recording, safety lines, keys), B tour (3.5 screens, 119
words: recording first, four stills, keys, install line top and bottom). My pick was A.

Answer (Byron, 2026-11-26, Claude Code session): "B"

What it means for the build: the recording opens the page edge to edge; heading, facts and the
install box follow on the first screen; then Order book, Order review (with the DRY, LIVE and
no-account lines), Price chart and Search as large stills from the real session; then Keys; then
the install box again; then the footer. Built at `site/next/` first so it can be tried on a
phone beside the live page.
