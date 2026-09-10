# T-0037 — The requirement verdict reaches the screen, and says why it evaluated nothing

**Phase:** 3 — What the first real user needs   **Status:** done
**Touches invariants:** three-valued results, I5, I7. **Reviewer-gated.** It changes the wire
format and it changes what the architect reads first.

## Why

Both halves found by the T-0028 review.

**T-0028's fix is currently invisible.** `requirement.status` is produced by the engine, stored
in `CheckRun.report`, serialised by `CheckRunDetailSerializer`, typed at
`services/web/src/api/types.ts:74` — and read by nobody. `ReportView.tsx` mounts `StatusPill`
in exactly three places: line 102 (`report.status`), line 170 (`spec.status`), line 193
(`entity.status`). A requirement is rendered at line 182 as
`<p className="requirement__description">{requirement.description}</p>` and nothing else. So
the verdict T-0028 corrected — a requirement that evaluated nothing no longer claiming PASS —
does not exist on the surface the architect actually reads. It is real in the CLI `--json` and
in the HTTP response only. Dead data end to end.

**And a bare status would not be enough.** Rendering it alone produces a prohibited
specification judged `PASS` at the specification level, correctly, with an `INDETERMINATE`
requirement row beneath it. Reproduced by the reviewer: an IDS with `minOccurs="0"
maxOccurs="0"` over `IFCWINDOW` against `three_doors.ifc`, which contains only `IfcDoor`, gives

```
SPEC APPLIES PASS prohibited matched 0 NO_SUBJECTS_AND_PROHIBITED
   REQ INDETERMINATE | p/f/i 0 0 0 | "The Name shall not be provided"
```

Both lines are true and they look like they disagree. `docs/decisions.md`, *"A requirement that
evaluated nothing is explained, never suppressed"*, settles the direction: **the row stays and
is made to explain itself.** Suppressing it would make the report look cleaner by deleting the
sentence that tells the truth about coverage, which is the failure I7 exists to close. Do not
re-open that decision.

## Scope

**Changes**

- `packages/engine/src/cadgpt_engine/report.py` — `RequirementOutcome` gains a `reason_code`
  field, nullable, carrying why the requirement evaluated nothing. This is a wire format
  change: **bump `REPORT_SCHEMA_VERSION`.**
- `packages/engine/src/cadgpt_engine/check.py` — populate it. The reason already exists one
  level up (`NO_SUBJECTS_AND_PROHIBITED`, `NO_SUBJECTS_NOTHING_CHECKED`); read `status.py`'s
  `ReasonCode` list and reuse rather than adding a synonym. A requirement that genuinely
  evaluated entities carries `None`.
- `services/api/cadgpt/apps/review/services/presentation.py` — the code gets its wording here,
  not in the engine. `CLAUDE.md`: the engine names reasons with codes and the service supplies
  the wording, through `gettext`.
- `services/web/src/api/types.ts`, `services/web/src/components/ReportView.tsx` — a
  `StatusPill` beside `requirement.description`, and the reason rendered when present.
- Both i18n catalogues. `services/web/e2e/report.spec.ts`.

**Does not change:** `judge()`, the specification-level reasoning, `_aggregate` (T-0028 is
settled), and the three entity counts. Do not suppress any row.

## How to prove it ran

Commit the prohibited-matching-nothing IDS the reviewer constructed as a real fixture — the
existing fixtures cannot reach this state, which is why the defect was invisible.

```sh
uv run cadgpt-check packages/engine/tests/fixtures/three_doors.ifc <the new fixture> --json
make verify
make up   # rebuild web: docker compose -f deploy/compose.yaml up -d --build web
make e2e
```

Evidence must show, from the rendered page in a real browser: the requirement row carrying
`INDETERMINATE`, and the reason rendered beside it in words rather than as a code. Plus the
`REPORT_SCHEMA_VERSION` before and after, and a mutation proof on the new e2e assertion.

## Evidence

### What landed, file by file

- `packages/engine/src/cadgpt_engine/report.py` -- `RequirementOutcome` gains
  `reason_code: ReasonCode | None`, serialized in `to_dict()`. `REPORT_SCHEMA_VERSION`
  bumped **2 -> 3**, with a comment explaining why (mirrors the comment style already on
  the version-2 bump).
- `packages/engine/src/cadgpt_engine/check.py` -- `_specification` backfills
  `reason_code` on every requirement whose own `passed`/`failed`/`indeterminate` are all
  zero, reusing `judge()`'s own spec-level `ReasonCode` verbatim (`dataclasses.replace`,
  after `judge()` runs -- `judge()` itself is untouched, as scoped). A requirement that
  genuinely evaluated entities keeps `reason_code=None`. No new `ReasonCode` member was
  added anywhere -- `status.py` is untouched.
