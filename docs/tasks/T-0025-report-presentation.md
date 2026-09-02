# T-0025 — Coverage before findings, findings ordered by severity, and a status filter that cannot hide an unknown

**Phase:** 3 — What the first real user needs   **Status:** done
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
   elements and its applicability is `APPLIES`, so nothing in this run qualifies.

   **Correction (fix-now round, F3):** the paragraph originally here claimed that
   `establishedNothing()` in `ReportView.tsx` "is exercised by
   `packages/engine/tests/test_check.py`'s existing coverage of `judge()`". That claim was
   false on three counts, per the review verdict below: `test_check.py` contains no
   reference to `judge`, `DOES_NOT_APPLY` or `UNDETERMINED` at all — that coverage is in
   `packages/engine/tests/test_judgement.py` (`judge` imported at line 11, the
   `DOES_NOT_APPLY`/`UNDETERMINED` cases parametrised from line 17); a Python test cannot
   exercise a TypeScript function under any reading, the two run in different languages and
   different processes; and, substantively, the frontend's `establishedNothing()` at the
   time did not mirror `judge()`'s reasoning at all — it read `spec.matched === 0` directly,
   which the fix-now round's F2 identifies as wrong (it named a specification the engine
   judged FAIL, `NO_SUBJECTS_BUT_REQUIRED`, as having established nothing). What was actually
   true at the time: no test anywhere, Python or TypeScript, exercised
   `establishedNothing()`'s zero-match branch, because this task's own e2e fixture
   (`door_width.ids`, one specification, matched 3) could not reach it — the single
   specification present has `applicability APPLIES` and `matched === 3`, so the branch
   never ran. The fix-now round's new fixture, `services/web/e2e/fixtures/nothing_established.ids`,
   is what closes that gap; see the Fix-now evidence section below.

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


---

## Review verdict — 2026-09-02, the first and only review of this task

Dispatched on opus against the hunt list recorded above. It earned its dispatch: the two
surfaces the hunt list named as unverified — the coverage sentence and the `establishedNothing`
branch — were both wrong, and neither was reachable from this task's fixture. The reviewer
reproduced both by running the real engine over two constructed IDS files rather than by
reading the code.

Six of the reviewer's suspicions did not survive its own reading and were dropped: the four
undriven filter states (nothing renders as clean, empty or passing in any of them; a
specification with all rows hidden still renders with its pill, matched count and reason),
`INDETERMINATE` reading as `PASS` under filtering (impossible — the count band reads payload
fields, and `classify()` never returns `PASS`, so the unreachable PASS branch is correctly
noted), `bySeverity` mutating props or sorting unstably (it copies before sorting and is
stable and correct at both call sites over a shuffled seven-item input), the mutation proof
being fabricated (it reproduces byte-for-byte, and the coverage assertion is genuinely the
first to fail against `aa03fb4^`), the scope violation (nothing under `packages/engine` or
`services/api` was touched), and the screenshot (opened; it matches its description).

### FIX NOW — three findings

**F1. The coverage sentence is a constant, not a measurement.** `ReportView.tsx:59-62, 86`.
`specifications_passed + specifications_failed + specifications_indeterminate` is identically
`len(specifications)` for every report the engine can produce: `check.py:223-227` counts one
`Status` per specification over a three-member enum and `_aggregate`'s fallback is
`INDETERMINATE`, so there is no fourth outcome. Numerator and denominator are the same number
by construction. Reproduced on a two-specification IDS where one matches nothing:

```
spec: Minimum clear door width 900 mm | applicability: APPLIES        | status: FAIL          | matched: 3
spec: Wall fire rating                | applicability: DOES_NOT_APPLY | status: INDETERMINATE | matched: 0

frontend sentence => '2 of 2 specifications in this rule set were evaluated.'
establishedNothing() names: ['Wall fire rating']
```

The headline claims full coverage while the block directly beneath it names a specification
that checked nothing. A run where 79 of 80 provisions matched nothing still reads "80 of 80".
This is `prd.md` §5.7 exactly — *"coverage improves by narrowing applicability while checking
less, and the number that looks like progress is the one that hides the retreat"* — and it is
the one thing this task's own Scope said the sentence must never do. It is load-bearing beyond
the SPA: `docs/decisions.md` records this presentation as the specification the Markdown
generator implements, so it would propagate into the deliverable file.

