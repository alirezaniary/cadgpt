# T-0052 — The coverage predicate exists three times; the engine should own it once

**Phase:** 3   **Status:** done
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

**What landed.** The engine now owns both predicates, in `packages/engine/src/cadgpt_engine/status.py`:
`NOTHING_ESTABLISHED_REASONS` / `established_nothing()` and `SEVERITY_RANK`, exported from
`cadgpt_engine/__init__.py`. `report_markdown.py` (same language) imports both directly and no
longer has `_NOTHING_ESTABLISHED_REASONS` / `_SEVERITY_RANK` of its own.
`presentation.localize_report` computes one new wire field, `established_nothing`, on every
specification from `cadgpt_engine.established_nothing` — `ReportView.tsx` reads that field
instead of its old hand-copied `NOTHING_ESTABLISHED_REASONS` set/`establishedNothing()`, which are
deleted. `SEVERITY_RANK` alone stays duplicated in `ReportView.tsx`, on purpose: T-0025 review
Q2's `UNKNOWN_STATUS_RANK` fallback (a report a *newer* engine wrote, read by an *older*
frontend) is a client-side forward-compatibility need with no wire representation the server
could hand down instead — see `docs/decisions.md` ("The coverage predicate and severity rank are
owned by the engine; UI chrome stays two catalogues") for the full reasoning, including why the
rest of the duplicated label set (headings/table columns between `django.po` and
`services/web/src/i18n/*.json`) is deliberately left alone: that decision distinguishes
*report prose* (server-authored, already the rule) from static *UI chrome* naming the same
section in two idioms, which carries no per-run data to drift.

The one live divergence T-0032 found is fixed: `django.po`'s `msgstr` for `"Rule packs checked"`
now reads `بسته‌های مقرراتی که بررسی شدند`, byte-identical to `fa.json`'s
`report.selection.title`. Verified live (see "Real path" below).

Two new tests close the gap: `packages/engine/tests/test_judgement.py::test_nothing_established_reason_codes_are_total_over_judge`
sweeps every `judge()` parameter combination and asserts the resulting zero-evidence code set
equals `NOTHING_ESTABLISHED_REASONS` — this is the drift test the mutation below exercises.
`services/api/cadgpt/apps/review/tests/test_report_markdown.py::test_report_view_severity_rank_matches_the_engine`
reads `ReportView.tsx`'s `SEVERITY_RANK` literal back out of the `.tsx` source and asserts it
equals `cadgpt_engine.SEVERITY_RANK`. `test_established_nothing_reads_the_field_presentation_computed`
proves `report_markdown.py` follows the `established_nothing` field rather than re-deriving one
from `reason_code`. `test_presentation.py` gained two tests for the new field itself.

**`make verify`:**

```
$ make verify
...
Contracts: 5 kept, 0 broken.
...
310 passed, 1 deselected, 35 warnings in 5.07s
...
> @cadgpt/web@0.1.0 lint / typecheck / build / build-workbench / test-unit / test-storybook
...
Test Files  1 passed (1)      Tests  2 passed (2)     (test-unit)
Test Files  9 passed (9)      Tests  36 passed (36)   (test-storybook)
```
Full transcript: ruff check/format clean, `mypy --strict` over `packages/engine/src` and
`services/api/cadgpt` — "Success: no issues found in 176 source files" — all 5 import-linter
contracts kept, 310 backend tests passed (1 postgres-marked deselected, as `make verify` always
does), frontend build + Storybook build + 2 unit + 36 Storybook tests all green.

**Real path.** Ran the engine's real CLI entry point against real fixture files —
`packages/engine/tests/fixtures/three_doors.ifc` and
`services/web/e2e/fixtures/nothing_established.ids` (an existing fixture built for exactly this
shape: one specification that genuinely evaluates real doors, one that established nothing via
`NO_SUBJECTS_NOTHING_CHECKED`, one real `NO_SUBJECTS_BUT_REQUIRED` FAIL):

```
$ uv run cadgpt-check packages/engine/tests/fixtures/three_doors.ifc services/web/e2e/fixtures/nothing_established.ids
three_doors.ifc (IFC4)  against  'Coverage against a rule set that partly matches nothing'
engine 0.2.0

  overall            FAIL
  specifications     1 pass / 1 fail / 1 indeterminate
  entity outcomes    3 pass / 0 fail / 0 indeterminate

  [         PASS] Door name recorded
      APPLIES, cardinality required, 3 element(s) matched
  [INDETERMINATE] Wall fire rating recorded
      DOES_NOT_APPLY, cardinality optional, 0 element(s) matched
      No element matched this rule, so nothing was checked. ...
  [         FAIL] Wall count required
      APPLIES, cardinality required, 0 element(s) matched
      The rule requires matching elements and the model contains none.
```

Then fed the same `--json` output through the *real* production functions
(`cadgpt.apps.review.services.presentation.localize_report` and
`...report_markdown.render_markdown_report`, imported and called exactly as
`report_generation.py` and `serializers.py` call them) via `manage.py`-equivalent Django setup —
this is the file renderer and the JSON the API serves, not a mock:

```
$ uv run python render.py report.json after_localized.json after_report.md
counts: 3 0 0
spec counts: 1 1 1
established_nothing specs: ['Wall fire rating recorded']
```

Confirmed the live Persian divergence is fixed, with real `gettext` and the real `fa.json`, both
reading the identical string:
```
>>> gettext('Rule packs checked')   under translation.override('fa')
'بسته‌های مقرراتی که بررسی شدند'
>>> fa.json's report.selection.title
'بسته‌های مقرراتی که بررسی شدند'
```
And confirmed it renders in a real generated Markdown file (with a rule pack selection attached,
under `fa`):
```
## بسته‌های مقرراتی که بررسی شدند
```

**Counts unchanged, before and after, both renderers.** `git stash`d this task's diff, ran the
identical `report.json` through the identical `render.py` script against the pre-T-0052 code
(`before_localized.json`, `before_report.md`), `git stash pop`ped back to this task's code, and
reran (`after_localized.json`, `after_report.md`):
```
$ diff before_report.md after_report.md && echo IDENTICAL
IDENTICAL
$ python3 -c "... strip 'established_nothing' keys and compare ..."
equal after stripping established_nothing: True
```
The only difference between the before/after JSON is the additive `established_nothing` field
itself (absent before this task, `.get()`-safe); the Markdown file is byte-for-byte identical.
`counts: 3 0 0` / `spec counts: 1 1 1` match on both sides.

**Mutation test — the drift detector actually catches drift.** Added a fourth `ReasonCode`
(`MUTATION_FOURTH_ZERO_EVIDENCE_CODE`) to `status.py` and pointed `judge()`'s
`optional`-with-no-requirements branch at it instead of `NO_REQUIREMENTS_NOTHING_ASSERTED`,
deliberately *not* adding it to `NOTHING_ESTABLISHED_REASONS` — exactly "a fourth reason code
added upstream and not carried into the exclusion set":

```
$ uv run pytest packages/engine/tests/test_judgement.py services/api/cadgpt/apps/review/tests/test_report_markdown.py services/api/cadgpt/apps/review/tests/test_reasons.py -q
FAILED packages/engine/tests/test_judgement.py::test_an_optional_specification_with_no_requirements_never_passes
FAILED packages/engine/tests/test_judgement.py::test_nothing_established_reason_codes_are_total_over_judge
AssertionError: assert {<ReasonCode....MA_MISMATCH'>} == frozenset({<R...A_MISMATCH'>})
  Extra items in the left set:
  <ReasonCode.MUTATION_FOURTH_ZERO_EVIDENCE_CODE: 'MUTATION_FOURTH_ZERO_EVIDENCE_CODE'>
  Extra items in the right set:
  <ReasonCode.NO_REQUIREMENTS_NOTHING_ASSERTED: 'NO_REQUIREMENTS_NOTHING_ASSERTED'>
FAILED services/api/cadgpt/apps/review/tests/test_reasons.py::test_every_engine_reason_code_has_a_translatable_label[MUTATION_FOURTH_ZERO_EVIDENCE_CODE]
```
`test_nothing_established_reason_codes_are_total_over_judge` — the single drift test both
renderers now depend on transitively — failed exactly as intended, catching the divergence at
the one place it can now occur, rather than the two renderers silently disagreeing with each
other the way they could before this task. Mutation reverted
(`git diff --stat packages/engine/src/cadgpt_engine/status.py packages/engine/src/cadgpt_engine/check.py`
shows no residual change), full suite reconfirmed green (`uv run pytest -m "not postgres" -q` →
"310 passed, 1 deselected").

**Wiring.**
- `cadgpt_engine/__init__.py`: `from cadgpt_engine.status import (..., NOTHING_ESTABLISHED_REASONS, SEVERITY_RANK, ..., established_nothing)` and both names listed in `__all__` — this is what makes them importable as `cadgpt_engine.established_nothing` / `cadgpt_engine.SEVERITY_RANK` from the service.
- `services/api/cadgpt/apps/review/services/presentation.py`: `from cadgpt_engine import established_nothing`, called at
  `"established_nothing": established_nothing(spec.get("reason_code"))` inside `localize_report` — the function every report-serving path (`CheckRunDetailSerializer.get_report` and `report_generation.py`'s Markdown path) already calls before a report reaches either renderer.
- `services/api/cadgpt/apps/review/services/report_markdown.py`: `from cadgpt_engine import SEVERITY_RANK`, used at `sorted(items, key=lambda item: SEVERITY_RANK[item["status"]])`.
- `services/web/src/components/ReportView.tsx`: `establishedNothing` now reads `spec.established_nothing` — the field `types.ts`'s `SpecificationOutcome.established_nothing: boolean` declares as always present, matching what `localize_report` always sets.

**NOT DONE:** nothing. All five scope items (single predicate + rank definition, drift test,
the live heading fix, a reasoned decision on the label set, counts unchanged) are complete with
evidence above.

## Review

**Verdict: clean.** Reviewer independently re-ran `make contracts`, `make verify`, the engine
CLI real path, and reproduced the mutation test (plus three more mutations of their own:
frontend `SEVERITY_RANK`, `_established_nothing` reverted to a local set, and the
`established_nothing` field deleted from `localize_report` — all four caught by the new tests
and reverted cleanly). Confirmed `NOTHING_ESTABLISHED_REASONS` is correctly derived from
`judge()`'s actual `(INDETERMINATE, code)` returns, I1 is intact (`status.py` imports only
`enum`), `established_nothing` is unconditionally set, the Persian strings are now
byte-identical, and counts are unchanged via an independent worktree diff. No invariant
violation, no false evidence-block claim.

**Findings — none fix-now, all recorded as observations for the judge:**
1. *(Medium)* No test exercises the frontend's actual consumption of `established_nothing` —
   `ReportView.tsx`'s `establishedNothing()` was mutated to `return false` and the full frontend
   suite (lint, typecheck, 2 unit, 36 Storybook) still passed. TypeScript catches a renamed
   field; nothing catches the screen ignoring it. This is the one unverified hop in the
   drift-proofing chain this task built; the Markdown side and `localize_report` are both
   mutation-verified. Pre-existing gap (the old hand-copied TS set had the same hole), not a
   regression.
2. *(Low)* `status.py:122`'s guard comment names a nonexistent test
   (`test_report_markdown.py::test_established_nothing_reason_codes_are_total_over_judge`); the
   real guard is `test_judgement.py::test_nothing_established_reason_codes_are_total_over_judge`.
   Misleads the next person adding a reason code.
3. *(Low)* `SEVERITY_RANK` is exported as a mutable `dict` while its siblings are `frozenset`s —
   no `Final`/`MappingProxyType`, so any consumer can reorder the engine's severity ranking
   process-wide.
