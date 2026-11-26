# Landing page design guide: GitHub Primer, dark

System: GitHub Primer (primer.style), dark theme. Primer Brand for page patterns (Hero, River,
MinimalFooter), Primer product for controls (Button, IconButton, SegmentedControl). Writing:
Primer's content guidelines (sentence case, no full stop on labels, name the action on the
button, no "we").

## Colour roles (Primer dark)

| Role | Token | Value | On ground contrast |
|------|-------|-------|--------------------|
| Ground | bgColor-default | #0d1117 | - |
| Inset ground (nav, footer) | bgColor-inset | #010409 | - |
| Raised (command box, table head) | bgColor-muted | #151b23 | - |
| Ink | fgColor-default | #f0f6fc | 17.4:1 (ground) |
| Muted ink | fgColor-muted | #9198a1 | 6.5:1 ground, 5.9:1 raised |
| Border | borderColor-default | #3d444d | - |
| Link, selected tab line, focus ring | fgColor-accent | #4493f8 | 6.1:1 ground, 5.6:1 raised |
| Done | fgColor-success | #3fb950 | 7.5:1 |
| Pressed fill (icon button, tab) | control-transparent-bgColor-active | Primer's value | - |
| DRY (attention) | fgColor-attention | #d29922 | 7.5:1 |
| LIVE (danger) | fgColor-danger | #f85149 | 5.7:1 ground, 5.2:1 raised |

Contrast figures are to be re-measured in the build check, not trusted from this table.

## Type

Mona Sans (Primer Brand's face, OFL, vendored like Plex is today) for text; the platform
monospace stack for commands and keys. Primer's product scale only: 40 heading, 20 section heading, 16 body,
14 meta, 12 keys. Primer's named weights only: semibold (600) for headings, normal (400) for
the rest. IBM Plex Mono is retired from the page; the recording keeps the terminal look.

## Space, shape, depth, motion

- Spacing on Primer's 4px base: 4, 8, 12, 16, 24, 32, 48, 64. Side gutter 16 on a phone.
- Radius 6 (controls, boxes), 12 (the recording). No shadows on a dark ground: borders only.
- Motion: press scales to 0.97 over 100ms (the owner's standing rule for every UI, not Primer's; it needs a touchstart listener to fire on iOS); the copy icon swaps to the check with a 150ms
  fade; tab change swaps the command with no slide. All off under reduced motion.
- Touch targets at least 44px.

## Element to pattern

| Element | Primer pattern |
|---------|----------------|
| Top bar | Primer Brand SubdomainNavBar layout only: the product's own name, one link, no GitHub mark |
| First screen | Primer Brand Hero: label, heading, description, media. The action is the install box, not a Hero button; there is no primary button on the page |
| Install line | Primer copy-to-clipboard: monospace text in a bordered box, IconButton that confirms with a check |
| Install alternatives | UnderlinePanels (Primer: a tab that changes content in place without changing the URL) |
| Stills with captions | Primer Brand River |
| Keys | a plain two-column table with `kbd` keys |
| DRY / LIVE | Primer Label (attention, danger variants) |
| Footer | Primer Brand MinimalFooter layout only: no GitHub logo, copyright or social links |

## Banned

Numbered section labels on content that is not a sequence, blinking cursors and prompt
decorations in headings, prose that describes the page or the video, uppercase letter-spaced
labels, more than one accent colour per screen, text over the recording, native video controls
over the picture, cards around every block.