**F2. A specification the engine judged a definite FAIL is named under "established nothing".**
`ReportView.tsx:35-37`. `judge()` (`check.py:129-135`) returns `(APPLIES, FAIL,
NO_SUBJECTS_BUT_REQUIRED)` when `matched == 0` and cardinality is `required` — required
elements are *absent*, which is an established violation, not an absence of evidence. The
`matched === 0` disjunct swallows it. Reproduced with `minOccurs="1"`:

```
spec: Wall fire rating | app: APPLIES | status: FAIL | matched: 0 | reason: NO_SUBJECTS_BUT_REQUIRED
establishedNothing() names: ['Wall fire rating']
```

The coverage block then says the specification established nothing while the findings list
below shows it with a red Fail pill — a coverage statement contradicting the verdict it sits
above, which is the same failure `check.py:87-95` was written to prevent for requirement
lines, and it understates a real finding to a plan reviewer.

**Correction to this task's own Scope §1.** Scope §1 above prescribed the
`DOES_NOT_APPLY | UNDETERMINED_APPLICABILITY | matched == 0` criterion verbatim. That
criterion is wrong for the reason in F2 and the builder implemented what was written. The
criterion is corrected here and this correction, not Scope §1, is what the fix implements.

**F3. The evidence block contains a false claim.** Lines 239-243 above assert that
`establishedNothing()` is exercised by `packages/engine/tests/test_check.py`'s coverage of
`judge()`. `test_check.py` contains no reference to `judge`, `DOES_NOT_APPLY` or
`UNDETERMINED` — that coverage is in `test_judgement.py:17`; a Python test cannot exercise a
TypeScript function under any reading; and per F1 and F2 the frontend condition does not
mirror `judge()` at all. Running the real engine against the branch the claim says is covered
is precisely what surfaced both defects. A cheaper adjacent claim stood in for missing
evidence.

### QUEUED, not fixed here

Q1 filter-banner denominator conflates the filter's hiding with the engine's `entities_omitted`
cap; Q2 one out-of-vocabulary status makes the severity comparator non-transitive and silently
unsorts the whole list; Q3 non-unique React key on entity rows when `global_id` is null;
Q4 a partially-filtered specification gives no local signal; Q5 RTL is claimed but never
rendered under `fa` in any test; Q6 `{spec.cardinality}` renders a raw untranslated payload
value. Carried into `docs/plan.md` as T-0034, T-0035 and T-0036.

## Fix-now round — what the builder must land

Three changes, in `services/web/src/components/ReportView.tsx`, its two i18n catalogues if the
wording moves, and `services/web/e2e/report.spec.ts`. Nothing else.

1. **The coverage numerator must be a measurement.** It must exclude the specifications that
   established nothing, or the sentence must stop claiming evaluation. Whichever is chosen,
   the sentence and the "established nothing" block must be arithmetically consistent with
   each other on the same screen, and the sentence must never imply that what was not
   evaluated was fine.
2. **`establishedNothing()` must never name a specification the engine judged FAIL.** A
   `matched == 0` specification whose status is FAIL is a real finding — required elements are
   absent — not an absence of evidence. Drive the predicate off the specification's
   `reason_code` where the payload carries one, in preference to re-deriving the engine's
   judgement in TypeScript; `judge()` in `check.py` is the authority and the frontend must not
   hold a second, divergent copy of it.
3. **A test that reaches the branch.** The e2e fixture cannot reach it — that is why this
   defect shipped. Add a fixture with a specification that matches nothing (the reviewer built
   one; build it as a committed fixture, do not leave it ad hoc) and assert both F1 and F2 from
   the rendered page: the sentence does not read "N of N", and the FAIL specification is not
   named as having established nothing.

## Fix-now evidence

Builder round dispatched against the "Review verdict" and "Fix-now round" sections above.
Three changes landed in `services/web/src/components/ReportView.tsx`: `establishedNothing()`
now reads the two reason codes `judge()` pairs with a non-`APPLIES` applicability
(`SCHEMA_MISMATCH`, `NO_SUBJECTS_NOTHING_CHECKED`) instead of `applicability !== "APPLIES" ||
matched === 0`, and `evaluated` is now `specifications.length - nothingEstablished.length`
instead of the always-equal-to-the-total sum. No i18n wording changed (see key parity below).
A new fixture, `services/web/e2e/fixtures/nothing_established.ids`, and a second
rule-set/review flow appended to the existing `report.spec.ts` test reach the branch neither
F1 nor F2 could be caught in before.

### 1. `make verify`

