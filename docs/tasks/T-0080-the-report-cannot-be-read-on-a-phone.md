# T-0080 — The report cannot be read on a phone

**Phase:** 3   **Status:** open
**Touches invariants:** none directly. But see "What must not change" — the fix must not
reach for `display: none` on a column, because hiding a finding's status or reason is a
three-valued problem wearing a layout costume.

## Why

Found by the workbench built in T-0079, on its first run — measured, not eyeballed:

```
--- responsive: the report at three widths ---
      1280px  no horizontal overflow
       768px  no horizontal overflow
       390px  HORIZONTAL OVERFLOW (+318px)
```

At a 390px viewport, `Screens/Review/Detail/Checked` pushes 318 pixels off the side of the
page. The whole document scrolls sideways, so the disclosure, the coverage line and the
counts all drift out of view while reading a findings table.

`services/web/src/styles.css` contains no `@media` query at all — this was noted as
intrinsic-until-proven in `docs/design/DESIGN.md` and is now proven otherwise. Two things
are responsible:

- `.entities` is `table-layout: fixed` with explicit per-column widths on children 1–4
  (`5.5rem + 8rem + 13rem + 11rem` = 37.5rem ≈ 600px) plus an `auto` fifth column. A fixed
  layout does not shrink those; below ~640px the table is simply wider than the viewport.
- `.counts` is `repeat(3, minmax(0, 1fr))` and never collapses, so at 390px the three count
  tiles are ~110px each and `--text-2xl` values start to crowd their labels.

The first market reads this product on a Persian right-to-left layout, where a horizontal
overflow pushes content off the *left* edge — the direction a reader's eye does not chase.

## Scope

**Changes**

- `services/web/src/styles.css`. The report's entity table must stay readable below 640px.
  Preferred direction, in order: let `.entities` fall back to `table-layout: auto` with
  `min-inline-size` guards under a narrow breakpoint; or give the table its own
  `overflow-x: auto` container so the *table* scrolls while the page does not. Whichever is
  chosen, the page itself must not scroll horizontally.
- `.counts` collapsing below three columns at narrow widths is in scope **only if** it can
  be done without ever rendering fewer than three tiles.

**What must not change**

- All three counts stay visible at every width. Collapsing to a two-column grid is fine;
  dropping the indeterminate tile, or moving it behind a toggle, is not — it is the
  product's whole value-add and this is exactly the kind of quiet layout decision that
  would erase it.
- No entity column may be hidden. A finding's status, class, GlobalId, reason and detail are
  each load-bearing; if one must give, it wraps, it does not disappear.

**Not in scope**

- Any other screen's responsive behaviour. The changelist and the forms measured clean at
  390px in the same run and are not touched here.

## How to prove it ran

The measurement that found it, repeated, plus a human look:

```sh
cd services/web && pnpm run build-workbench
python3 -m http.server 6099 -d storybook-static &
# then, at 390 / 768 / 1280:
#   scrollWidth - clientWidth on documentElement must be <= 2 at every width
```

Evidence must show the number at all three widths, in both `dir=rtl` and `dir=ltr` (the
workbench's language toolbar switches direction), and state whether the entity table
scrolls internally or reflows. A screenshot at 390px is worth pasting, but the overflow
number is the claim.
