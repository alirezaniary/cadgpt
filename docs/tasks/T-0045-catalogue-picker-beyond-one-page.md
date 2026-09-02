# T-0045 — The catalogue picker must show every pack, and filter on the server

**Phase:** 3   **Status:** open
**Touches invariants:** none structurally, but this is the coverage failure in the picker.

## Why

Found by the T-0031 review. `services/web/src/api/queries.ts` fetches `/v1/rule-packs/` with no
`size` parameter and never follows `next`; `SimplePagination.page_size` is 20
(`services/api/cadgpt/apps/base/drf/pagination.py:16`). `ReviewsPage.tsx` then filters that one
page client-side with `String.includes`.

The moment the catalogue exceeds 20 packs a user filtering for a jurisdiction whose packs sit on
page 2 is shown `review.catalogue.empty` — *"No packs match this filter."* — and cannot select
them. The packs exist, the filter is correct, and the product says nothing matches. **That is
silent narrowing of what can be picked, dressed as an empty result**, and it is the same class of
failure T-0031 refused on the server side.

It is not hypothetical: the plan's stated near-term path is Iranian building code, then EU, then
US. Twenty is one jurisdiction's worth.

`RulePackFilterSet` (`services/api/cadgpt/apps/rulepack/api/v1/filters.py`) already exposes
server-side `jurisdiction`, `region` and `version` filters that the frontend does not use, so the
client is reimplementing — with different semantics — a filter that already exists. The client's
substring `includes` diverges from the server's `iexact`, which means the two disagree about what
matches even within one page.

## Scope

**Changes**

- The picker filters through the existing server-side `RulePackFilterSet` rather than over one
  client-held page, so the result set is the catalogue and not the first 20 rows of it.
- The list is either fully paged through or explicitly paged in the UI. Decide which and say why
  in the evidence — a picker that loads everything is fine at catalogue scale and honest; a
  picker that loads one page and does not say so is not.
- The empty state must distinguish **"no packs match this filter"** from **"the catalogue has not
  loaded yet"**. Both i18n catalogues.

**What explicitly does not change**

- `RulePackFilterSet` itself, or the pagination default. Both are correct; the frontend is what
  ignores them.
- The selection wire format, the run record, the refusal logic. T-0031 settled those.

## How to prove it ran

`make verify`, then against `make up`:

1. Seed the catalogue past one page — **more than 20 packs** — and show a pack on page 2 being
   found by a filter and successfully selected, ending in a completed run that cites it.
2. The pre-fix behaviour reproduced once, so the defect is on record: the same filter returning
   the empty state before the change.
3. Rendered evidence from `make e2e`'s chromium, not curl. The defect is in the browser.

## Evidence

## Review