Clean, engine and API untouched by this round (the 166 passed here include the T-0028
engine work already in the tree, which this task does not touch):

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
........................................................................ [ 86%]
......................                                                   [100%]
166 passed, 18 warnings in 3.32s
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
dist/assets/index-BSJJyq8C.js   305.09 kB │ gzip: 95.33 kB │ map: 1,288.90 kB
✓ built in 2.16s
```

### 2. `make up` (already running), `web` rebuilt, `make e2e`

`docker compose -f deploy/compose.yaml up -d --build web` was run against the already-running
compose stack. This project's compose build groups `api` and `web` together (the `--build web`
invocation rebuilt and recreated both `cadgpt-api-1` and `cadgpt-web-1`; `postgres`, `redis`
and `worker` were left alone) — noted here because it means the `api` container picked up
whatever was on disk under `services/api` and `packages/engine` at build time too, not just
the `web` change. `packages/engine` was not edited by this round; the working tree's
uncommitted T-0028 engine changes are the other agent's and were left alone throughout.

```
$ docker compose -f deploy/compose.yaml up -d --build web
...
 api  Built
 web  Built
 Container cadgpt-api-1  Recreated
 Container cadgpt-web-1  Recreated
 Container cadgpt-api-1  Started
 Container cadgpt-web-1  Started

$ make e2e
cd services/web && pnpm exec playwright install chromium && pnpm run e2e
> @cadgpt/web@0.1.0 e2e
> playwright test
Running 1 test using 1 worker
  ✓  1 [chromium] › e2e/report.spec.ts:40:1 › a real check run reproduces 1 pass / 1 fail / 1
     indeterminate in the browser (16.2s)
  1 passed (18.0s)
```

Run a second time against the same, un-reset containers (T-0024's re-runnability property
still holds):

```
$ pnpm run e2e
  ✓  1 [chromium] › ... (13.3s)
  1 passed (14.7s)
```

### 3. Mutation proof

Two separate reverts, each rebuilding `web` (`docker compose -f deploy/compose.yaml up -d
--build web`) and running the suite against the real stack, then restored and reverified.

**F1 reverted** — `evaluated` put back to
`specifications_passed + specifications_failed + specifications_indeterminate`, predicate
(F2's fix) left in place:

```
$ make e2e
  ✘  1 [chromium] › e2e/report.spec.ts:40:1 › ...
  Error: expect(locator).toHaveText(expected) failed
  Locator:  locator('section.report').locator('[data-testid="coverage"] > p').first()
  Expected: "2 of 3 specifications in this rule set were evaluated."
  Received: "3 of 3 specifications in this rule set were evaluated."
    Call log:
      - Expect "toHaveText" with timeout 5000ms
        14 × locator resolved to <p>3 of 3 specifications in this rule set were evalu…</p>
  1 failed
```

Exactly the pre-fix bug reproduced live: with the old numerator, "Wall count required"
(FAIL, matched 0) and "Wall fire rating recorded" (INDETERMINATE, matched 0) both still
count as "evaluated" because the sum is definitionally the total, so the sentence claims
full coverage while the block beneath it names a specification that established nothing.

**F1 restored, `web` rebuilt, reran clean** (folded into section 2's runs above — the
restored file is what produced both passing runs pasted there).

**F2 reverted** — `establishedNothing()` put back to
`spec.applicability !== "APPLIES" || spec.matched === 0`, F1's fix left in place. This
regression corrupts the F1 assertion too, since `evaluated` is derived from the same
predicate; that combined failure was captured first:

```
$ make e2e
  ✘  1 [chromium] › e2e/report.spec.ts:40:1 › ...
  Error: expect(locator).toHaveText(expected) failed
  Locator:  locator('section.report').locator('[data-testid="coverage"] > p').first()
  Expected: "2 of 3 specifications in this rule set were evaluated."
  Received: "1 of 3 specifications in this rule set were evaluated."
  1 failed
```

To isolate the F2-specific assertion on its own, the F1 coverage-sentence assertion was
temporarily disabled in a local copy of the spec (not committed) and the suite rerun
directly against the same rebuilt `web`:

```
$ pnpm run e2e
  ✘  1 [chromium] › e2e/report.spec.ts:40:1 › ...
  Error: expect(locator).toHaveCount(expected) failed
  Locator:  locator('section.report').locator('[data-testid="coverage-nothing-established"]').locator('li')
  Expected: 1
  Received: 2
    Call log:
      - Expect "toHaveCount" with timeout 5000ms
        14 × locator resolved to 2 elements
  1 failed
