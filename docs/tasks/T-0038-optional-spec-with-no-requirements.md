# T-0038 — A specification that asserted nothing must not report PASS either

**Phase:** 3 — What the first real user needs   **Status:** done
**Touches invariants:** three-valued results, I7. **Reviewer-gated.**

## Why

T-0028 fixed this at the requirement level. The T-0028 reviewer found it still live one level
up, in the function T-0028 was explicitly forbidden to touch.

`judge()` at `packages/engine/src/cadgpt_engine/check.py:155-160` now carries a comment
asserting that reaching its final return proves "something was evaluated and passed". That is
false for a specification with **no requirement facets at all**. Reproduced: `<ids:requirements/>`
with `minOccurs="0" maxOccurs="unbounded"` over `IFCDOOR`, run against
`packages/engine/tests/fixtures/three_doors.ifc`:

```
spec APPLIES PASS optional matched 3 reqs 0 reason null
report status PASS, passed/failed/indeterminate all zero
```

It validates against the buildingSMART XSD, so it is reachable from real user input — a rule
author who selects a subject and has not yet written the requirement gets a green PASS over a
rule that asserts nothing. An *optional* specification with zero requirements checked nothing
and established nothing, and the report calls it a pass. That is the same I7 failure T-0028
just closed, one level up.

**The `required`-cardinality version is not a defect and must stay PASS.** `minOccurs="1"` with
zero requirements is a legitimate existence check — "at least one of these must exist" — and
`matched > 0` genuinely establishes it. The hole is specifically `optional` plus zero
requirements. A fix that turns existence checks indeterminate breaks a real feature.

## Scope

**Changes**

- `packages/engine/src/cadgpt_engine/check.py` — `judge()`. A specification with no requirement
  facets whose cardinality is `optional` established nothing and is `INDETERMINATE`, with a
  reason. And **either fix the comment at lines 155-160 or delete it** — a comment asserting an
  invariant the code does not hold is worse than no comment.
- `packages/engine/src/cadgpt_engine/status.py` — a `ReasonCode` if none fits; read the list
  first and reuse `NO_SUBJECTS_NOTHING_CHECKED` or its neighbours rather than adding a synonym.
- `packages/engine/pyproject.toml` — **bump the engine package version.** This release changes
  a verdict the engine can emit. See `docs/decisions.md`, *"A verdict-changing engine release
  bumps the engine version"*, which this task is the first application of; it is retrospective
  for T-0028 as well, so state in the evidence that the bump covers both changes.
- `packages/engine/tests/` — a fixture per case and a test per case.

**Does not change:** `_aggregate` (settled by T-0028), the `required`-with-zero-requirements
PASS, the report schema — the wire format does not move here, only the verdict, which is
precisely why the *engine* version and not `REPORT_SCHEMA_VERSION` is what bumps.

## How to prove it ran

```sh
uv run cadgpt-check packages/engine/tests/fixtures/three_doors.ifc <optional-no-reqs.ids> --json
uv run cadgpt-check packages/engine/tests/fixtures/three_doors.ifc <required-no-reqs.ids> --json
make verify
```

Evidence must show both: the optional-with-no-requirements specification flipping PASS ->
INDETERMINATE with its reason, and the required-with-no-requirements specification **still**
PASS. Paste before and after for both. Mutation proof on each new test. Quote the bumped
version line and the `CheckRun.engine_version` a fresh run now records — the point of the bump
is that a stored run says which engine judged it, so show a real run recording the new value.

## Evidence

**Code.** `judge()` in `packages/engine/src/cadgpt_engine/check.py` takes a new
`has_requirements: bool` parameter. Immediately after the `prohibited` branch and before the
final `_aggregate` return, a new branch: `if cardinality == "optional" and not has_requirements:
return (Applicability.APPLIES, Status.INDETERMINATE, ReasonCode.NO_REQUIREMENTS_NOTHING_ASSERTED)`.
`required` with zero requirements is untouched — it still falls through to the final
`_aggregate(matched, failed, indeterminate)` return, which is `PASS` when `matched > 0`. The
call site, `_specification()`, passes `bool(spec.requirements)`. The comment on the final return
(previously the one flagged as false) is rewritten to state the two cases that legitimately
reach it now that the illegitimate one is intercepted above it.

