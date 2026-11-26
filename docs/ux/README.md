# Landing page redesign: decisions

The owner decides; each answer is recorded here verbatim with its date, then what it means for
the build. Order is big to small. Nothing goes live without a yes in words.

Page: https://polymarket-tui.botsmith.dev/ (`site/index.html`).

| # | Decision | Status |
|---|----------|--------|
| 1 | Who the page is for and what they want | set |
| 2 | Which published design system it follows | sent |
| 3 | The path from landing to installed: what stays on the page, what goes | proposed |
| 4 | Whether the blog pages are in this pass | proposed |
| 5 | Two different directions built with real content; pick one | proposed |
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
