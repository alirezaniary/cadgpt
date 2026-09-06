# T-0082 — The catalogue filter has no labels

**Phase:** 3   **Status:** open
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