```

With the old predicate, both zero-match Wall specifications are named as "established
nothing" — including "Wall count required", the one the engine judged a definite FAIL. That
is exactly F2.

**F2 restored** (`spec.reason_code !== null && NOTHING_ESTABLISHED_REASONS.has(...)`), the
temporary spec edit discarded, `web` rebuilt, suite reran clean (the two passing runs in
section 2 above are from this restored state — `git status` at the end of this round shows
only the four files listed at the top of this section changed, confirmed below).

### 4. Screenshot

`services/web/e2e/screenshots/report.png`, regenerated by this round's runs, opened and
inspected directly. It is the same scenario as the original T-0025 evidence (the
`door_width.ids` review, screenshotted before the filter-toggle assertions and before the
second, `nothing_established.ids` review is created later in the same test) — top to
bottom: report header with a red **Fail** pill; **Coverage** block reading "1 of 1
specifications in this rule set were evaluated." (evaluated = 1 - 0, since the one
specification present has `reason_code: null` — not in `NOTHING_ESTABLISHED_REASONS` —
so `nothingEstablished.length` is 0 and the arithmetic still lands on "1 of 1" correctly
for this fixture); the three count tiles (Passed 1 / Failed 1 / Could not be determined 1)
and "These were not checked. They are not passes."; no "established nothing" block, correctly,
since nothing in this fixture qualifies; the **Show** filter with **Fail** and
**Indeterminate** both checked; then **Specifications**, "Minimum clear door width 900 mm"
(Fail pill), the requirement line "The OverallWidth shall be {'minInclusive': '900'}", and
the two entity rows in order — **Fail** (`800.0` does not match) then **Indeterminate**
(`None` is empty). The F1/F2 branch (the second, `nothing_established.ids` review) is
exercised later in the same test via DOM assertions, not a second screenshot — the task's
"How to prove it ran" section does not ask for one there.

### 5. i18n key parity

This round changed no wording — F1 and F2 are pure logic changes to `establishedNothing()`
and `evaluated` in `ReportView.tsx`; the existing `report.coverage.*` strings are reused
unchanged. Confirmed no i18n diff: `git diff --stat services/web/src/i18n/en.json
services/web/src/i18n/fa.json` is empty.

`report.*` keys, both catalogues, walked from the JSON trees (identical sets, 18 keys each):

```
report.coverage.evaluated
report.coverage.nothingEstablished_one
report.coverage.nothingEstablished_other
report.coverage.title
report.engine
report.failed
report.filter.allHidden
report.filter.label
report.filter.showing
report.indeterminate
report.indeterminateNote
report.matched
report.nothingChecked
report.omitted
report.passed
report.schema
report.specifications
report.summary
```

### What changed, file by file

- `services/web/src/components/ReportView.tsx` — `establishedNothing()` now reads
  `spec.reason_code` against `NOTHING_ESTABLISHED_REASONS = {SCHEMA_MISMATCH,
  NO_SUBJECTS_NOTHING_CHECKED}` instead of `applicability !== "APPLIES" || matched === 0`;
  `evaluated` is now `report.specifications.length - nothingEstablished.length` instead of
  `specifications_passed + specifications_failed + specifications_indeterminate`.
- `services/web/e2e/fixtures/nothing_established.ids` — new, committed. Three
  specifications against `three_doors.ifc`: one that matches all 3 doors and passes, one
  optional-cardinality spec against `IfcWall` (absent from the fixture model) that
  genuinely establishes nothing, and one required-cardinality spec against the same absent
  `IfcWall` that is a real, established FAIL. Placed under `services/web/e2e/fixtures/`
  rather than `packages/engine/tests/fixtures/` to stay entirely inside this round's
  allowed scope and clear of the other agent's in-progress engine work.
- `services/web/e2e/report.spec.ts` — extended with a second rule-set/review flow using the
  new fixture, asserting the coverage sentence ("2 of 3", not "3 of 3"), that
  "established nothing" names exactly "Wall fire rating recorded" and never "Wall count
  required", and that the latter still renders as a Fail finding in the specification list.
- `services/web/e2e/screenshots/report.png` — regenerated by this round's e2e runs.
- `docs/tasks/T-0025-report-presentation.md` — this section, and the F3 correction to the
  original evidence block's false claim about `test_check.py` coverage.

**NOT DONE:** nothing. `git status --porcelain` at the end of this round:

```
 M docs/tasks/T-0025-report-presentation.md
 M services/web/e2e/report.spec.ts
 M services/web/e2e/screenshots/report.png
 M services/web/src/components/ReportView.tsx
?? services/web/e2e/fixtures/
```

(The untracked `docs/tasks/T-003*.md` files and the modified files under `packages/engine/`
visible in a full `git status` are the coordinator's and the other agent's respectively, not
this round's — left untouched throughout, as instructed.)