A new `ReasonCode.NO_REQUIREMENTS_NOTHING_ASSERTED` was added rather than reusing
`NO_SUBJECTS_NOTHING_CHECKED`, after reading that code's own message ("No element matched this
rule, so nothing was checked") — false here, since `matched == 3`. Reusing it would have made
the label lie about a real report. Wired through `cadgpt_engine.messages` (English fallback),
`cadgpt.apps.review.reasons.REASON_LABELS` (the Django `gettext_lazy` label a report actually
renders), and `services/api/cadgpt/locale/fa/LC_MESSAGES/django.po` (Farsi translation, added by
hand in the file's existing `#: cadgpt/apps/review/reasons.py (CODE)` comment convention — a
plain `manage.py makemessages -a` regenerates the whole catalogue with line-number comments
instead and was reverted rather than committed, to keep this diff to what T-0038 needs).

**Engine version bump.** `packages/engine/pyproject.toml`: `version = "0.1.0"` -> `"0.2.0"`.
Per `docs/decisions.md`, *"A verdict-changing engine release bumps the engine version"*: **this
bump is retrospective for T-0028 as well** — T-0028 changed what `INDETERMINATE` a stored report
could carry without ever bumping the version off `0.1.0`, and that decision entry says the T-0038
bump is where T-0028's verdict change finally gets one. `uv.lock`'s `cadgpt-engine` entry moved
with it (`uv run` regenerates the lock automatically; diff is the one version line).

**New fixtures and tests** (packages/engine/tests/): `fixtures/door_optional_no_requirements.ids`
(optional cardinality, `<ids:entity><ids:name><ids:simpleValue>IFCDOOR</...></ids:entity>`,
empty `<ids:requirements/>`) and `fixtures/door_required_no_requirements.ids` (same, `required`
cardinality). Both validate against the bundled buildingSMART XSD (`ifctester.ids.open(...,
validate=True)` — confirmed by hand before wiring tests: `s.get_usage()` returned `"optional"`
and `"required"` respectively, `s.requirements == []` for both). `conftest.py` gained matching
path fixtures. `test_judgement.py` gained two direct-`judge()` tests
(`test_an_optional_specification_with_no_requirements_never_passes`,
`test_a_required_specification_with_no_requirements_stays_pass`) plus two new rows in the
existing `JUDGEMENTS` parametrization, all threading the new `has_requirements` argument.
`test_check.py` gained two real-path tests running `run_check()` against the new fixtures.

### 1. `make verify`

Run with `PATH`/`LD_LIBRARY_PATH` pointed at a locally-extracted `gettext` (the sandbox has no
system package manager access; `msgfmt`/`xgettext` are not on `PATH` otherwise — an environment
gap, not a repository one). Full output tail:

```
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
File ".../locale/fa/LC_MESSAGES/django.po" is already compiled and up to date.
uv run pytest
...
256 passed, 34 warnings in 4.33s
...
Storybook build completed successfully
```
Exit code: `0`.

### 2. The real path, before and after

Ran `cadgpt-check` against both fixtures with the fix reverted (`git stash` on the five changed
`src`/`pyproject.toml`/`uv.lock` files, fixtures kept), then again with it restored.

**Before** (both wrongly PASS — reproduces the defect exactly as described):

```json
// door_optional_no_requirements.ids
{
  "engine_version": "0.1.0",
  "status": "PASS",
  "specifications": [{
    "cardinality": "optional", "matched": 3, "reason_code": null,
    "status": "PASS", "requirements": []
  }]
}
```
```json
// door_required_no_requirements.ids
{
  "engine_version": "0.1.0",
  "status": "PASS",
  "specifications": [{
    "cardinality": "required", "matched": 3, "reason_code": null,
    "status": "PASS", "requirements": []
  }]
}
```

