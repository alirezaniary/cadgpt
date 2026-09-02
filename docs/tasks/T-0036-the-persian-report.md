# T-0036 — The Persian report: prove RTL, and stop rendering a raw payload value

**Phase:** 3 — What the first real user needs   **Status:** open
**Touches invariants:** none. **Every user-facing string goes through `gettext`** is a rule in
`CLAUDE.md`, and this task closes the last place the report view breaks it.

## Why

Found by the T-0025 review (Q5, Q6). The frontend is described as RTL-native and the review
confirmed the mechanics are genuinely right — the new CSS uses logical properties throughout
(`padding-block-end`, `border-block-end`, `padding-inline-start`), `grep` finds no physical
`left`/`right` anywhere in `styles.css`, and the two catalogues are at exact parity: 51 keys in
each, zero orphans in either direction.

What is missing is that **nothing ever renders the app under `fa`.** RTL is a claim the test
suite does not make. The e2e harness cannot make it as written either: its selectors are
English by construction — `getByRole("checkbox", { name: "Indeterminate" })` — so the harness
would have to be taught the locale before it could assert anything about it.

And one string escapes the catalogues. `ReportView.tsx:152` renders `{spec.cardinality}` — the
raw `required` / `prohibited` / `optional` value straight from `ifctester`'s `get_usage()` — as
user-facing text. Pre-existing rather than introduced by T-0025, but it is an English word on a
Persian page, in the line that says what a rule demands.

## Scope

**Changes** — `services/web/src/components/ReportView.tsx`, both i18n catalogues,
`services/web/e2e/report.spec.ts` (or a component test, if that is the honest instrument).

1. `cardinality` renders through `t()` with a key per value. It is a closed vocabulary of
   three; enumerate them rather than interpolating the raw value into a template.
2. One rendering of the report under `fa` that actually asserts something: that the document
   direction is RTL, that the coverage and filter blocks lay out rather than overflow, and that
   no untranslated key or raw English value appears in the report body. If the e2e harness is
   the instrument, it needs locale-independent selectors — `data-testid` already exists on the
   rows and should be extended to the controls rather than matching on English labels.

**Does not change:** the engine's `cardinality` value on the wire — it stays the machine token;
only its rendering is localized. No new locale is added; `fa` already exists.

## How to prove it ran

`make verify`, then `make up` (rebuild `web`) and `make e2e` with the `fa` assertion in it,
stdout pasted, and a screenshot of the report under `fa` which you must open and describe —
specifically whether the coverage block, the count tiles and the filter read correctly
right-to-left, and whether any English survives in the report body.

## Evidence

<!-- the builder writes this -->

## Review
