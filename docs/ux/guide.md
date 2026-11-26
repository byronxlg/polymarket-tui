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
| Ink | fgColor-default | #f0f6fc | 17.6:1 |
| Muted ink | fgColor-muted | #9198a1 | 6.6:1 |
| Border | borderColor-default | #3d444d | - |
| Action (primary button) | bgColor-success-emphasis | #238636, white label | 4.6:1 label |
| Link | fgColor-accent | #4493f8 | 6.2:1 |
| Done | fgColor-success | #3fb950 | 7.4:1 |
| DRY (attention) | fgColor-attention | #d29922 | 7.6:1 |
| LIVE (danger) | fgColor-danger | #f85149 | 5.7:1 |

Contrast figures are to be re-measured in the build check, not trusted from this table.

## Type

Mona Sans (Primer Brand's face, OFL, vendored like Plex is today) for text; the platform
monospace stack for commands and keys. Scale: 40/44 heading 700, 24/30 section heading 600,
18/26 lead, 16/24 body, 13/18 meta. Two weights carry hierarchy: 700/600 for headings, 400 for
the rest. IBM Plex Mono is retired from the page; the recording keeps the terminal look.

## Space, shape, depth, motion

- Spacing on Primer's 4px base: 4, 8, 12, 16, 24, 32, 48, 64. Side gutter 16 on a phone.
- Radius 6 (controls, boxes), 12 (the recording). No shadows on a dark ground: borders only.
- Motion: press scales to 0.97 over 100ms; the copy icon swaps to the check with a 150ms
  fade; tab change swaps the command with no slide. All off under reduced motion.
- Touch targets at least 44px.

## Element to pattern

| Element | Primer pattern |
|---------|----------------|
| Top bar | Primer Brand SubdomainNavBar, reduced to name and one link |
| First screen | Primer Brand Hero: label, heading, description, action, media |
| Install line | Primer copy-to-clipboard: monospace text in a bordered box, IconButton that confirms with a check |
| Install alternatives | SegmentedControl |
| Stills with captions | Primer Brand River |
| Keys | Primer DataTable (two columns) with `kbd` keys |
| DRY / LIVE | Primer Label (attention, danger variants) |
| Footer | Primer Brand MinimalFooter |

## Banned

Numbered section labels on content that is not a sequence, blinking cursors and prompt
decorations in headings, prose that describes the page or the video, uppercase letter-spaced
labels, more than one accent colour per screen, text over the recording, native video controls
over the picture, cards around every block.
