# The brand mark in a dark product

Written 2026-09-12, before the work, after two earlier passes at the same defect were
rejected. The first pass measured the problem correctly and answered it by recoloring the
asset; that answer did not survive contact with the running app. This story exists so the
third attempt is checked against a goal rather than against a contrast number.

**As a** architect at a design office being asked to upload a building model — and a whole
year of drawings — to a product I have never used, run by a company I have not heard of
**I want** the product to look like something with an owner: a real identity, presented the
way a real company presents one, on the first screen and on every screen after it
**So that** the trust question I am actually asking ("is this a serious tool, or someone's
weekend project?") is answered before I get as far as the file picker

## Why this is not a contrast ticket

The mark is two-tone: a navy (`#1B1456`) bracket pair with a blue (`#3165EB`) crosshair
threaded through it. Both tones are **figure**. It was drawn for a light ground, and the
product has none — `--bg` is `#26293f` and `--card` is `#2d3250`, both within a hair of the
mark's own navy. On those surfaces the navy half of the mark is not low-contrast, it is
*absent* (1.15:1 / 1.31:1), and the blue half is under the 3:1 floor for a graphical object
too (2.85:1 / 2.49:1). What a user sees is a blue squiggle, not a logo.

So the goal is not "raise a ratio." It is "the mark is legible as itself, everywhere it
appears, without the asset being redrawn per surface" — because an identity that needs a
different file for every background is not an identity, it is three logos.

## Acceptance criteria

- Given the sign-in screen at first load, when I look at the card, then I see a complete
  logo — both tones, whole — as the focal point of the screen, not a fragment floating in
  the dark.
- Given the app shell, when I look at the topbar, then the mark reads at small size in a
  dense row next to other controls, and sits with the wordmark as one lockup rather than as
  two unrelated items separated by the same gap as everything else in the bar.
- Given a browser tab, whether the browser's tab strip is light or dark, when I look for
  this app among a dozen open tabs, then the favicon is identifiable as this product — the
  same idea as the in-product mark, not a third variant.
- **Given any surface the mark appears on, when its colors are sampled, then they are the
  master `cadgpt-logo.svg`'s own colors** — the fix may change what the mark sits *on*, and
  must not change what the mark *is*.
- Given a person who has seen the two rejected attempts, when they look at the result, then
  the change reads as a composition decision applied consistently, not as one asset patched
  in isolation.

## Explicitly out of scope

- Redrawing the mark. It is a supplied brand asset; its geometry and its two colors are
  input to this work, not output of it.
- A light theme. The identity is one dark theme (`docs/decisions.md`, T-0071) and stays one.
- The wordmark's spelling. "CADgpt" in Latin script even in the Persian UI is settled.
- Routing/auth behaviour in the three files that render the mark. Separate, finished work.
- Marketing surfaces. There are none; this is the product only.

## Assumptions / open questions

- **Assumed:** the accent staying the mark's own blue (`--accent: #3165ea`, settled when the
  mark first appeared in-product) is still right. This story re-checks it rather than
  reopening it: if the composition ends up with the mark sitting on its own ground, the
  accent no longer has to carry the job of "making the logo look intentional," and the
  question is only whether the blue still works as a CTA color. It does — it is already
  measured at 5.21:1 for its own label.
- **Open:** whether the mark should ever appear at large size anywhere other than the auth
  cards. Today it does not, and nothing is proposed here that would add a surface.
