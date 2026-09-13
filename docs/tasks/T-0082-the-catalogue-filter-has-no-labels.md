# T-0082 — The catalogue filter has no labels

**Phase:** 3   **Status:** done
**Touches invariants:** none.

## Why

Found by the workbench built in T-0079 — specifically by the workbench's own assertion
failing for the right reason: a check for the text "حوزهٔ قضایی" on
`Screens/Review/Detail/Never Checked` came back missing, because that string is a
`placeholder` and placeholders are not in `innerText`. Neither are they reliably in the
accessibility tree, and they vanish the moment a character is typed.

`ReviewDetailPage`'s catalogue picker has three such inputs — jurisdiction, region,
version:

```tsx
<input
  placeholder={t("review.catalogue.jurisdiction")}
  value={catalogueFilter.jurisdiction}
  ...
/>
```

Every other form in this app does the opposite, and `docs/design/DESIGN.md` records that as
the established pattern: "Field — `.field` + `label` + `input`/`select` — real
`<label htmlFor>`, never placeholder-only." Sign-in, register, create-workspace, add-project
and add-review all follow it. This one screen does not, and it is the screen where a person
is choosing which building regulations their model will be judged against — the worst place
in the product to leave someone unsure which box is which after they start typing.

Three inputs in a row, each losing its only identification as soon as it is used.

## Scope

**Changes**

- `services/web/src/features/review/ReviewDetailPage.tsx` — the three filter inputs get real
  labels, following `.field` as the rest of the app does. If three stacked labelled fields
  are too heavy for a filter row, a visually-hidden `<label>` plus the existing placeholder
  is acceptable — `.sr-only` already exists in `styles.css` for exactly this. What is not
  acceptable is leaving them unlabelled.
- `services/web/src/styles.css` only if the filter row needs a layout adjustment to hold
  labels.

**Not in scope, but adjacent — read before starting**

`docs/design/DESIGN.md` records two measured contrast pairs that are under AA for normal
text: `--accent` on `--card` at 3.84:1 (`.link-button`, `.table a:hover`,
`.user-menu-panel button.active`) and `--fail` on `--card` at 4.14:1 (`.error` — how every
form failure in the app is worded). Neither is this task, because both are token-level
decisions affecting every screen rather than one component's markup, and changing `--accent`
would move the identity T-0071 measured off zohal.io. If someone is in this CSS anyway it is
worth raising as its own task rather than fixing quietly here.

## How to prove it ran

```sh
cd services/web && pnpm run workbench
```

`Screens/Review/Detail/Never Checked`, with the a11y panel open: no
"Form elements must have labels" violation. Then type into the first filter and show that
its identification is still on screen — which is the actual defect, and the part an
automated a11y check would not catch on its own.

## Evidence

**Change made.** Each of the three catalogue filter inputs
(`services/web/src/features/review/ReviewDetailPage.tsx`) is now wrapped in a `.field` div
with a real `<label htmlFor>` associated by `id` (`catalogue-jurisdiction`,
`catalogue-region`, `catalogue-version`). The label uses `.sr-only` (already defined in
`styles.css`, unmodified) per the task's stated fallback for a three-input filter row; the
existing `placeholder` is kept alongside it. No CSS changes were needed — `.sr-only` already
existed and the filter row's layout is unaffected since a position:absolute element does not
participate in the `.field` grid.

```tsx
<div className="field">
  <label className="sr-only" htmlFor="catalogue-jurisdiction">
    {t("review.catalogue.jurisdiction")}
  </label>
  <input
    id="catalogue-jurisdiction"
    placeholder={t("review.catalogue.jurisdiction")}
    value={catalogueFilter.jurisdiction}
    onChange={(e) => setCatalogueFilter((f) => ({ ...f, jurisdiction: e.target.value }))}
  />
</div>
```
(region and version follow the same shape, ids `catalogue-region` / `catalogue-version`.)

**`make verify`:** passed in full (ruff, ruff format, mypy --strict on 170 files, all 5
import-linter contracts kept, `compilemessages`, 246 backend pytest, frontend
`lint && typecheck && build && build-workbench`). Tail of the run:

