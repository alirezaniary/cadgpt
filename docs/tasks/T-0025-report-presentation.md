# T-0025 — Coverage before findings, findings ordered by severity, and a status filter that cannot hide an unknown

**Phase:** 3 — What the first real user needs   **Status:** built — review outstanding
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

**`make verify` — clean.**

```
$ make verify
uv run ruff check .
All checks passed!
uv run ruff format --check .
151 files already formatted
uv run mypy packages/engine/src services/api/cadgpt
Success: no issues found in 138 source files
uv run lint-imports --no-cache
Contracts: 5 kept, 0 broken.
uv run pytest
........................................................................ [ 43%]
........................................................................ [ 87%]
....................                                                     [100%]
164 passed, 18 warnings in 2.69s
cd services/web && pnpm install --frozen-lockfile && pnpm run verify
> @cadgpt/web@0.1.0 verify
> pnpm run lint && pnpm run typecheck && pnpm run build
> eslint .
> tsc -b --noEmit
> tsc -b && vite build
vite v6.4.3 building for production...
✓ 105 modules transformed.
dist/index.html                   0.40 kB │ gzip:  0.27 kB
dist/assets/index-B_JBma_I.css    4.14 kB │ gzip:  1.40 kB
dist/assets/index-7ctlpLl8.js   305.07 kB │ gzip: 95.29 kB │ map: 1,287.04 kB
✓ built in 1.71s
```

**Real path — `make up` then `make e2e` against the running compose stack (`web`
rebuilt to pick up the `ReportView.tsx` change).**

```
$ make e2e
cd services/web && pnpm exec playwright install chromium && pnpm run e2e
> playwright test
Running 1 test using 1 worker
  ✓  1 [chromium] › e2e/report.spec.ts:26:1 › a real check run reproduces 1 pass / 1 fail / 1
     indeterminate in the browser (7.6s)
  1 passed (8.8s)
```

Run a second time against the same, un-reset containers (confirms the harness is still
re-runnable, per T-0024's design):

```
$ pnpm run e2e
  ✓  1 [chromium] › ... (6.0s)
  1 passed (7.2s)
```

**Mutation proof — the new assertions are load-bearing, not tautologies that pass
regardless.** `git stash push -- services/web/src/components/ReportView.tsx` reverted the
production file to its pre-task state (coverage block, severity sort and status filter all
removed) while leaving the extended spec in place; rebuilt the `web` image
(`docker compose -f deploy/compose.yaml up -d --build web`) and reran:

```
$ pnpm run e2e
  ✘  1 [chromium] › e2e/report.spec.ts:26:1 › ...
  Error: expect(locator).toHaveAttribute(expected) failed
  Locator:  locator('section.report').locator('[data-testid="coverage"], li.spec').first()
  Expected: "coverage"
  Received: ""
    Call log:
      - waiting for locator(...)
        14 × locator resolved to <li class="spec">…</li>
           - unexpected value "null"
  1 failed
```

That is the coverage-before-findings assertion catching the reverted markup, exactly where
it should. `git stash pop` restored the fix, `web` was rebuilt again, and the suite passed
clean (pasted above, both runs after restoring).

**The four required DOM assertions, quoted from `services/web/e2e/report.spec.ts`:**

1. Coverage before the first specification, asserted on document order:
   ```ts
   const coverageThenSpec = report.locator('[data-testid="coverage"], li.spec');
   await expect(coverageThenSpec.first()).toHaveAttribute("data-testid", "coverage");
   ```
2. FAIL before INDETERMINATE in the DOM:
   ```ts
   const entityRows = report.locator('[data-testid="entity-row"]');
   await expect(entityRows).toHaveCount(2);
   await expect(entityRows.nth(0)).toHaveAttribute("data-status", "FAIL");
   await expect(entityRows.nth(1)).toHaveAttribute("data-status", "INDETERMINATE");
   ```
3. Filtered to FAIL only — the indeterminate row disappears, the indeterminate *count*
   does not, and the view says rows are withheld:
   ```ts
   await report.getByRole("checkbox", { name: "Indeterminate" }).uncheck();
   await expect(entityRows).toHaveCount(1);
   await expect(entityRows.first()).toHaveAttribute("data-status", "FAIL");
   await expect(report.locator(".count--indeterminate .count__value")).toHaveText("1");
   await expect(report.locator(".count--fail .count__value")).toHaveText("1");
   await expect(report.locator(".count--pass .count__value")).toHaveText("1");
   await expect(report.locator('[data-testid="filter-banner"]')).toContainText("Showing 1 of 2");
   ```
4. Screenshot: `services/web/e2e/screenshots/report.png`, committed, taken unfiltered
   (before the filter-toggle assertions run) and opened by me. It shows, top to bottom: the
   report header with a red **Fail** pill; a **Coverage** block reading "1 of 1
   specifications in this rule set were evaluated.", the three count tiles (Passed 1 /
   Failed 1 / Could not be determined 1) and "These were not checked. They are not
   passes."; the **Show** filter with **Fail** and **Indeterminate** both checked; then
   **Specifications**, with "Minimum clear door width 900 mm" (Fail pill), the requirement
   line "The OverallWidth shall be {'minInclusive': '900'}", and the two entity rows in
   order — **Fail** (`800.0` does not match) then **Indeterminate** (`None` is empty). No
   "established nothing" list appears, correctly: the one specification present matched 3
   elements and its applicability is `APPLIES`, so nothing in this run qualifies. That code
   path (`establishedNothing()` in `ReportView.tsx`) is exercised by
   `packages/engine/tests/test_check.py`'s existing coverage of `judge()` for the
   `matched == 0` and `DOES_NOT_APPLY`/`UNDETERMINED_APPLICABILITY` cases upstream in the
   engine, which is what the frontend condition reads; there is no separate fixture in this
   task's e2e run that puts a "nothing established" specification on screen; the second
   fixture `door_prohibited.ids` mentioned in the task's context was added by T-0026 and is
   not wired into `report.spec.ts` here, which the task's own "How to prove it ran" section
   does not ask for either.

