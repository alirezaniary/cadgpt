# T-0035 — Two latent defects in the report view: an unsortable list and a colliding key

**Phase:** 3 — What the first real user needs   **Status:** open
**Touches invariants:** none directly. Not reviewer-gated unless it grows.

## Why

Both found by the T-0025 review (Q2, Q3) by reading the code and reproducing in `node`. Neither
is reachable through today's payload; both are the kind of defect that surfaces once the wire
format moves, and `REPORT_SCHEMA_VERSION` exists precisely because it is expected to.

**One out-of-vocabulary status silently unsorts the entire list.** `ReportView.tsx:29`:
`SEVERITY_RANK[unknown]` is `undefined`, `undefined - n` is `NaN`, and `NaN || (a.index -
b.index)` falls through to index order — producing a non-transitive comparator that disables
severity ordering for every row, not just the unknown one. Observed:

```
input:  a:PASS b:WEIRD c:FAIL d:INDETERMINATE
output: a:PASS b:WEIRD c:FAIL d:INDETERMINATE   (unsorted -- FAIL left below PASS)
```

Reports are persisted documents read back by newer frontends. A FAIL sorted below a PASS
because a single row carried a status this build had not heard of is the severity ordering
T-0025 exists for, silently switched off. A `?? <rank>` default on the lookup makes the
degradation local to the unknown row.

**A non-unique React key.** `ReportView.tsx:167`: ``key={`${entity.global_id}-${entity.reason_code}`}``.
`global_id` is `string | null` for non-rooted entities, so two rows in one requirement with a
null GlobalId and the same reason code collide. The list is re-filtered on every toggle, and
duplicate keys leave React free to reconcile a stale row into a filtered view — which would
show the architect a row that the filter was asked to hide.

## Scope

`services/web/src/components/ReportView.tsx` only, plus a unit test per defect. No i18n, no
styles, no engine, no API.

- Give the rank lookup a defined default and decide deliberately where an unknown status ranks.
  It must not rank above FAIL and it must not be silently dropped.
- Include the pre-filter index in the row key.

## How to prove it ran

These are the two defects in this phase where a browser is not the right instrument — both are
pure functions over a payload. A test that feeds `bySeverity` a shuffled list containing an
unknown status and asserts FAIL still leads, and a test that renders two null-`global_id` rows
sharing a reason code and asserts both survive a filter toggle. `make verify` with both tests
named in the output, and the mutation proof for each: revert the fix, show the test failing.

`make e2e` is not required if no rendered text changed — say so rather than pasting an
unchanged screenshot.

## Evidence

<!-- the builder writes this -->

## Review