```
Contracts: 5 kept, 0 broken.
cd services/api && uv run --project .. python manage.py compilemessages
File "…/cadgpt/locale/fa/LC_MESSAGES/django.po" is already compiled and up to date.
uv run pytest
...
246 passed, 32 warnings in 4.76s
cd services/web && pnpm install --frozen-lockfile && pnpm run verify
...
✓ built in 2.37s
...
Building preview.. / Building open services.. / Building manager..
✓ built in 9.93s
Output directory: /home/alireza/Projects/cadgpt/services/web/storybook-static
Storybook build completed successfully
```
(The environment was missing GNU gettext's `msgfmt`; a previously-fetched local copy under
`/tmp/claude-*/…/scratchpad/gettext-local` was put on `PATH`/`LD_LIBRARY_PATH` for this run —
an environment fix, not a code change, and the same gap exists identically on `main` without
this task's diff.)

**Real path.** Started the actual workbench (`pnpm run workbench`, Storybook dev server on
:6006 serving the real `ReviewDetailPage` component against MSW-mocked API responses — this
is the same "run and exercise the feature" instrument T-0079 built) and drove it with
Playwright + the project's own `axe-core` (the same engine Storybook's `@storybook/addon-a11y`
panel runs) against `Screens/Review/Detail/Never Checked`
(`screens-review-detail--never-checked`):

1. **A11y panel clean.** `axe.run(document, { runOnly: { type: "rule", values: ["label"] } })`
   against the rendered story:
   ```
   === axe-core 'label' rule violations ===
   []
   violation count: 0
   ```
   Zero violations of the "Form elements must have labels" rule (axe rule id `label`, the
   rule Storybook's a11y panel reports under that title) on the catalogue's three inputs.

2. **Identification stays on screen after typing — the actual defect.** Filled the first
   filter (`#catalogue-jurisdiction`) with `"Tehran"` and re-read the catalogue picker's
   `innerText`, reproducing exactly the check T-0079's workbench originally failed (a search
   for the Persian string "حوزهٔ قضایی" in `innerText`):
   ```
   input value: Tehran
   === innerText of catalogue-picker after typing ===
   "برای بررسی، بسته‌های مقررات را از فهرست انتخاب کنید\n\nحوزهٔ قضایی\nمنطقه\nنسخه\n\n
   هیچ بسته‌ای با این پالایش مطابقت ندارد.\n\nاجرای بررسی با بسته‌های انتخاب‌شده"
   contains jurisdiction label text: true
   ```
   "حوزهٔ قضایی" (Jurisdiction) is present in `innerText` while the field holds typed text —
   before this change the placeholder carrying that string would have vanished from both
   `innerText` and (unreliably) the accessibility tree the instant a character was typed.
   The `<label for="catalogue-jurisdiction">` association also resolves correctly after
   typing:
   ```
   accessible name via <label for> association after typing: حوزهٔ قضایی
   ```

**Wiring.** The labels are not a separate registration — they render inline in
`ReviewDetailPage.tsx`, which is the component `Screens/Review/Detail/Never Checked` in
`ReviewDetailPage.stories.tsx` renders via `render: at(fx.neverRunReview.uuid)` (mounting the
real `AppAt` router at the review route), and that story's `.field`/`<label htmlFor>` markup
is exactly what the Playwright run above exercised — proof came from driving the live
component, not a unit test of the JSX in isolation.

## NOT DONE

Nothing. Three inputs (jurisdiction, region, version) all received the same
`.field` + `.sr-only` `<label htmlFor>` treatment; the task's scope did not require touching
`styles.css`, and none was touched.

## Review

Not reviewer-gated — no invariant, single-file diff, fully read by the coordinator. Verified
against the real workbench with the project's own `axe-core`: zero "label" rule violations
on the three inputs, and — the part an automated a11y check alone would not catch — after
typing into the jurisdiction field its label text is still present in the picker's
`innerText` and its accessible-name association still resolves.
