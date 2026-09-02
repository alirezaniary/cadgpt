# T-0044 — Seeding real packs: a manifest, and knowing when the catalogue diverges from disk

**Phase:** 3 — What the first real user needs   **Status:** open
**Touches invariants:** none. Sequence this **when the first real pack is authored**, not before.

## Why

Found by the T-0030 review. Both halves are consequences of T-0030 having been correct: it was
forbidden to author rule content, so it seeded three of the repository's own fixtures under
`jurisdiction="sample"`, and it was required not to overwrite a pack a completed run cites.

**The manifest is hardcoded Python.**
`management/commands/seed_rule_packs.py:53-62` holds three fixture filenames,
`jurisdiction="sample"`, `version="0.1"`, and the command takes no arguments. Correct for
T-0030. But the product owner adding the Iranian building code pack — *the* next step for this
part of the product (`docs/plan.md`) — would have to edit Python and rebuild the image to do it.

**And a changed source file is skipped silently.** The reviewer verified both branches. Editing
`door_width.ids` from 900 to 1800 mm while keeping its title and re-seeding gives
`created=False`, the same row, **unchanged stored bytes and unchanged citation** — so T-0030's
requirement that it never "silently overwrite a pack a run already cites" is genuinely satisfied,
and that behaviour must not be traded away. The flip side is that nothing tells anyone the
catalogue has diverged from what is on disk.

Changing the *title* instead produces a **second row at the same `(sample, "", 0.1)` identity** —
"Accessible door width" and "Accessible door width v2" — because `name` is part of the key.

## Scope

- A `--manifest` or `--path` argument, or a manifest file the command reads, so a pack can be
  added without editing Python or rebuilding an image.
- A **divergence report**: when a pack's source file on disk differs from the stored bytes, say
  so rather than skipping silently. A checksum on the stored file is the obvious mechanism.
  Report it; do not auto-update — the skip is the correct behaviour and this task only makes it
  legible.
- Decide what a *revision* of a pack is, given that `name` is part of the identity key: a new
  version of the same pack, or a different pack. Say which in the evidence, because the answer
  determines whether "Accessible door width v2" is a bug or the intended way to revise.

**Does not change:** the skip-rather-than-overwrite guarantee. A completed `CheckRun` must stay
explainable, which means the bytes it cited must stay as they were.

**Note:** the divergence-and-revision half may properly belong with ratification in Phase 4
(`prd.md` §5.5). If, when this is picked up, it reads as a ratification concern rather than a
seeding one, say so and move it rather than building a half of it here.

## How to prove it ran

`make verify`, then the real path: seed from a manifest the command did not ship with, and show a
pack whose file changed on disk being **reported** as diverged rather than skipped silently.
Paste both runs.

## Evidence

<!-- the builder writes this -->

## Review
