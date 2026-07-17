# Marketing log

Every outbound marketing message, newest first. Strategy and rules:
`marketing.md`. Format per entry: timestamp (UTC), channel, where, link,
full text as sent, notes.

<!-- entries below, newest first -->

## 2026-07-17 21:45 UTC - Polymarket - World Cup final thread - DRAFTED, not sent

Target: comments on polymarket.com/event/fifwc-esp-arg-2026-07-19 (the
Spain vs Argentina final). Blocked: posting uses Byron's browser session
and the Claude Chrome extension is not connected. Draft, ready to post
as-is (numbers to be re-checked against the live book at post time):

> Structure note for anyone reading both boards: Spain is ~59c to lift the
> trophy but only ~42c to win the match - the gap is the draw (31c),
> because the match market only counts the first 90 minutes. Champion
> minus 90-minute price is ~16c of that 31c draw scenario, so the market
> has a final that goes past regulation as roughly a coin flip leaning
> Spain. Full breakdown with charts:
> https://polymarket-tui.botsmith.dev/blog/spain-vs-argentina-2026-world-cup-final-odds.html
> (I build a terminal client for Polymarket; link at the end of the post.)

## 2026-07-17 21:39 UTC - Moltbook - account registered, pending claim

Registered agent `pmtui` (201). API key in
`~/.config/moltbook/credentials.json` (0600, not in repo). Claim link and
verification code sent to Byron via Telegram; no posts possible until
claimed. Note: a first registration attempt as `polymarket-tui` succeeded
but its API key was lost to a response-parsing crash, so that name is now
squatted by an orphan registration - if Moltbook support can release it,
we can rename later. No messages sent on this channel yet.
