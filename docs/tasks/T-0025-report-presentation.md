# T-0025 — Coverage before findings, findings ordered by severity, and a status filter that cannot hide an unknown

**Phase:** 3 — What the first real user needs   **Status:** open
**Touches invariants:** three-valued results, I7. **The reviewer will be dispatched on this
task.** Every change here is a change to how a limitation is presented, which is the one place
this product is not allowed to be careless.

## Why

The report view is honest but flat. It renders specifications in IDS order, each with its
requirements and a table of entity rows, and it puts the three counts in a band above them.
An architect opening a real run — Schependomlaan against BIM Basis ILS produced 3,623
non-passing entities across its specifications — gets an undifferentiated wall. The twelve
doors that are genuinely too narrow sit somewhere inside the hundred and one that simply have
no width recorded, in whatever order the IDS file happened to list its specifications.

`prd.md` 5.7 asks for two specific things this view does not do. Findings are grouped by
severity, so the pile where the model carried the datum and broke the rule is read first. And
**coverage is presented before findings**, with the summary stating the size of the effective
rule set rather than only the findings emitted — because a report covering a fraction of a
rule set while presenting as complete manufactures confidence, and that is the failure mode
I7 exists to close.

## Scope

**Changes**

- `services/web/src/components/ReportView.tsx` — the whole of this task's behaviour.
- `services/web/src/i18n/en.json` and `services/web/src/i18n/fa.json` — every new string.
  Both catalogues, in the same commit. A string that exists in one is a bug.
- `services/web/src/styles.css` — as needed for the new blocks.
- `services/web/e2e/report.spec.ts` — extend the T-0024 spec to assert the new behaviour.

**What explicitly does not change**

- The engine, the report schema, the serializers, the API. Everything below is already in the
  payload; this is a presentation task and must not touch `packages/engine` or `services/api`.
  If you find you need a field that is not there, stop and say so rather than adding one.
- The scope disclosure — "what is checked is the model, what is submitted is sheets" — is
  **T-0026**, not this task. Leave room above the coverage block for it; do not write it.

### 1. Coverage, above the findings

A block that comes before the specification list and states the size of the effective rule
set, not just what came out of it. From the payload you already have:

- How many specifications were evaluated, out of how many the rule set contains:
  `specifications_passed + specifications_failed + specifications_indeterminate` against
  `specifications.length`.
- How many specifications **established nothing** — those whose `applicability` is
  `DOES_NOT_APPLY` or `UNDETERMINED_APPLICABILITY`, or whose `matched` is 0. A rule that
  matched nothing has established no compliance however green `ifctester` reports it; that
  is why `Applicability` is a separate enum from `Status` (see the commit
  *"Applicability is a separate question from status"*). Name them, do not just count them.
- The three entity counts stay, and stay three. They move into or directly under this block
  so that coverage reads before findings rather than beside them.

The wording is yours, but it must be a sentence an architect can repeat to a plan reviewer,
in the spirit of `prd.md` 5.7's *"this run evaluated 12 of 80 provisions"*. It must never
imply that what was not evaluated was fine.

### 2. Severity ordering

`docs/decisions.md`, *"Severity, for a report built on IDS, is the three-valued status"*:
IDS carries no severity field and we do not invent one. Severity is status, ordered
**FAIL, then INDETERMINATE, then PASS**.

- Order the specification list by that ranking, stably — two specifications with the same
  status keep their IDS order, because that order is the rule author's.
- Order the entity rows inside each requirement by the same ranking, stably.

INDETERMINATE sits above PASS and never below it. Sorting it last buries it under the passes
and quietly restores the two-valued reading this product exists to refuse.

### 3. The status filter

A control that filters which entity rows are shown. Three facts constrain it, and the third
is the one that is easy to get wrong:

- **The itemised rows are non-passing only.** `check.py` builds `EntityOutcome` rows for
  entities that did not pass; passing entities are counted and never listed
  (`packages/engine/src/cadgpt_engine/report.py`, `EntityOutcome` — "One element that did not
  pass, and why"). So the real filter is FAIL, INDETERMINATE, or both. **Do not build a PASS
  filter**: it would be a control that always yields an empty list and reads as "no passes
  found", which is the exact inversion of the truth.
- **The counts never move.** The three counts are counts of the run, not of the current view.
  Filtering to FAIL must not make the INDETERMINATE count disappear, shrink, or drop out of
  the summary. `INDETERMINATE` never becomes `PASS` in any count, summary, filter, or API
  response — filtering is a view state, and the count band is not a view.
- **The filter announces itself.** When a filter is active the view says so, and says what is
  being withheld — "showing 12 of 113" or equivalent. A filtered report that looks identical
  to an unfiltered one is a report that lies by omission. A specification left with no visible
  rows should say why it is empty rather than silently vanishing.
- `entities_omitted` is already rendered and must survive filtering with its meaning intact:
  it counts what the engine capped, not what the filter hid. Do not conflate the two numbers.

## How to prove it ran

The harness from T-0024 is the instrument; read `docs/tasks/T-0024-browser-evidence-harness.md`
for how it is invoked and what it already does. The fixtures produce exactly one of each
status, which is what makes them a usable test of ordering:

```sh
make verify
make up
make e2e
```

Extend `e2e/report.spec.ts` and paste the run's actual stdout. The evidence must show, from
the rendered page in a real browser:

1. The coverage block appears **before** the first specification in the DOM. Assert on
   document order, not on the presence of both — a coverage line rendered underneath the
   findings satisfies a presence check and fails the requirement.
2. The FAIL row (`ATTRIBUTE_VALUE_MISMATCH`, detail containing `800`) appears **before** the
   INDETERMINATE row (`ATTRIBUTE_EMPTY`) in the DOM.
3. With the filter set to FAIL only: the INDETERMINATE entity row is gone from the list, **and
   the indeterminate count in the summary still reads 1**, and the view states that rows are
   being withheld. This is the assertion the reviewer will look for first.
4. A screenshot of the report, unfiltered, committed and actually opened by you.

**Wiring:** quote the line where the new filter state is read in `ReportView.tsx`, and confirm
every new i18n key exists in both `en.json` and `fa.json` — paste the key list from each.

## Evidence

<!-- the builder writes this -->

## Review