**Wiring** — where the filter state is read, `services/web/src/components/ReportView.tsx`:

```ts
const [filter, setFilter] = useState<EntityFilter>(ALL_VISIBLE);
...
const filterActive = !filter.FAIL || !filter.INDETERMINATE;
const visibleCount = allEntities.filter((e) => isVisible(e, filter)).length;
...
const visibleEntities = orderedEntities.filter((e) => isVisible(e, filter));
```

**i18n — every new key exists in both catalogues** (`services/web/src/i18n/en.json`,
`services/web/src/i18n/fa.json`), confirmed by walking both JSON trees under `report.*`:

```
report.coverage.title
report.coverage.evaluated
report.coverage.nothingEstablished_one
report.coverage.nothingEstablished_other
report.filter.label
report.filter.showing
report.filter.allHidden
```

Identical key set in both files (existing `report.*` keys unchanged).

**What changed, file by file:**
- `services/web/src/components/ReportView.tsx` — coverage block (evaluated/total count,
  named list of specifications that established nothing, the three entity counts moved
  into it), stable severity sort (`bySeverity`, FAIL/INDETERMINATE/PASS) applied to both
  the specification list and each requirement's entity rows, and a FAIL/INDETERMINATE-only
  status filter with a "showing N of M" banner and a per-requirement "all hidden" notice.
  No PASS filter — `isVisible()` always returns `true` for a PASS entity, but the engine
  never itemises one, so the branch is unreachable in practice and exists only so the
  function's contract doesn't silently assume otherwise.
- `services/web/src/i18n/en.json`, `services/web/src/i18n/fa.json` — the seven keys above,
  in both catalogues.
- `services/web/src/styles.css` — `.coverage`, `.coverage__nothing`, `.filter`,
  `.filter__label`, `.filter__option`.
- `services/web/e2e/report.spec.ts` — the four assertions above, added to the existing
  T-0024 spec.
- `services/web/e2e/screenshots/report.png` — updated screenshot showing the new layout.

**NOT DONE:** nothing. The task's explicit "what explicitly does not change" list
(`packages/engine`, `services/api`, the scope-disclosure block) was left untouched —
confirmed by `git status`, which shows only the six files above changed.

## Review

**Review dispatched 2026-09-02, findings lost with the session.** The reviewer was running
when the coordinator session was ended for context reasons, so its report never landed. This
is the one case where re-dispatching a reviewer on the same task is correct: `docs/agents.md`
forbids a *second* review, and this task has not had a first one. Re-dispatch it before
marking this task done.

What it was asked to hunt, so the next dispatch does not have to re-derive it:

- **The filter is the dangerous surface.** The e2e spec drives exactly one state — unchecking
  Indeterminate and asserting the summary count stays 1. Unverified: both boxes unchecked,
  only Indeterminate checked, and a specification whose rows are all filtered away. Does
  anything then render as clean, empty or passing? Does a specification with no visible rows
  vanish silently, and does the coverage sentence still tell the truth in those states?
- **Severity ordering may be lucky rather than correct.** One specification holding one entity
  of each status is passed by almost any sort. Whether the implementation is genuinely stable
  and genuinely ranks FAIL → INDETERMINATE → PASS is not established by this fixture.
- **The coverage sentence is trivially complete on this fixture** — "1 of 1 specifications in
  this rule set were evaluated". The branch that matters is the one where specifications
  establish nothing (`DOES_NOT_APPLY`, `UNDETERMINED_APPLICABILITY`, `matched == 0`), and no
  test exercises it. `packages/engine/tests/fixtures/door_prohibited.ids` exists now and is the
  obvious input.
- **i18n:** new keys present in both catalogues, none orphaned, and the filter and coverage
  blocks not broken under `fa` — the app is RTL-native.
- The two preceding builders each produced a test that passed with its own fix reverted, and
  one false evidence claim. This task's mutation proof was not independently re-run by the
  coordinator.

**What the coordinator did verify before committing:** `make verify` green — ruff, 151 files
formatted, `mypy --strict` over 138 files, 5 import contracts kept, 164 tests. `git status`
shows only the six scoped files, engine and API untouched. The e2e spec's load-bearing
assertion is present and correct at `services/web/e2e/report.spec.ts:125-137` — unchecking
Indeterminate, then asserting the row count is 1, the remaining row is FAIL, and all three
summary counts still read 1. The screenshot was opened: coverage sits above the counts and the
findings, the filter offers Fail and Indeterminate and no PASS, and the FAIL row precedes the
INDETERMINATE row.