**After**:

```json
// door_optional_no_requirements.ids
{
  "engine_version": "0.2.0",
  "status": "INDETERMINATE",
  "specifications": [{
    "cardinality": "optional", "matched": 3,
    "reason_code": "NO_REQUIREMENTS_NOTHING_ASSERTED",
    "status": "INDETERMINATE", "requirements": []
  }]
}
```
```json
// door_required_no_requirements.ids
{
  "engine_version": "0.2.0",
  "status": "PASS",
  "specifications": [{
    "cardinality": "required", "matched": 3, "reason_code": null,
    "status": "PASS", "requirements": []
  }]
}
```

Optional flipped PASS -> INDETERMINATE with a reason. Required stayed PASS, byte-for-byte the
same shape, only `engine_version` moved. (Full JSON for all four runs is reproducible with
`uv run cadgpt-check packages/engine/tests/fixtures/three_doors.ifc
packages/engine/tests/fixtures/door_{optional,required}_no_requirements.ids --json` from
`packages/engine`.)

### 3. Mutation-testing the new tests

Each mutation applied to `check.py`, run against `tests/test_judgement.py tests/test_check.py`,
then reverted (verified byte-identical to the fix via `diff` before continuing):

- **Deleted the new `optional`-branch entirely** (restores the original bug) -> killed by 3
  tests: `test_applicability_and_status_come_from_subjects_and_cardinality[optional-3-True-0-0-False-...]`,
  `test_an_optional_specification_with_no_requirements_never_passes`,
  `test_an_optional_specification_with_no_requirements_is_indeterminate_not_pass`.
- **Inverted the condition** (`and has_requirements` instead of `and not has_requirements`) ->
  killed by the same 3 tests.
- **Reused the wrong reason code** (`NO_SUBJECTS_NOTHING_CHECKED` instead of
  `NO_REQUIREMENTS_NOTHING_ASSERTED`) -> killed by 2 tests asserting the exact code.
- **Broke the call-site wiring** (`_specification` passing a hardcoded `True` instead of
  `bool(spec.requirements)`) -> killed by exactly 1 test,
  `test_an_optional_specification_with_no_requirements_is_indeterminate_not_pass` in
  `test_check.py` — the direct `judge()` unit tests in `test_judgement.py` cannot see a
  call-site wiring bug, which is exactly why the real-path integration test in `test_check.py`
  exists alongside it.

Every mutation was killed. `check.py` was restored to the intended fix and `diff`-verified
identical before moving on.

### 4. A real `CheckRun` recording the bumped engine version, end to end

Not just the constant in isolation: a real `POST /api/v1/reviews/{uuid}/check/` through DRF, a
real synchronous Celery task (`CELERY_TASK_ALWAYS_EAGER` in test settings), a real `CheckRun` row
read back from the database, and a real `GET` of the stored report — through
`cadgpt.apps.review.services.execution.CheckRunExecutor`, the only code path a worker enters.
Two new permanent regression tests do this,
`test_an_optional_specification_with_no_requirements_is_indeterminate_end_to_end` and
`test_a_required_specification_with_no_requirements_still_passes_end_to_end` in
`services/api/cadgpt/apps/review/tests/test_check_run.py` (both pass: see the 256-pass count
above). Ran a throwaway, uncommitted copy of the same scenario with `-s` to capture literal
output (deleted afterward; `git status` on `services/api/cadgpt/apps/review/tests/` shows only
the permanent test file modified):

