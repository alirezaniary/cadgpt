# T-0052 — The coverage predicate exists three times; the engine should own it once

**Phase:** 3   **Status:** open
**Touches invariants:** three-valued results, I7 coverage honesty.

## Why

Found by the T-0032 review, and the coordinator had flagged the same shape before dispatching it.

The report now has **two renderers**, and the rule that decides what counts as evaluated is written
independently in each:

- `services/api/cadgpt/apps/review/services/report_markdown.py:43` — `_NOTHING_ESTABLISHED_REASONS`
- `services/web/src/components/ReportView.tsx:58` — `NOTHING_ESTABLISHED_REASONS`

Both are hand-copied literals of reason codes that `judge()` assigns at
`packages/engine/src/cadgpt_engine/check.py:177-200`. `_SEVERITY_RANK` duplicates the view's
`SEVERITY_RANK` the same way. Beyond the predicates, the entire heading and label set is now
duplicated between `django.po` and `services/web/src/i18n/*.json`.

The reviewer verified every copy agrees in English today and that the engine has no fourth
non-`APPLIES` code — **there is no present defect in the numbers**. What is wrong is that nothing
compares them and no test would fail on drift. The coverage guarantee — the product's whole
value-add over raw `ifctester` — rests on a predicate maintained in triplicate by memory.

That this is a real risk rather than a tidiness complaint is settled by T-0032's own review: the
duplicated strings **had already diverged in Persian**, where the file and the screen named the
same three-valued verdict with different words. The predicates have not drifted yet. The wording
did, in the first release that had two renderers.

The engine already owns the reason codes. It is the natural owner of the predicate derived from
them.

**One divergence is already live and must be fixed here, not merely prevented.** T-0032's builder
reported it honestly after closing the fix-now round, having found it outside that round's scope:
`report_markdown.py`'s `"Rule packs checked"` heading does not match `fa.json`'s
`report.selection.title`. It is the same defect as the one T-0032's review caught in the verdict
words — the file and the screen naming the same thing differently in Persian — on a string the
review did not enumerate. That it surfaced immediately, in the same release, on a string nobody had
listed, is the argument for this task: enumerating divergences does not scale, and the third one
will not be found by reading either.

## Scope

**Changes**

- The "established nothing" predicate and the severity ranking have **one definition**, owned where
  the reason codes are owned, and both renderers consume it rather than restating it. The engine
  must stay free of framework and network (I1) and must not learn what a `RulePack` is — exporting
  a predicate over its own reason codes does neither.
- A test that fails if a renderer's notion of the predicate diverges from the engine's.
- The duplicated label set gets whatever the same reasoning implies. If server-authored strings are
  the answer for the file (`docs/decisions.md`), say what the screen should do and why.

**What explicitly does not change**

- The numbers today. This is a consolidation; if any count changes, it has gone wrong.
- The Persian wording itself — T-0032's fix-now round reconciled that; this is about making it
  impossible to diverge again.

## How to prove it ran

`make verify`, plus the mutation that is the whole point: **add a fourth reason code to the engine
and show the drift test failing** rather than the two renderers silently disagreeing. Then show the
counts unchanged across a real run in both renderers, before and after.

## Evidence

## Review
