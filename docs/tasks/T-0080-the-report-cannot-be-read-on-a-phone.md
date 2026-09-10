# T-0080 — The report cannot be read on a phone

**Phase:** 3   **Status:** built
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

## Evidence

### What changed and why (the real cause was two bugs, not one)

`services/web/src/components/ReportView.tsx` — the entity `<table className="entities">`
is now wrapped in `<div className="entities-scroll">`, so the *table* scrolls horizontally
rather than the page.

`services/web/src/styles.css` — two rules, not one:

1. `.entities-scroll { overflow-x: auto; max-inline-size: 100%; }` next to `.entities` —
   the direction the task named second ("give the table its own `overflow-x: auto`
   container").
2. `.report, .specs, .spec { min-inline-size: 0; }` — required for (1) to actually work.
   `.report` and `.specs` are CSS Grid containers (a single implicit `auto` column) and
   `.spec` is a grid item of `.specs`; a grid item's automatic minimum size defaults to its
   content's min-content. Without this, the entity table's fixed-column floor sized each of
   these tracks in turn — `.report`/`.specs`/`.spec` themselves grew past `.page`'s width
   and the *page* overflowed before `.entities-scroll`'s own `overflow-x: auto` ever had a
   narrower box to clip against. Measured directly: with only fix (1) in place, overflow at
   390px was **358px** (worse than the bug's original 318px, because `.report`, `.specs`
   and `.spec` were all still growing to the table's content width). Adding `min-inline-size:
   0` to those three grid-participating selectors is what actually contains it — confirmed
   below. `table-layout: fixed` and every column width from T-0074 are untouched; no column
   is hidden.

`.counts` was not touched — it was not a source of overflow. `getBoundingClientRect`/
`scrollWidth` measurement at 390px (below) shows all three `.count` tiles laid out on one
row (`repeat(3, minmax(0, 1fr))` already shrinks correctly; `minmax(0, ...)` was already
doing its job) and `document.querySelectorAll(".count").length === 3` at every width in
every direction.

### `make verify`

Blocked initially by a pre-existing environment gap unrelated to this task: `msgfmt`
(GNU gettext, needed by `compile-messages` → `test`) was not installed and `apt-get
install` requires root, which this sandbox does not have. A `gettext_0.21-14ubuntu2_amd64
.deb` was already sitting in the scratchpad from an earlier task's attempt at the same
problem; it was missing its two runtime shared libraries (`libgettextlib-0.21.so`,
`libgettextsrc-0.21.so`), which the same `.deb` also ships but had not been extracted.
Extracting them and pointing `PATH`/`LD_LIBRARY_PATH` at the extracted tree (no root, no
change to the repo or its config) made `msgfmt` work and unblocked the gate. This is an
environment-provisioning fix, not a code change — no file in the repository was touched to
achieve it.

```
$ make verify
...
uv run ruff check .
All checks passed!
uv run ruff format --check .
187 files already formatted
uv run mypy packages/engine/src services/api/cadgpt
Success: no issues found in 170 source files
uv run lint-imports --no-cache
...
Contracts: 5 kept, 0 broken.
cd services/api && uv run --project .. python manage.py compilemessages
...
246 passed, 32 warnings in 4.79s
cd services/web && pnpm install --frozen-lockfile && pnpm run verify
...
✓ 206 modules transformed. (app build)
✓ 489 modules transformed. (workbench build)
Storybook build completed successfully
$ echo $?
0
```

Full log: exit 0. The 32 warnings are the pre-existing `ifcopenshell` `ResourceWarning`s in
the engine/API suites (`file.__del__` / `KeyError` during garbage collection), unrelated to
this task and present before this change.

### Real path — the actual measurement that found the bug, repeated

Built the static workbench export and served it, exactly as the task specifies, then drove
the real `Screens/Review/Detail/Checked` story (fixture data through the app's own render
path, same story T-0079 used to find the original 318px) in a real Chromium instance at
390 / 768 / 1280px, in both `en` (ltr) and `fa` (rtl) — the workbench's language toolbar
drives direction off locale (`fa` → rtl is the shipped default, `en` → ltr is the fallback).

```sh
cd services/web && pnpm run build-workbench
python3 -m http.server 6099 -d storybook-static &
# ephemeral playwright spec driving http://127.0.0.1:6099/iframe.html?id=screens-review-detail--checked,
# written for this task and deleted afterward — not part of the committed suite, the same
# way T-0079's own verify-workbench.mjs was never committed either
npx playwright test e2e/_overflow-check.spec.ts --reporter=list
```

```
Running 6 tests using 1 worker

dir=ltr width= 390px  overflow=   0  counts=3  entities-table-scrolls-internally=true  (document dir attr=ltr)
  ✓  overflow dir=ltr width=390 (2.0s)
dir=ltr width= 768px  overflow=   0  counts=3  entities-table-scrolls-internally=false (document dir attr=ltr)
  ✓  overflow dir=ltr width=768 (1.8s)
dir=ltr width=1280px  overflow=   0  counts=3  entities-table-scrolls-internally=false (document dir attr=ltr)
  ✓  overflow dir=ltr width=1280 (1.8s)
dir=rtl width= 390px  overflow=   0  counts=3  entities-table-scrolls-internally=true  (document dir attr=rtl)
  ✓  overflow dir=rtl width=390 (2.1s)
dir=rtl width= 768px  overflow=   0  counts=3  entities-table-scrolls-internally=false (document dir attr=rtl)
  ✓  overflow dir=rtl width=768 (2.2s)
dir=rtl width=1280px  overflow=   0  counts=3  entities-table-scrolls-internally=false (document dir attr=rtl)
  ✓  overflow dir=rtl width=1280 (1.8s)

6 passed (12.8s)
```

`overflow` is `document.documentElement.scrollWidth - document.documentElement.clientWidth`,
measured after the real report renders (`.entities` present in the DOM) — the same
definition the bug report used, where 390px originally measured `+318`. At every width, in
both directions, it is now `0` (well inside the `<= 2` bar the task set). At 390px the
entity table scrolls internally (`.entities-scroll`'s `scrollWidth` > its `clientWidth`);
at 768px and 1280px it does not need to — the table fits and lays out exactly as before.
`counts=3` at every measurement: the three count tiles (pass/fail/indeterminate) are never
fewer than three, confirmed by `document.querySelectorAll(".count").length`.

Before the fix, on the same story, same measurement: `overflow=318` at 390px (matching the
bug report exactly, confirming the harness measures what the task describes) — offending
element identified directly (`scrollWidth > clientWidth`): `<table class="entities">` at
`clientWidth: 600` (the T-0074 fixed-column sum) vs `scrollWidth: 619`, with `.requirement`,
`.spec` and `.specs` all forced to the same ~600–635px width above it — exactly the
mechanism the task's Why section describes.

Screenshots at 390px (full report, `dir=ltr` and `dir=rtl`) and a crop of the entities
table showing the first column (status/class/GlobalId) in view with reason/detail scrolled
just out of the clipped box — confirming reflow-by-scroll, not truncation — were captured
during this run and are not committed (ephemeral verification artifacts, not part of the
repository).

### Wiring

This is a pure CSS/markup fix — there is no task, route or migration to register — so
"wiring" here means: the class lives on the element that actually renders in production,
and the stylesheet carrying the fix is the one the app actually loads.

`services/web/src/components/ReportView.tsx` (the component every review's report renders
through — `ReviewDetailPage.tsx:291`, `<ReportView report={currentReport}
rulePackSelection={run.data?.rule_pack_selection ?? []} />`):

```tsx
<div className="entities-scroll">
  <table className="entities">
```

`services/web/src/main.tsx:9` — the stylesheet carrying every rule above is the one the
whole app loads, not a story-only or test-only copy:

```ts
import "@/styles.css";
```

### NOT DONE

Nothing in this task's scope is left undone. `.counts` was investigated and left
unchanged — it was never a source of overflow at any measured width (see above), and the
task made touching it conditional ("only if it can be done without ever rendering fewer
than three tiles"); since it needed no change, none was made.