```
=== OPTIONAL, no requirements ===
CheckRun.engine_version: 0.2.0
CheckRun.outcome: INDETERMINATE
{
  "name": "Optional door subject, no requirements",
  "applicability": "APPLIES",
  "status": "INDETERMINATE",
  "cardinality": "optional",
  "matched": 3,
  "reason_code": "NO_REQUIREMENTS_NOTHING_ASSERTED",
  "passed": 0, "failed": 0, "indeterminate": 0,
  "requirements": [],
  "reason_label": "اعضایی با این قاعده منطبق شدند، اما قاعده هیچ الزامی بیان نمی‌کند، بنابراین چیزی درباره آنها بررسی نشد."
}

=== REQUIRED, no requirements ===
CheckRun.engine_version: 0.2.0
CheckRun.outcome: PASS
{
  "name": "Required door subject, no requirements",
  "applicability": "APPLIES",
  "status": "PASS",
  "cardinality": "required",
  "matched": 3,
  "reason_code": null,
  "passed": 0, "failed": 0, "indeterminate": 0,
  "requirements": [],
  "reason_label": null
}
```

`CheckRun.engine_version` is `"0.2.0"` on both real rows — the point of the bump: a stored run
now says which engine judged it, and this one genuinely differs from every run recorded before
this fix.

### Wiring

- `judge()`'s call site, `packages/engine/src/cadgpt_engine/check.py` (`_specification`):
  `cardinality, matched, schema_matches, failed, indeterminate, bool(spec.requirements)` — the
  new argument is threaded from the real parsed IDS, not a default.
- The new `ReasonCode` reaches a user: `cadgpt.apps.review.reasons.REASON_LABELS` (
  `services/api/cadgpt/apps/review/reasons.py`) — `ReasonCode.NO_REQUIREMENTS_NOTHING_ASSERTED:
  _("Elements matched this rule, but it states no requirements, so nothing was checked about
  them.")` — and `test_every_engine_reason_code_has_a_translatable_label` in
  `services/api/cadgpt/apps/review/tests/test_reasons.py` (parametrized over `list(ReasonCode)`,
  so this code was mechanically included) passed in the 256-pass run above; it failed before this
  entry was added, which is what caught the missing wiring in the first place.
- The engine version reaches storage: `services/api/cadgpt/apps/review/services/execution.py:251`
  — `run.engine_version = report.engine_version` — unchanged by this task, and proven live in
  section 4 above (`CheckRun.engine_version: 0.2.0`).

### NOT DONE

Nothing. All three changes in scope (`check.py`/`judge()`, the new `ReasonCode`, the engine
version bump retroactively covering T-0028) are implemented, tested directly and through the
real path, and mutation-verified.

---

## 2026-09-10 — Post-review fix-now round

The review found a real invariant violation the first pass introduced: `judge()`'s new
`NO_REQUIREMENTS_NOTHING_ASSERTED` INDETERMINATE was not in either renderer's
"established nothing" exclusion set, so it was silently counted as *evaluated* in the
coverage numerator, and the web view additionally dropped it from the "what wasn't
established" disclosure list entirely — CLAUDE.md's "INDETERMINATE never becomes PASS in
any count, summary, filter, or API response" one level up from where the first round's own
evidence checked it (at the specification's own `status` field, which was correct; the bug
was in the two separate coverage-aggregation predicates neither round 1 nor its evidence
touched). Scope of this round, per the coordinator: fix exactly this, add the missing
structural test, re-prove the real path, re-run `make verify`. Nothing else the review
raised (the weak `engine_version` truthy-only assertion, the stale compose image, `judge()`'s
exported signature accepting an unreachable combination, the pre-existing dirty
`.gitignore`/logo files) was touched — those are queued as observations for the judge, not
this round's job.

**Fix.**
`services/api/cadgpt/apps/review/services/report_markdown.py:66-68` —
`_NOTHING_ESTABLISHED_REASONS` gained `"NO_REQUIREMENTS_NOTHING_ASSERTED"`, now
`frozenset({"SCHEMA_MISMATCH", "NO_SUBJECTS_NOTHING_CHECKED", "NO_REQUIREMENTS_NOTHING_ASSERTED"})`.
`services/web/src/components/ReportView.tsx:61-65` — the mirrored `NOTHING_ESTABLISHED_REASONS`
`Set` gained the same string. Both docstrings/comments were updated to name the third code and,
on the Python side, the new test that now guards it.

