# Cold reads of the landing page words

A fresh agent is told only what the reader knows (trades on Polymarket, works in a terminal,
has never heard of polymarket-tui, opened the link on a phone) and is given the page's words in
order. It quotes every word it cannot explain. Repeat until none. `words.md` cannot change
without a new row here: `tests/test_site_words.py` compares the last hash in this table with the
file (first 16 hex characters of its SHA-256).

| Date | words.md | Unexplained | What changed after |
|------|----------|-------------|--------------------|
| 2026-11-26 | - | 12 | "Python 3.12+" dropped (every install route brings its own); "signed, never sent" became the app's word "posted"; "No account" and "Account setup" became "wallet"; arrow and space keys renamed. The read also exposed a factual error carried over from the old page: LIVE is not per session, it persists (README, `core/credstore.py`). |
| 2026-11-26 | - | 4 | LIVE line reworded; space key names what it does; footer "places" became "posts". |
| 2026-11-26 | - | 2 | "after a prompt" became "asks first"; the L key row became "DRY or LIVE"; space row names the order book. |
| 2026-11-26 | - | 1 | "Starts in DRY" against "stays on after you quit": now "New installs start in DRY" and "It opens in the mode you left". |
| 2026-11-26 | bd81a08f7e2df548 | 0 | Nothing. Noted, not changed: "start in" and "opens in" both describe launching. |