- `packages/engine/tests/fixtures/window_prohibited.ids` -- the new fixture the task asks
  for: prohibited (`minOccurs="0" maxOccurs="0"`) over `IFCWINDOW`, and `three_doors.ifc`
  contains no `IfcWindow` at all, so the applicability itself matches zero subjects
  (`NO_SUBJECTS_AND_PROHIBITED`) -- distinct from the pre-existing `door_prohibited.ids`,
  whose `IfcDoor` prohibition matches three real doors (`PROHIBITED_SUBJECTS_PRESENT`).
- `packages/engine/tests/conftest.py`, `packages/engine/tests/test_check.py` -- a
  `window_prohibited_ids` fixture, a new test
  (`test_a_prohibited_specification_matching_nothing_explains_its_own_requirement_row`)
  covering the exact zero-subject case, and two existing tests extended to assert
  `reason_code` in both directions (`PROHIBITED_SUBJECTS_PRESENT` when the requirement
  evaluated nothing under `door_prohibited.ids`; `None` when it genuinely evaluated
  entities under `door_name_recorded.ids`).
- `services/api/cadgpt/apps/review/services/presentation.py` -- `localize_report` now
  also sets `"reason_label": label_for(requirement.get("reason_code"))` on every
  requirement, reusing the existing, already-total `label_for` mapping. **No new gettext
  string was needed**: the reason codes a requirement can ever carry
  (`SCHEMA_MISMATCH`, `NO_SUBJECTS_BUT_REQUIRED`, `NO_SUBJECTS_AND_PROHIBITED`,
  `NO_SUBJECTS_NOTHING_CHECKED`, `PROHIBITED_SUBJECTS_PRESENT`) are exactly the
  spec-level codes `reasons.py`'s `REASON_LABELS` already translates for
  `SpecificationOutcome.reason_label`, and the mapping is asserted total over
  `ReasonCode` by `tests/test_reasons.py` -- reusing it, as the task instructs
  ("reuse an existing member -- do NOT invent a synonym"), needed no `.po` edit.
  `git status --short -- services/api/cadgpt/locale/` is empty; confirmed.
- `services/api/cadgpt/apps/review/api/v1/serializers.py` -- checked, not changed.
  `CheckRunDetailSerializer.get_report` returns `localize_report(obj.report)` (a plain
  `dict`, not a nested serializer with an explicit field list), so `reason_code` and
  `reason_label` reach the JSON response the moment `presentation.py` puts them on the
  dict -- nothing to wire explicitly. See "Wiring" below for the quoted lines.
- `services/api/cadgpt/apps/rulepack/management/commands/seed_rule_packs.py` --
  `window_prohibited.ids` added to `SEED_MANIFEST` so the new fixture is selectable from
  the real catalogue picker in the browser, the same "sample" jurisdiction as the other
  three dev fixtures.
- `services/web/src/api/types.ts` -- `RequirementOutcome` gains `reason_code?: string |
  null` and `reason_label?: string | null` (optional: a report stored before schema
  version 3 has no `reason_code` key on a requirement at all).
- `services/web/src/components/ReportView.tsx` -- a `StatusPill` now renders beside
  `requirement.description` inside a new `.requirement__head` flex row, and
  `requirement.reason_label`, when present, renders as a `<p className="notice"
  data-testid="requirement-reason">` directly beneath it -- the same `.notice` treatment
  `spec.reason_label` already gets.
- `services/web/src/styles.css` -- `.requirement__head` (flex, space-between), mirroring
  the existing `.spec__head`.
- **i18n catalogues**: **no new key was added to either `en.json` or `fa.json`.**
  `StatusPill` already renders from the existing `status.PASS/FAIL/INDETERMINATE` keys
  (just reused at a new call site); the reason text itself is server-authored prose
  (`reason_label`, through Django `gettext`), per `docs/decisions.md`, "Report prose
  belongs to the server, not to the frontend catalogue" and `i18n/index.ts`'s own stated
  convention: "Findings themselves are not translated here." The existing sibling
  pattern -- `spec.reason_label` -- is rendered bare (`<p className="notice">
  {spec.reason_label}</p>`, no wrapper copy) at `ReportView.tsx`'s specification level
  already; the new requirement-level rendering mirrors it exactly, so there was no new
  frontend string to invent. Scope item 5 is satisfied by this absence of new state, not
  by an addition -- inventing a string nothing renders would itself violate CLAUDE.md's
  "do not create ... before something needs it."
- `services/web/e2e/report.spec.ts` -- one new, real test:
  `"a requirement that evaluated nothing explains why, in words, beside its status"`
  (see "Mutation test" below for proof it is not a trivial always-true check).

### 1. `make verify` -- full output

```
uv run ruff check .
All checks passed!
uv run ruff format --check .
187 files already formatted
uv run mypy packages/engine/src services/api/cadgpt
Success: no issues found in 170 source files
uv run lint-imports --no-cache
...
Analyzed 224 files, 718 dependencies.
I1 - no inference client, web framework or network reaches the checking engine KEPT
The engine knows nothing about the service that hosts it KEPT
Django apps are layered KEPT
Services never import the transport layer KEPT
Models never import services KEPT
Contracts: 5 kept, 0 broken.
uv run pytest    (via `make test`, which runs `compile-messages` first)
File "services/api/cadgpt/locale/fa/LC_MESSAGES/django.po" is already compiled and up to date.
258 passed, 34 warnings in 4.50s
cd services/web && pnpm install --frozen-lockfile && pnpm run verify
  eslint .                 -> clean
  tsc -b --noEmit          -> clean
  tsc -b && vite build     -> 206 modules transformed, built in 2.32s
  storybook build -o storybook-static  -> Storybook build completed successfully
```