**The missing structural test.** Added
`test_every_established_nothing_reason_code_is_excluded_from_coverage` to
`services/api/cadgpt/apps/review/tests/test_report_markdown.py`. Unlike a hand-typed
parametrization (which would just restate the same three codes on both sides and could never
catch a *new* one), this sweeps every reachable `judge()` parameter combination
(`cardinality × matched × schema_matches × failed × indeterminate × has_requirements`, 96
combinations) and collects every reason code `judge()` ever pairs with `Status.INDETERMINATE`.
That set is provably identical to "codes meaning nothing was established": `judge()` only
attaches a reason code at all on an early return that bypassed real per-entity evidence, and
among those early returns the ones landing on `FAIL`/`PASS` (`NO_SUBJECTS_BUT_REQUIRED`,
`NO_SUBJECTS_AND_PROHIBITED`, `PROHIBITED_SUBJECTS_PRESENT`) are real verdicts, not absences of
evidence — only the `INDETERMINATE`-paired ones are. The test asserts this observed set equals
`_NOTHING_ESTABLISHED_REASONS` exactly, the same "total over what the engine can produce"
pattern `test_every_engine_reason_code_has_a_translatable_label` (`test_reasons.py`) already
uses for label wiring.

**Mutation proof the new test actually catches the shipped bug**, not a tautology: reverted
`_NOTHING_ESTABLISHED_REASONS` to the pre-fix two-element set
(`frozenset({"SCHEMA_MISMATCH", "NO_SUBJECTS_NOTHING_CHECKED"})`) and ran the new test alone:

```
FAILED services/api/cadgpt/apps/review/tests/test_report_markdown.py::test_every_established_nothing_reason_code_is_excluded_from_coverage
AssertionError: assert {'NO_REQUIREM...EMA_MISMATCH'} == frozenset({'N...MA_MISMATCH'})
Extra items in the left set:
'NO_REQUIREMENTS_NOTHING_ASSERTED'
```

Restored and `diff`-verified byte-identical to the fix before continuing. The TS mirror has no
compiler-enforced equivalent (an object literal has no such introspection short of running the
module), stated explicitly in both files' comments as the one place this fix still relies on a
human keeping two sets in sync by hand rather than a test — noted, not silently assumed away.

**Real path, re-run.** `render_markdown_report` invoked directly (not mocked) against the real
engine's output for both fixtures, in the actual Django settings/translation context
(`DJANGO_SETTINGS_MODULE=cadgpt.config.settings.test`, `translation.override("en")`):

Optional, no requirements — corrected coverage section:

```
## Coverage

0 of 1 specifications were evaluated.

| Passed | Failed | Could not be determined |
|---|---|---|
| 0 | 0 | 0 |

1 specification established nothing — it matched no elements, or its applicability could not be determined:

- Optional door subject, no requirements
```

(Before this round's fix: "1 of 1 specifications were evaluated." and no "established nothing"
section at all — the exact contradiction the reviewer rendered and reported.)

Required, no requirements — confirmed unaffected:

```
## Coverage

1 of 1 specifications were evaluated.

| Passed | Failed | Could not be determined |
|---|---|---|
| 0 | 0 | 0 |
```

No "established nothing" section — the required-existence-check case still counts as
evaluated/PASS, exactly as round 1 established.

**Web-side equivalent**, since a full browser render is out of proportion for a two-line fix:
the corrected predicate and the `evaluated` computation were run verbatim (copied from
`ReportView.tsx`'s actual updated `NOTHING_ESTABLISHED_REASONS`/`establishedNothing` code, not
reimplemented) under Node against fixture-shaped specification objects for both cases:

