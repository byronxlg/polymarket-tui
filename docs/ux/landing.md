# Landing page: brief, states, paths

## Brief

Who lands here and from where: someone who trades on Polymarket and works in a terminal, from the
GitHub README, a search result, or a link in a chat. On a phone as often as on a laptop.

What they already know: Polymarket, order books, YES and NO, limit orders, `uv` and `brew`.

The one thing they do: copy an install line.

What they must learn at this moment: it is real (a recording of a real session), it will not
spend money by accident (starts in DRY), and how to install it.

Word budget: 220 words on the page, footer included (646 today).

## Where each piece of text lives

| Text | Why this reader needs it | Home |
|------|--------------------------|------|
| Name, one-line description | to confirm they are in the right place | first screen |
| Version, platforms, Python version | to know it runs on their machine before copying | above the heading |
| Install line and its three alternatives | the one action | first screen, one line, tabs for the alternatives |
| Recording | proof it is real | first screen or directly under it |
| DRY / LIVE | the one fear: spending by accident | next to the order still, where the fear arises |
| No account to browse | removes the last reason not to install | with DRY / LIVE |
| Keys | what "all keyboard" means in practice | one compact table after the proof |
| Unofficial, real money in LIVE, what it cannot do | legal and honest | footer |
| Blog | not needed to install; posts stopped 2026-10-03 | one footer link |

Dropped: the paragraph describing the video, the numbered section labels, the feature
paragraphs (the stills show them), the API host list (it is in the README).

## Control states

| Control | Rest | Pressed | Busy | Done | Failed | Disabled |
|---------|------|---------|------|------|--------|----------|
| Copy button (Primer IconButton + copy feedback) | copy icon, muted | scales to 0.97, darker fill | none: the clipboard write is instant | check icon in success green and the label "Copied" for 2s, announced to screen readers, then back to rest | the command text is selected so a manual copy works; label "Select and copy" | never |
| Install tabs (Primer SegmentedControl): uv, Homebrew, Script, Source | one selected, filled | darker fill | none | selection moves, command line swaps, Copy returns to rest | n/a (no network) | never |
| GitHub link, footer links | link colour | Primer pressed colour | browser's own | new page | browser's own | never |
| Recording | plays muted, looped, no native controls; a Pause button under it | Pause button pressed state | poster still shown until the first frame | playing | poster still stays, no broken-video box | with reduced motion: paused on the poster, button reads Play |

## Paths

A static page: no forms, no multi-step flow. The paths that need a test each:

| From | Action | Result |
|------|--------|--------|
| First screen | tap Copy | install line on the clipboard, "Copied" shown, back to rest after 2s |
| First screen | tap Copy twice quickly | one "Copied", timer restarts, no flicker |
| First screen | tap another install tab | that command shown on one line (scrolls sideways inside its box if longer), Copy at rest |
| "Copied" showing | tap another tab | Copy returns to rest at once |
| Clipboard refused | tap Copy | command selected, "Select and copy" |
| Any | reload or back | the uv tab selected, video from the start |
| Slow network | open page | text and install line usable before the video arrives; poster holds the space, no layout jump |
| Reduced motion | open page | video paused on the poster, Play button |
| Deep link `#install` (old links) | open | lands on the install line |