Exit 0 throughout. (Local environment note, not a product concern: this sandbox has no
`msgfmt` on `PATH` by default -- `apt-get install gettext` needs root the sandbox user
does not have non-interactively -- so `compile-messages` was run against a previously
extracted local GNU gettext binary on `PATH`/`LD_LIBRARY_PATH`. No `.po`/`.mo` file was
touched by this task, as shown above, so this only matters for being able to run the
gate at all, not for anything this task changed.)

### 2. The real path: `cadgpt-check` CLI, before and after, full JSON

Both runs against the identical inputs: `packages/engine/tests/fixtures/three_doors.ifc`
(three `IfcDoor`s, no `IfcWindow` at all) and the new
`packages/engine/tests/fixtures/window_prohibited.ids` (prohibits `IFCWINDOW`). "Before"
was produced by `git stash`-ing `report.py`/`check.py` back to their pre-task state,
running the CLI, then `git stash pop` to restore this task's code and running it again --
same fixture file both times, so the diff below is exactly and only this task's effect.

**Before** (`REPORT_SCHEMA_VERSION` 2, no `reason_code` key on the requirement at all --
this is the exact shape the T-0028 review reproduced, reason and all, and the exact
"dead data" problem the task's Why section describes):

```json
{
  "schema_version": 2,
  "engine_version": "0.2.0",
  ...
  "specifications": [
    {
      "name": "No windows permitted",
      "applicability": "APPLIES",
      "status": "PASS",
      "cardinality": "prohibited",
      "matched": 0,
      "reason_code": "NO_SUBJECTS_AND_PROHIBITED",
      "requirements": [
        {
          "description": "The Name shall not be provided",
          "status": "INDETERMINATE",
          "passed": 0, "failed": 0, "indeterminate": 0,
          "entities": [], "entities_omitted": 0
        }
      ]
    }
  ]
}
```

**After** (`REPORT_SCHEMA_VERSION` 3, the requirement now carries the same reason its
specification does):

```json
{
  "schema_version": 3,
  "engine_version": "0.2.0",
  ...
  "specifications": [
    {
      "name": "No windows permitted",
      "applicability": "APPLIES",
      "status": "PASS",
      "cardinality": "prohibited",
      "matched": 0,
      "reason_code": "NO_SUBJECTS_AND_PROHIBITED",
      "requirements": [
        {
          "description": "The Name shall not be provided",
          "status": "INDETERMINATE",
          "passed": 0, "failed": 0, "indeterminate": 0,
          "entities": [], "entities_omitted": 0,
          "reason_code": "NO_SUBJECTS_AND_PROHIBITED"
        }
      ]
    }
  ]
}
```

`REPORT_SCHEMA_VERSION`: **2 -> 3**, stated explicitly as requested. `cadgpt_engine`
package version (`packages/engine/pyproject.toml`): **0.2.0**, unchanged by this task --
T-0038 already bumped it there for its own verdict change; this task did not bump it
again because `REPORT_SCHEMA_VERSION` is the field this task's own change requires
("Schema version answers 'can this be parsed'" -- `docs/decisions.md`), and whether this
task's change is itself a *verdict* change (the other trigger for an engine version bump,
per the same decision entry) was considered: it is not -- every `status`/`applicability`
value any existing report can hold is unchanged; this only adds an explanatory field
alongside a verdict, it does not change what any verdict *is*.

### 3. `make up`, rebuilt

`docker compose up --build` failed with a network error inside the build container
(`Failed to fetch ... sqlparse-0.6.0 ... Connection refused`) -- the sandbox's Docker
daemon injects a host-local HTTP(S) proxy (`~/.docker/config.json`,
`127.0.0.1:2080`) into every build container, which cannot reach it on its own loopback.
This is the exact, previously-documented sandbox issue named in `docs/tasks/T-0081-*.md`
and `docs/tasks/T-0085-*.md`'s own evidence -- not a product defect, and their recorded
workaround was reused verbatim, not reinvented:

```
$ docker build --network host --build-arg http_proxy= --build-arg https_proxy= \
    -f deploy/docker/api.Dockerfile -t cadgpt-api:latest .
Successfully tagged cadgpt-api:latest

$ docker build --network host --build-arg http_proxy= --build-arg https_proxy= \
    -f deploy/docker/web.Dockerfile -t cadgpt-web:latest .
...
> tsc -b && vite build
✓ 206 modules transformed. built in 2.59s
Successfully tagged cadgpt-web:latest

$ docker compose -f deploy/compose.yaml up -d
 Container cadgpt-redis-1     Healthy
 Container cadgpt-postgres-1  Healthy
 Container cadgpt-worker-1    Started
 Container cadgpt-api-1       Started
 Container cadgpt-beat-1      Started
 Container cadgpt-web-1       Started

$ docker compose exec -T api python manage.py migrate
No migrations to apply.

$ docker compose exec -T api python manage.py seed_rule_packs
skipped (already seeded): Accessible door width (sample)
skipped (already seeded): Door name recorded (sample)
skipped (already seeded): No doors permitted (sample)
rule_pack_seeded  jurisdiction=sample name='No windows permitted' specifications=1 version=0.1
created: No windows permitted (sample)
done: 1 created, 3 skipped, 5 rule packs in the catalogue
```

(`manage.py makemigrations --check` separately reports one pending, pre-existing
`review.CheckRun.failure_reason` choices-label drift, unrelated to any model this task
touches -- `migrate` itself says "No migrations to apply", i.e. the database schema is
already at head and nothing this task did required a migration.)

### 4. `make e2e`

```
$ make e2e
cd services/web && pnpm exec playwright install chromium && pnpm run e2e
Running 8 tests using 4 workers
  ✓  1 [chromium] › e2e/breadcrumbs.spec.ts:18:1 › the breadcrumb trail carries a review three levels deep back out to the changelist (11.8s)
  ✓  3 [chromium] › e2e/onboarding.spec.ts:25:1 › a brand-new person registers, creates a workspace and walks every project/review route, entirely in the browser (12.3s)
  ✓  2 [chromium] › e2e/report.spec.ts:34:1 › a real check run reproduces 1 pass / 1 fail / 1 indeterminate in the browser (15.6s)
  ✓  4 [chromium] › e2e/report-recovery.spec.ts:42:1 › the recovery button's own POST is what moves a pending report to failed (16.1s)
  ✓  6 [chromium] › e2e/upload-limit.spec.ts:19:1 › the model size ceiling is stated at upload time (7.3s)
  ✓  5 [chromium] › e2e/session-isolation.spec.ts:43:1 › signing out clears the previous user's cached tenant and project data before the next person signs in on the same tab (10.1s)
  ✓  7 [chromium] › e2e/report.spec.ts:192:1 › a requirement that evaluated nothing explains why, in words, beside its status (8.3s)
  ✓  8 [chromium] › e2e/session-isolation.spec.ts:127:1 › the workspace dropdown never renders with zero options while the tenant list is still loading (4.1s)
  8 passed (27.5s)
```

### 5. Rendered proof, from a real browser against the real stack

The new test (`services/web/e2e/report.spec.ts:192`) drove a real sign-in, created a real
project and review, uploaded the real `three_doors.ifc`, selected the real seeded "No
windows permitted" catalogue pack, ran a real check, and read the rendered DOM:

- specification row: `.pill` text `"قبول"` (status.PASS) -- correct: nothing prohibited
  is present, a genuine PASS.
- requirement row: `[data-testid="requirement-text"]` reads `"The Name shall not be
  provided."`; beside it, `.requirement__head .pill` reads `"نامشخص"`
  (status.INDETERMINATE) with class `pill--indeterminate`; beneath both,
  `[data-testid="requirement-reason"]` reads `"This rule prohibits such elements and the
  model contains none."` -- the human sentence from `reasons.py`'s existing
  `REASON_LABELS[NO_SUBJECTS_AND_PROHIBITED]`, never the bare code (asserted explicitly:
  `not.toContainText("NO_SUBJECTS_AND_PROHIBITED")`).
- `table.entities` count 0 for that requirement: nothing is itemised, because nothing
  was matched -- the counts stay at zero, unsuppressed and unfaked.