```
=== optional ===
evaluated: 0 of 1
nothingEstablished list: Optional door subject, no requirements
=== required ===
evaluated: 1 of 1
nothingEstablished list: (empty)
```

The optional specification now appears in the disclosure list the reviewer found empty; the
required case is untouched. `make verify`'s frontend build and Storybook build (below) confirm
`ReportView.tsx` still typechecks and builds with this change.

**`make verify`**, full run after the fix:

```
uv run ruff check .
All checks passed!
...
uv run mypy packages/engine/src services/api/cadgpt
Success: no issues found in 170 source files
...
Contracts: 5 kept, 0 broken.
...
uv run pytest
...
257 passed, 34 warnings in 4.33s
...
Storybook build completed successfully
```
Exit code: `0`. (257, up from round 1's 256 — the one new structural test.)

**NOT DONE, this round:** nothing in scope. Left alone, per the coordinator's instruction and the
"a review of a fix is never dispatched" rule in `docs/agents.md`: the weak
`assert run.engine_version` (truthy-only, doesn't pin `"0.2.0"`), the stale compose image, the
unreachable `(cardinality="prohibited", has_requirements=False)` combination `judge()`'s exported
signature still accepts without complaint, and the pre-existing dirty `.gitignore`/`cadgpt-logo.svg`
files unrelated to this task. These are the coordinator's/judge's observations, not this round's.

## Review

**Verdict: one fix-now, closed in the post-review round above; four observations for the judge.**

Independently re-verified rather than trusted: `make verify` (256 passed pre-fix), the real
JSON output for both fixtures (optional PASS -> INDETERMINATE, required stays PASS, both
`engine_version: 0.2.0`), branch containment (the new branch cannot swallow a genuine PASS/FAIL
— `has_requirements=False` implies `failed == indeterminate == 0` and `get_usage()` only ever
returns `required|optional|prohibited`), the Farsi catalogue is genuinely compiled, and two of
the builder's claimed mutations were re-run by hand with identical results.

**Fix-now (closed):** the new `NO_REQUIREMENTS_NOTHING_ASSERTED` INDETERMINATE was absent from
both renderers' "established nothing" exclusion sets (`report_markdown.py`,
`ReportView.tsx`), so it was silently counted as *evaluated* in the coverage numerator — the
delivered Markdown report read "1 of 1 specifications were evaluated" directly above a
specification whose own reason label said nothing was checked about it, and the web view
additionally dropped it from the "what wasn't established" disclosure list. A direct instance
of the invariant this task exists to protect. Closed same-task, same builder, per
`docs/agents.md` — no new review dispatched on the fix. Verified: both sets now include the
code, a new structural test (`test_every_established_nothing_reason_code_is_excluded_from_
coverage`) sweeps all 96 reachable `judge()` combinations and mutation-kills the exact reverted
bug, and the real Markdown/web output was re-rendered showing the corrected "0 of 1 evaluated"
with the specification now listed under "established nothing."

**Observations for the judge (not acted on; the coordinator does not self-approve these into
the queue):**

1. `CheckRun.engine_version` has no test asserting the literal bumped value — both call sites
   assert only `assert run.engine_version` (truthy). Reverting the version bump alone leaves
   `make verify` green; nothing in the permanent suite would catch a silent revert.
2. The running compose stack's image is stale (`cadgpt-engine==0.1.0` inside the container,
   the old `ReasonCode` set) — a tenant hitting the live stack today still gets the pre-fix
   PASS. Deployment/rebuild, not a code defect.
3. `judge()` is a public export of `cadgpt_engine` and, called directly with
   `has_requirements=False, failed=5`, now returns INDETERMINATE and hides a FAIL — unreachable
   through `_specification`'s real call site, but not defended against as a library contract.
4. `.gitignore` and `cadgpt-logo.svg` are dirty in the working tree, predate this task, and are
   unrelated to it (present at session start, tied to the separate
   `feat/inbr-regulations-pipeline` branch).
