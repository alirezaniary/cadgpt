# T-0034 — The filter banner must not claim credit for what the engine capped

**Phase:** 3 — What the first real user needs   **Status:** open
**Touches invariants:** three-valued results, I7. **Reviewer-gated** — every line of this task
is a change to how a limitation is stated.

## Why

Found by the T-0025 review (Q1, Q4), not by a test. Two related ways the filtered report
understates what the reader is not seeing.

**The denominator is wrong.** `ReportView.tsx:64-67, 139` builds `allEntities` from
`r.entities`, which `check.py:103-104` has already truncated at `DEFAULT_ENTITY_LIMIT = 500`,
with the remainder recorded separately in `entities_omitted`. On the Schependomlaan run this
repository's Phase 0 measured — 3,623 non-passing entities — a FAIL-only filter renders

```
Showing 12 of 500 findings. The rest are hidden by this filter, not resolved.
```

That sentence asserts the entire gap between 12 and 500 is the filter's doing, and it states a
total of 500 for a run with 3,623 findings. T-0025's own Scope §3 said "do not conflate the two
numbers" — `entities_omitted` counts what the engine capped, the banner counts what the filter
hid — and the wording conflates them anyway. A reader who unchecks nothing still never learns
that 3,123 findings were never itemised at all.

**A partially-filtered specification gives no local signal.** `ReportView.tsx:187-191`
announces only when *every* row in a requirement is hidden. A specification showing 2 of 30
rows is indistinguishable from a specification with 2 findings. The global banner is the only
signal and it is off-screen the moment the reader scrolls into a long list — which, on a real
run, is immediately.

## Scope

**Changes** — `services/web/src/components/ReportView.tsx`, both i18n catalogues, `styles.css`
as needed, `services/web/e2e/report.spec.ts`.

1. The banner must distinguish the two numbers. Either state the omitted count alongside the
   filtered one, or word `total` as the count of *itemised* findings and name the cap
   separately. Whichever is chosen, a reader must be able to tell how many findings exist,
   how many were itemised, and how many the current filter is hiding — three numbers, never
   collapsed into two.
2. A per-requirement signal when some but not all of its rows are hidden.

**Does not change:** the engine, the cap itself, the count band (counts are of the run, not of
the view), and the absence of a PASS filter. `packages/engine` and `services/api` are not
touched.

## How to prove it ran

The existing e2e fixture has two itemised rows and cannot exercise a cap. A fixture or a
stubbed payload that has both `entities_omitted > 0` and a filter hiding rows is required —
if that cannot be reached through the real stack without an unreasonably large fixture, say so
and drive it through a component test with a real payload shape, but do not assert the wording
against a payload you hand-wrote to match it.

`make verify`, then `make up` (rebuild `web`) and `make e2e`, with stdout pasted, plus a
screenshot of a filtered report showing all three numbers.

## Evidence

<!-- the builder writes this -->

## Review