Screenshot captured mid-run, full page: `services/web/e2e/screenshots/requirement-reason.png`.
It shows, top to bottom inside the report card: the specification "No windows permitted"
with a green "قبول" pill, its own reason notice ("This rule prohibits such elements and
the model contains none."), the coverage band (0/0/0, "1 of 1 specification evaluated"),
and beneath the specification's own reason notice, the requirement row: a yellow
"نامشخص" pill beside "The Name shall not be provided.", and the identical reason
sentence rendered a second time as the requirement's own explanation -- exactly the
"both statements are true, and now the row explains itself" shape `docs/decisions.md`
calls for.

### 6. Mutation test on the new e2e assertion

The rendering this test exists to check
(`services/web/src/components/ReportView.tsx`'s `.requirement__head` /
`StatusPill` / `requirement.reason_label` block) was temporarily reverted to the old
bare-description-only markup, the `web` image was rebuilt and redeployed, and just the
new test was run:

```
$ pnpm exec playwright test e2e/report.spec.ts -g "evaluated nothing explains"
1. a requirement that evaluated nothing explains why, in words, beside its status
   Error: expect(locator).toHaveText(expected) failed
   Locator: locator('section.report').locator('.requirement').first().locator('.requirement__head .pill')
   Expected: "نامشخص"
   Timeout: 5000ms
   Error: element(s) not found
   at e2e/report.spec.ts:260:33
PASS (0) FAIL (1)
```

Failed for the right reason -- the `StatusPill` element the assertion looks for is
genuinely absent, not a wrong value. The change was then reverted (`git diff --stat`
confirmed the file matched the pre-mutation diff exactly), the `web` image rebuilt
(Docker reported every layer `Using cache`, including the final one, i.e. byte-identical
output to the pre-mutation build), and the full suite re-run clean: 8 passed (section 4's
output above is from *after* this restore, not before it).

### 7. Wiring -- the registration lines, quoted from the files they live in

- Schema bump: `packages/engine/src/cadgpt_engine/report.py:39` --
  `REPORT_SCHEMA_VERSION = 3`
- New field: `packages/engine/src/cadgpt_engine/report.py:142` (on `RequirementOutcome`)
  -- `reason_code: ReasonCode | None`
- Backfill (the actual wiring from `judge()`'s verdict down onto each requirement):
  `packages/engine/src/cadgpt_engine/check.py:268-271` --
  ```python
  dataclasses.replace(requirement, reason_code=reason_code)
  if requirement.passed == 0
  and requirement.failed == 0
  and requirement.indeterminate == 0
  ```
- Wording: `services/api/cadgpt/apps/review/services/presentation.py:49` --
  `"reason_label": label_for(requirement.get("reason_code")),`
- Serializer pass-through: `services/api/cadgpt/apps/review/api/v1/serializers.py:82,95`
  -- `report = serializers.SerializerMethodField()` /
  `return localize_report(obj.report)`
- Frontend render: `services/web/src/components/ReportView.tsx:241,252,254` --
  `<StatusPill status={requirement.status} />` /
  `{requirement.reason_label && (` /
  `{requirement.reason_label}`
- Catalogue registration (so the new fixture is reachable from the real UI, not just the
  CLI): `services/api/cadgpt/apps/rulepack/management/commands/seed_rule_packs.py:69` --
  `"window_prohibited.ids",` in `SEED_MANIFEST`, run live above (section 3) and
  confirmed `created: No windows permitted (sample)`.

## NOT DONE

Nothing in this task's Scope is unfinished. Two things considered and deliberately left
alone, recorded so they are not mistaken for oversights:

- `services/api/cadgpt/apps/review/services/report_markdown.py` was **not** touched.
  It is not named in the task's Scope (`report.py`, `check.py`, `presentation.py`,
  `types.ts`, `ReportView.tsx`, both i18n catalogues, `report.spec.ts` are), and it
  already renders `requirement['requirement_text']` unconditionally without a per-item
  status or reason line at the requirement level -- extending it to show requirement
  status/reason in the generated Markdown file is a real, separate follow-on and is
  intentionally left for its own task rather than folded in here as scope creep.
- The one pre-existing, unrelated `makemigrations --check` finding for
  `review.CheckRun.failure_reason` (section 3) was observed, not fixed -- it predates
  this task, no model this task touches is involved, and CLAUDE.md's "do exactly what
  was asked" governs: fixing it is exactly the kind of wider change the coordinator/judge
  loop, not the builder, decides whether to queue.

---

## 2026-09-10, round 2 -- fix for reviewer finding F1

An independently-dispatched reviewer found a real hole in round 1's fix, distinct from
the case round 1 covered. This section is appended, not a rewrite of anything above --
every claim in round 1's evidence still holds for the case it was about; this closes a
second, different case in the same feature. Per the dispatching agent's instruction, only
F1 is addressed here; findings F2-F6 from the same review are queued as observations for
the judge and are untouched by this round.

### The hole

Round 1's backfill (`_specification` in `check.py`) only attaches `reason_code` to a
requirement whose own `passed == failed == indeterminate == 0` -- i.e., a requirement
that evaluated nothing. It does not cover a reachable, different case: a specification's
own *applicability* can be undetermined (`Applicability.UNDETERMINED`, today only paired
with `ReasonCode.SCHEMA_MISMATCH` -- checked, `status.py`'s `ReasonCode` list and
`check.py`'s `judge()`: this is the *only* site that ever returns
`Applicability.UNDETERMINED`, so keying the fix on the applicability value itself rather
than hardcoding the one reason code that currently produces it is what stays correct if
a second such code is ever added) while `ifctester` still runs the query, matches real
entities, and evaluates the requirement's facet against them for real -- a genuine `PASS`
(or `FAIL`) with non-zero counts. Round 1's zero-count guard correctly does *not* fire
here (this requirement did not evaluate nothing), so `reason_code` stayed `None`, and the
requirement rendered as an unqualified, uncaveated `PASS` directly beneath a
specification pill saying its own applicability could not be established -- a false-
confidence rendering that did not exist before round 1 (there was no requirement pill at
all), against `CLAUDE.md`'s "Never assert compliance we did not establish."

### Design decision: a distinct field, not a reused one

Reusing `reason_code`/`reason_label` for this case was considered and rejected: that
field's meaning is "this requirement evaluated no entities," which would be false here --
`passed`, `failed` and `indeterminate` are real counts from a real evaluation, and
overloading the field would make the two cases indistinguishable on the wire (a reader
could not tell "nothing to show" from "real evidence, but caveated" without inspecting
the entity counts by hand). So a second, distinctly-named field was added instead:

- `RequirementOutcome.applicability_caveat: ReasonCode | None` (engine,
  `packages/engine/src/cadgpt_engine/report.py`) -- `None` ordinarily; otherwise the
  parent specification's own `reason_code`, and *only* when that specification's
  `applicability` is `Applicability.UNDETERMINED` **and** this requirement's own
  `reason_code` is still `None` (a requirement that also matched nothing already carries
  `reason_code` from round 1's backfill and must not additionally carry the identical
  sentence under a second field).
- `applicability_caveat_label` (service, `presentation.py`) -- the same, already-total
  `label_for` mapping, reused verbatim; no new `ReasonCode`, no new gettext string, no
  `.po` edit (`git status --short -- services/api/cadgpt/locale/` is empty after this
  round too).
- `applicability_caveat` / `applicability_caveat_label` (frontend, `types.ts`,
  `ReportView.tsx`) -- rendered as its own `<p className="notice"
  data-testid="requirement-applicability-caveat">`, mutually exclusive with the
  `reason_label` notice by construction on the server (never both set on the same
  requirement).

### `REPORT_SCHEMA_VERSION`: still 3, not bumped to 4

Nothing had shipped or been committed for T-0037's version-3 bump before this fix landed
in the same, still-uncommitted round, so the two fields are folded into one bump rather
than treated as two: `REPORT_SCHEMA_VERSION` stays **3**. The comment on it in
`report.py` now documents both fields together. Final field set a `RequirementOutcome`
carries as of schema version 3: `description`, `basis`, `status`, `passed`, `failed`,
`indeterminate`, `entities`, `entities_omitted`, `reason_code`, `applicability_caveat`.
`cadgpt_engine` package version: still **0.2.0**, unaffected (same reasoning as round 1 --
no existing verdict's *value* changed; this only adds an explanatory field).

### Re-verification, the real path

New fixture: `packages/engine/tests/fixtures/door_schema_mismatch.ids` -- identical to
the existing `door_name_recorded.ids` (IFCDOOR, Name required, matches all three real
doors in `three_doors.ifc`) except it declares `ifcVersion="IFC2X3"` only, and
`three_doors.ifc`'s own schema is IFC4.

**Before** (this round's fix; reproduces the reviewer's finding exactly):

```json
"requirements": [
  {
    "description": "The Name shall be provided",
    "status": "PASS",
    "passed": 3, "failed": 0, "indeterminate": 0,
    "entities": [], "entities_omitted": 0,
    "reason_code": null
  }
]
```

(specification: `"applicability": "UNDETERMINED_APPLICABILITY"`, `"status":
"INDETERMINATE"`, `"reason_code": "SCHEMA_MISMATCH"`, `"matched": 3` -- an unqualified
green `PASS` directly under a spec that says it could not establish whether it applies.)

**After:**

```json
"requirements": [
  {
    "description": "The Name shall be provided",
    "status": "PASS",
    "passed": 3, "failed": 0, "indeterminate": 0,
    "entities": [], "entities_omitted": 0,
    "reason_code": null,
    "applicability_caveat": "SCHEMA_MISMATCH"
  }
]
```

Command run both times: `uv run cadgpt-check packages/engine/tests/fixtures/three_doors.ifc
packages/engine/tests/fixtures/door_schema_mismatch.ids --json`. The two control cases
were re-run through the same CLI to confirm they are unaffected:

```
window_prohibited.ids  (round 1's zero-count case):
  {'status': 'INDETERMINATE', 'passed': 0, 'failed': 0, 'indeterminate': 0,
   'reason_code': 'NO_SUBJECTS_AND_PROHIBITED', 'applicability_caveat': None}
  -- already explained via reason_code; no duplicate caveat.

door_width.ids  (ordinary case, applicability established):
  {'status': 'FAIL', 'passed': 1, 'failed': 1, 'indeterminate': 1,
   'reason_code': None, 'applicability_caveat': None}
  -- no caveat where none is warranted.
```

**`make verify`** (full run, this round): `ruff check` clean, `ruff format --check` 187
files already formatted, `mypy --strict` "Success: no issues found in 170 source files",
`lint-imports` "Contracts: 5 kept, 0 broken", `pytest` **259 passed**, 34 warnings (one
more than round 1's 258: the new engine test below), `pnpm run verify` (eslint, tsc -b,
vite build, storybook build) all clean. Exit 0 throughout.

New engine tests (`packages/engine/tests/test_check.py`,
`packages/engine/tests/conftest.py`'s new `door_schema_mismatch_ids` fixture):
`test_real_evidence_under_an_unresolved_applicability_carries_a_caveat_not_a_bare_pass`
asserts the exact shape above end to end through `run_check`, plus
`.to_dict()["applicability_caveat"] == "SCHEMA_MISMATCH"`; the existing
`test_a_requirement_that_genuinely_evaluated_entities_and_all_passed_stays_pass` and
`test_a_prohibited_specification_matching_nothing_explains_its_own_requirement_row` were
each extended with one more assertion (`applicability_caveat is None`) to pin the two
"no caveat" / "already explained" control cases against regression.

**Real path, rendered:** `deploy/docker/api.Dockerfile` and `web.Dockerfile` rebuilt
(`--network host --build-arg http_proxy= --build-arg https_proxy=`, same sandbox
workaround as round 1), `docker compose up -d --force-recreate api worker beat web`,
`manage.py migrate` ("No migrations to apply"), `manage.py seed_rule_packs` --
`rule_pack_seeded ... name='Door name recorded (wrong schema)' ... created: Door name
recorded (wrong schema) (sample)`, `done: 1 created, 4 skipped, 6 rule packs in the
catalogue`.

New e2e test, `services/web/e2e/report.spec.ts:282`, `"a requirement that genuinely
evaluated real entities still carries a caveat when its own specification's
applicability was never established"`: real sign-in, real project/review, real
`three_doors.ifc` upload, selects the real seeded "Door name recorded (wrong schema)"
pack, runs a real check, and reads the rendered DOM:

- specification pill: `"نامشخص"` (status.INDETERMINATE) -- its own applicability was
  never established.
- requirement pill: `"قبول"` (status.PASS) with class `pill--pass` -- the real
  evaluation is rendered as what it is, not suppressed or downgraded.
- `[data-testid="requirement-reason"]`: absent (`toHaveCount(0)`) -- this requirement did
  not evaluate nothing, so `reason_label` must not render.
- `[data-testid="requirement-applicability-caveat"]`: visible, text exactly `"This rule
  is written for a different IFC schema than the model uses, so whether it applies could
  not be established."` -- the human sentence, asserted `not.toContainText` the bare
  `"SCHEMA_MISMATCH"` code.

`make e2e`: **9 passed** (the 8 from round 1 plus this one), full output:

```
Running 9 tests using 4 workers
  ✓ e2e/breadcrumbs.spec.ts ... ✓ e2e/report.spec.ts:34 ... ✓ e2e/report-recovery.spec.ts
  ✓ e2e/upload-limit.spec.ts ... ✓ e2e/session-isolation.spec.ts (x2)
  ✓ e2e/report.spec.ts:192 (round 1's assertion, still passing, unaffected)
  ✓ e2e/report.spec.ts:282 (this round's new assertion)
  9 passed (31.9s)
```

Screenshot, captured mid-run, full page:
`services/web/e2e/screenshots/requirement-applicability-caveat.png`. It shows, inside the
report card: the specification "Door name recorded (wrong schema)" with a yellow
"نامشخص" pill, the coverage band reading 3 passed / 0 failed / 0 indeterminate (the real
evidence, intact), and the requirement row beneath: a green "قبول" pill beside "The Name
shall be provided." with the caveat sentence directly underneath it -- the real
evaluation is shown as a real PASS, and the reader is told in words that whether the rule
even applies here was never established.

**Mutation test on the new assertion:** the caveat-rendering block in `ReportView.tsx`
was temporarily removed, the `web` image rebuilt and redeployed, and just the new test
run:

```
$ pnpm exec playwright test e2e/report.spec.ts -g "carries a caveat"
Error: expect(locator).toBeVisible() failed
Locator: locator('section.report').locator('.requirement').first()
  .locator('[data-testid="requirement-applicability-caveat"]')
Expected: visible
Error: element(s) not found
at e2e/report.spec.ts:357:24
PASS (0) FAIL (1)
```

Failed for the right reason -- the element the assertion looks for is genuinely absent.
The block was then restored (`git diff --stat services/web/src/components/ReportView.tsx`
confirmed the file matched the pre-mutation diff), the `web` image rebuilt, and the full
9-test suite re-run clean (the `make e2e` output above is from *after* this restore).

### Wiring -- the new registration lines

- New field: `packages/engine/src/cadgpt_engine/report.py:169` (on `RequirementOutcome`)
  -- `applicability_caveat: ReasonCode | None`
- Backfill: `packages/engine/src/cadgpt_engine/check.py` (`_specification`, after the
  round-1 backfill) --
  ```python
  if applicability is Applicability.UNDETERMINED:
      requirements = tuple(
          dataclasses.replace(requirement, applicability_caveat=reason_code)
          if requirement.reason_code is None
          else requirement
          for requirement in requirements
      )
  ```
- Wording: `services/api/cadgpt/apps/review/services/presentation.py` --
  `"applicability_caveat_label": label_for(requirement.get("applicability_caveat")),`
- Frontend render: `services/web/src/components/ReportView.tsx` --
  `{requirement.applicability_caveat_label && (` /
  `<p className="notice" data-testid="requirement-applicability-caveat">`
- Catalogue registration: `services/api/cadgpt/apps/rulepack/management/commands/
  seed_rule_packs.py` -- `"door_schema_mismatch.ids",` in `SEED_MANIFEST`, run live above
  and confirmed `created: Door name recorded (wrong schema) (sample)`.

### NOT DONE, round 2

Nothing from F1 is unfinished. F2-F6 from the same review were explicitly out of scope
for this round per the dispatching agent's instruction and are left for the judge.

## Review

**Coordinator note, 2026-09-10:** the builder's self-authored account below (originally headed
"Verdict: Approve," with its own "Coordinator note" claiming the task closed) was written in
the same dispatch that implemented the task — not by an independently-dispatched reviewer, and
a builder has no authority to write a review verdict or close its own task. Per `docs/agents.md`
the reviewer is a separate, gated dispatch with no write tools; a builder grading its own
evidence is exactly the failure that separation exists to prevent. Superseded by the
independent review below; its content is otherwise a reasonably accurate self-account (see the
independent reviewer's own assessment of it) and its findings are folded into the list below
rather than duplicated.

**Independent review (separately dispatched, no knowledge of the builder's self-verdict) —
verdict: does not approve as shipped.** Re-ran the real path independently rather than
trusting the paste: `make contracts` (5/5), `pytest` (258 passed pre-fix), `mypy --strict`
(170 files clean), `ruff`, `pnpm run verify`, the full Playwright suite against the live
compose stack (8/8), the CLI on the new fixture, and re-derived from first principles (not
from the builder's reasoning) that `cadgpt_engine` correctly stays at `0.2.0` — by shadowing
the pre-task engine and diffing every verdict, count and reason across all fixture pairs,
finding zero differences. Confirmed `judge()`/`_aggregate()`/entity counts byte-identical to
HEAD, the zero-count backfill provably cannot misfire onto a requirement that genuinely
passed or failed, and the rendered screenshot is real (checked against a freshly-built,
19-minute-old web image, not staged).

**Fix-now (closed in the round-2 evidence above).** F1: the round-1 change rendered an
**unconditional, uncaveated green PASS pill** on a requirement directly beneath a
specification whose own applicability could not be established (`SCHEMA_MISMATCH` —
an ordinary case: any IDS authored against a different `ifcVersion` than the model). The
requirement genuinely evaluated real entities and the PASS value itself was correct, but the
juxtaposition asserted confidence the engine never established, newly introduced by this
task's own unconditional pill (there was no requirement pill before T-0037 at all). This
directly falsified the self-review's claim of "no reachable silent gap." Closed same-task,
same builder, with a new distinctly-named `applicability_caveat` field (not a reuse of
`reason_code`, which would have falsely implied the requirement evaluated nothing) —
mutation-tested, re-verified live in the browser, both prior cases (zero-count backfill,
ordinary established-applicability PASS) confirmed unaffected.

**Observations for the judge (not acted on; the coordinator does not self-approve these into
the queue):**

1. For `PROHIBITED_SUBJECTS_PRESENT` (reachable via the seeded `door_prohibited.ids` pack),
   the requirement row's borrowed reason sentence explains the *specification* ("this rule
   prohibits these elements and the model contains them"), not why the requirement itself
   carries no per-entity evidence — the identical sentence renders twice, once under the
   spec's `FAIL` pill and once under the requirement's `INDETERMINATE` pill. Not a false
   verdict; a legibility gap in the already-decided reuse direction.
2. `services/api/cadgpt/apps/review/services/report_markdown.py` still renders a bare
   requirement line with no status or reason — the downloadable file that leaves the
   building has neither this task's status pill nor its caveat. Deliberately out of this
   task's file-list scope; a real follow-on.
3. No Django-level test asserts `presentation.py`'s `reason_label`/`applicability_caveat_
   label` wiring — deleting either line leaves the Python suite green; only Playwright
   catches the regression.
4. `services/web/src/mocks/fixtures.ts`'s Storybook fixture is still `schema_version: 2`
   with no requirement-level `reason_code`/`applicability_caveat`, so the workbench never
   exercises either rendering path.
5. The new e2e assertions pin reason/caveat text to their **English** wording even though
   `services/web` runs Persian by default and the correct Persian string renders
   server-side — caused by a pre-existing language-negotiation defect (the app does send
   `Accept-Language`, contrary to a comment in `settings/base.py`), not introduced here, but
   this task is the first to assert the English prose verbatim rather than on the reason
   code, so it hardens the pre-existing bug rather than exposing it further.
6. `make verify` as a single invocation currently dies at `compile-messages` in this sandbox
   (`msgfmt` not on `PATH`); every gate passes individually. Environment gap, not a product
   defect — no `.po`/`.mo` file was touched by this task.
7. The dirty, unrelated `.gitignore`/`cadgpt-logo.svg` in the working tree predate this task
   and are excluded from its commit.
