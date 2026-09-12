# T-0041 — A verdict is reachable without the statement of what was checked

**Phase:** 3 — What the first real user needs   **Status:** done
**Touches invariants:** I7. **Reviewer-gated.**

## Why

Found by the T-0029 review, one level up from where that task was looking.

T-0029 put the I7 disclosure at the top of the report: this checked the model, not the drawing
set your office submits. But the report is not the only place a verdict appears. The reviews
list renders the outcome before anyone opens anything:

```
three-doors-1788369893695
three_doors.ifc
                                    Complete   [Fail]   [Run check]   [Summary]
1 / 1 / 1
```

A status pill and three counts, with no statement of what was checked. On a clean run that row
is a compliance-shaped signal — a green pill and a row of numbers — and it is the surface a
reader most plausibly screenshots into an email or pastes into a message to a colleague. The
disclosure two clicks away does not travel with it.

`prd.md` §5.7 is not scoped to the report view: *every report names the model it checked*, and
I7 forbids letting "the model complies" be read as "the submission complies". A verdict that
travels without its scope is the same failure the disclosure exists to close, and it travels
more easily than the report does.

## Scope

**Corrected by the coordinator before dispatch, 2026-09-12, following the T-0029/T-0036
precedent for a drifted task file:** this task was written before T-0074 (done 2026-09-04)
replaced the single `ReviewsPage.tsx` changelist with `features/project/ProjectDetailPage.tsx`
(a project's own reviews table) and `features/review/ReviewDetailPage.tsx`. `ReviewsPage.tsx`
no longer exists. The premise is unchanged: `ProjectDetailPage.tsx`'s table renders a status
pill and per-run counts in a row that already names `review.model_file.original_name`, with
nothing stating that the verdict is *about the model* rather than about the drawing set the
office submits. The surface moved; the gap did not.

This task is **a decision followed by a small change**, and the decision is the substance: what
is the minimum that has to accompany a verdict wherever a verdict appears?

**Changes**

- `services/web/src/features/project/ProjectDetailPage.tsx` (and any other surface rendering a
  run's outcome outside the report) — the verdict does not appear without at least naming the
  artifact it describes. The row already names the model file; what is missing is that the
  outcome is *about the model*.
- Both catalogues — but note `docs/decisions.md`, *"Report prose belongs to the server, not to
  the frontend catalogue"*: if what you add is report prose it belongs on the server beside the
  disclosure. If it is a UI label on a list row, it is UI chrome and belongs in the frontend
  catalogues. Decide which this is and say why in the evidence.

**Explicitly not this task:** re-stating the whole disclosure paragraph on every row. A wall of
qualification on a list is dismissed as boilerplate and makes the real disclosure weaker, not
stronger. The question is the *minimum* that keeps the verdict honest in transit.

**Does not change:** the engine, the counts, the three-valued discipline, or the report view's
own disclosure (T-0029 owns that).

## How to prove it ran

`make verify`, `make up` with containers rebuilt, `make e2e`, and a screenshot of the reviews
list you have opened — with the verdict row visible — quoted in the evidence so the wording is
on the record. An assertion that the verdict and the scope statement appear together, and a
mutation proof that removing the scope statement fails it.

## Evidence

**Decision: UI chrome, in the frontend catalogues — not report prose.** `docs/decisions.md`'s
"report prose belongs to the server, not to the frontend catalogue" governs text that is
*rendered into a stored document* — the I7 disclosure (`disclosure.py`) is read at report-render
time by a Celery worker and, per that module's own docstring, has to stay reachable from a
worker that never has a browser or an i18n catalogue loaded. The reviews table has no such
constraint: it is rendered entirely client-side, by a component that already imports
`useTranslation` and already renders every other string on the row (`review.modelFile`,
`review.statusColumn`, `status.FAIL`) through the frontend catalogue. Nothing here is stored,
nothing is composed server-side with a filename interpolated in, and a Celery worker never
needs it. It is exactly the same kind of string as `review.outcomeScope`'s neighbours on the
row, so it goes where they go: `services/web/src/i18n/en.json` and `fa.json`, key
`review.outcomeScope`.

**What was added.** A new key, `review.outcomeScope` — en: *"Describes the model, not the
drawings"*, fa: *"دربارهٔ مدل است، نه نقشه‌ها"* — rendered directly beside the outcome pill
(`<span className="table__scope">`), not only in a column header, because the failure mode
named in `Why` is a *cropped screenshot of one row*: a header a few rows above the crop line
does not travel with it. Added to both places a run's outcome renders outside the report:
`ProjectDetailPage.tsx`'s reviews table (the primary target) and `ReviewDetailPage.tsx`'s own
run-history table (`and any other surface rendering a run's outcome outside the report` in the
Scope section) — the latter names its model once, above the table, not per row, so its outcome
cells needed the same tie-back. This is one short phrase, not the disclosure paragraph
restated — the thing the Scope section explicitly forbids.

### `make verify`

Full run, from the repo root, after putting a portable `msgfmt` (GNU gettext 0.21, already
present on this machine from an earlier task's own workaround, at
`/tmp/gettext-extract/usr/bin`) on `PATH`/`LD_LIBRARY_PATH` — the base image has
`gettext-base` but not full `gettext`, and this sandbox has no root to `apt-get install` it;
`compile-messages` needs `msgfmt` and this is the same non-destructive workaround, not a
change to any gate:

```
$ make verify
uv run ruff check .                → All checks passed!
uv run ruff format --check .       → 190 files already formatted
uv run mypy packages/engine/src services/api/cadgpt → Success: no issues found in 172 source files
uv run lint-imports --no-cache     → Contracts: 5 kept, 0 broken.
cd services/api && ... compilemessages → (fa.po already compiled and up to date)
uv run pytest                      → 292 passed, 34 warnings in 5.00s
cd services/web && pnpm run verify:
  lint      → 0 errors, 2 warnings (pre-existing, in ReportView.tsx/main.tsx, untouched by this task)
  typecheck → clean
  build     → ✓ built in 2.71s
  build-workbench (storybook build) → completed successfully
  test-unit → 1 file, 2 tests passed
  test-storybook → 9 files, 35 tests passed
```

### Mutation proof

Added a `play` function to `ProjectDetailPage.stories.tsx`'s `Populated` story (Storybook's
interaction tests, wired into `pnpm run verify` as `test-storybook`) that opens the row
containing `fx.checkedReview` (whose fixture outcome is `FAIL`) and asserts, within that one
`<tr>`, both the pill text (`status.FAIL` → "مردود") and the scope statement
(`review.outcomeScope` → "دربارهٔ مدل است، نه نقشه‌ها") are present.

With the fix in place:

```
$ pnpm run test-storybook
 Test Files  9 passed (9)
      Tests  35 passed (35)
```

With the scope `<span>` removed from `ProjectDetailPage.tsx` (mutation):

```
$ pnpm run test-storybook
 ❯ |storybook (chromium)| .../ProjectDetailPage.stories.tsx (4 tests | 1 failed)
   × Populated
TestingLibraryElementError: Unable to find an element with the text:
دربارهٔ مدل است، نه نقشه‌ها.
<tr>
  <td><a ...>کنترل معماری — فاز ۲</a></td>
  <td class="ltr muted">niavaran-tower-A3.ifc</td>
  <td>تمام‌شده</td>
  <td><span class="pill pill--fail">مردود</span></td>
  <td class="muted">۱۴ شهریور ۱۴۰۵، ۱۵:۳۰</td>
</tr>
 Test Files  1 failed | 8 passed (9)
      Tests  1 failed | 34 passed (35)
```

The pill survives the mutation (it is untouched); only the scope statement disappears, and the
test fails on exactly that — the row that used to be a compliance-shaped signal with nothing
saying what it was about. Restored the fix afterward and re-ran to confirm the suite is green
again (35/35, shown above).

### The real path

`make up`: `docker compose up --build` tries to rebuild `api`/`worker`/`beat` too, and this
sandbox's Docker daemon cannot reach `pypi.org` for `uv sync` from inside the build network
namespace (a pre-existing, documented sandbox limitation — see T-0034, T-0036, T-0081, T-0083 —
not caused by this change). This task touches only `services/web`, and `api`/`worker`/`beat`
were already running unmodified code, so only `web` needed a real rebuild, same precedent as
T-0034:

```
$ docker compose -f deploy/compose.yaml build web
...
#13 [web build 7/7] RUN pnpm run build   → ✓ built in 2.48s
...
 web  Built
$ docker compose -f deploy/compose.yaml up -d --no-deps web
 Container cadgpt-web-1  Recreated
 Container cadgpt-web-1  Started
```

Then a real check run against the real running stack (register a real account through the
API, create a real project and review through the browser, upload the real
`three_doors.ifc`, run the real `door_width.ids` check, wait for the real report), then back
out to the project's own reviews table and read the row:

```
Row (ProjectDetailPage, real stack, real check run, real FAIL outcome):
  t0041-real-path-1789198438603   three_doors.ifc   تمام‌شده   [● مردود
                                                                  دربارهٔ مدل است، نه نقشه‌ها]
  ۲۱ شهریور ۱۴۰۵، ۱۱:۰۳
```

("مردود" = Fail, the outcome pill; "دربارهٔ مدل است، نه نقشه‌ها" = "About the model, not the
drawings", the new scope statement, rendered directly under the pill in the same cell.)
Screenshot: `services/web/e2e/screenshots/t0041-reviews-table-outcome-scope.png` (not tracked
by git — `e2e/screenshots/` is gitignored, per this repo's own convention — but present on disk
from this run). The pairing was also asserted in-test (`expect(row.getByText("مردود"))` and
`expect(row.getByText("دربارهٔ مدل است، نه نقشه‌ها"))` against the same `<tr>` locator), both
passed, in a throwaway spec run once for this evidence and then deleted (not a permanent
addition to `e2e/`; the permanent regression coverage is the Storybook `play` function above).

`make e2e` (full suite, 13 specs against the real stack): 12 passed. One pre-existing failure,
unrelated to this task and not touching any file this task changed —
`e2e/report.spec.ts:380`, "a restricted attribute name renders as its own sentence...": its
catalogue-picker locator (`li` filtered by `hasText: "Restricted attribute name"` and
`hasText: "v0.1"`) matches *two* seeded rule packs, both added by `seed_rule_packs.py`'s
checked-in manifest (`door_name_restricted.ids` → "Restricted attribute name", and
`door_name_restricted_with_bound.ids` → "Restricted attribute name with a value bound", added
in T-0039's own review round, both version "0.1") — the spec's locator was never tightened
after the second fixture was added, so it now resolves to two `<li>` elements instead of one.
Reproduced alone (`pnpm exec playwright test e2e/report.spec.ts -g "restricted attribute
name"`), same failure, confirming it is not an artifact of parallel workers. This is the rule
pack catalogue picker on `ReviewDetailPage`/`ReviewAddPage` — a different surface than the one
this task touches — and out of this task's scope to fix; reported here rather than silenced.
The other 12 specs passed, including `onboarding.spec.ts` (which walks every project/review
route in the browser) and `report.spec.ts`'s other four specs.

### Wiring

- `review.outcomeScope` reaches the browser through the same import every other row string
  already uses — `services/web/src/i18n/index.ts`: `import en from "@/i18n/en.json";` /
  `import fa from "@/i18n/fa.json";`, passed to `i18n.use(initReactI18next).init({ resources
  ... })` immediately below.
- `ProjectDetailPage.tsx` renders it at the outcome cell: `<span
  className="table__scope">{t("review.outcomeScope")}</span>`, inside the same `<td>` as
  `<StatusPill status={latest.outcome} />`.
- `ReviewDetailPage.tsx`'s run-history table renders the identical pairing at
  `<td>{candidate.outcome ? (<div className="table__outcome"><StatusPill .../><span
  className="table__scope">{t("review.outcomeScope")}</span></div>) : null}</td>`.
- `.table__outcome` / `.table__scope` registered in `services/web/src/styles.css` beside the
  existing `.pill` rules.

### Reviewer follow-up: F1 (no regression coverage on the second surface) and F2 (the one
assertion that did exist couldn't detect the string disappearing)

The independent reviewer confirmed the shipped behaviour was correct (the scope statement
genuinely renders beside the pill, for all three outcomes, on both surfaces) but found the
*proof* had two holes:

- **F1** — `ReviewDetailPage.stories.tsx` had zero `play` functions; deleting the scope
  `<span>` from `ReviewDetailPage.tsx` left `test-storybook` at 35/35.
- **F2** — `ProjectDetailPage.stories.tsx`'s one assertion read
  `rowScope.getByText(i18n.t("review.outcomeScope"))`: a second catalogue lookup through the
  same JSON the component itself reads. Deleting the key from both `en.json` and `fa.json`
  left both sides falling back to the bare key string (`"review.outcomeScope"`) via
  i18next's `fallbackLng`, so the assertion still passed — 35/35 green while every row
  silently started rendering a raw i18n key instead of prose.

**Fix.**

- `ProjectDetailPage.stories.tsx`'s `Populated` story: the scope assertion now reads
  `rowScope.getByText("دربارهٔ مدل است، نه نقشه‌ها")` — the literal Persian string the
  catalogue actually holds (the workbench's `initialGlobals: { locale: "fa" }`,
  `.storybook/preview.tsx`, is the active language under `test-storybook`) — instead of a
  second `i18n.t(...)` round-trip.
- `ReviewDetailPage.stories.tsx`'s `Checked` story gained a `play` function, the same
  row-scoped shape as `ProjectDetailPage.stories.tsx`'s: it locates the succeeded run's row
  in the run-history table by its formatted date (`formatDate(fx.succeededRun.created_at)`,
  unique in that table), then asserts — within that one `<tr>` — both the pill
  (`i18n.t("status.FAIL")` → "مردود") and the scope statement, again against the literal
  string rather than a second catalogue lookup, for the same reason as above.

**Re-run after the fix:**

```
$ pnpm run test-storybook
 Test Files  9 passed (9)
      Tests  35 passed (35)
```

**Mutation proof 1 (F1) — scope `<span>` removed from `ReviewDetailPage.tsx`:**

```
$ pnpm run test-storybook
 ❯ |storybook (chromium)| ReviewDetailPage.stories.tsx (9 tests | 1 failed)
   × Checked
TestingLibraryElementError: Unable to find an element with the text:
دربارهٔ مدل است، نه نقشه‌ها.
<tr class="active">
  <td>تمام‌شده</td>
  <td><div class="table__outcome"><span class="pill pill--fail">مردود</span></div></td>
  <td class="muted">۱۴ شهریور ۱۴۰۵، ۱۵:۳۰</td>
</tr>
 Test Files  1 failed | 8 passed (9)
      Tests  1 failed | 34 passed (35)
```

Restored the `<span>` and re-ran: 9 files / 35 tests, all green again.

**Mutation proof 2 (F2) — `review.outcomeScope` deleted from both `en.json` and `fa.json`:**

```
$ pnpm run test-storybook
 FAIL  ProjectDetailPage.stories.tsx > Populated
 FAIL  ReviewDetailPage.stories.tsx > Checked
TestingLibraryElementError: Unable to find an element with the text:
دربارهٔ مدل است، نه نقشه‌ها.
<span class="table__scope">review.outcomeScope</span>
 Test Files  2 failed | 7 passed (9)
      Tests  2 failed | 33 passed (35)
```

Both play functions now fail on the literal-string assertion — the raw i18n key
(`review.outcomeScope`) is visible in the DOM in the failure output, exactly the silent
regression F2 named. Restored both keys and re-ran: 9 files / 35 tests, all green again
(confirmed by `git diff services/web/src/i18n/en.json services/web/src/i18n/fa.json`
showing only the original single-line addition to each file, no net change).

**`make verify` (full, re-run after the fix, same portable-`msgfmt`-on-`PATH` workaround as
above — no change to any gate):**

```
uv run ruff check .                → All checks passed!
uv run ruff format --check .       → 190 files already formatted
uv run mypy packages/engine/src services/api/cadgpt → Success: no issues found in 172 source files
uv run lint-imports --no-cache     → Contracts: 5 kept, 0 broken.
compilemessages                    → (fa.po already compiled and up to date)
uv run pytest                      → 292 passed, 34 warnings in 4.53s
cd services/web && pnpm run verify:
  lint      → 0 errors, 2 warnings (pre-existing, in ReportView.tsx/main.tsx, untouched)
  typecheck → clean
  build     → ✓ built in 8.75s
  build-workbench (storybook build) → completed successfully
  test-unit → 1 file, 2 tests passed
  test-storybook → 9 files, 35 tests passed
```

### NOT DONE

Nothing. The engine, the counts, the three-valued discipline, and the report view's own
disclosure (T-0029) were not touched, per Scope. The one e2e failure above is pre-existing,
unrelated, and named rather than fixed or hidden — fixing it is a different task (the
catalogue-picker locator in `report.spec.ts`, or disambiguating the two seed fixtures' names),
not this one's. F1 and F2, the two fix-now defects the reviewer found in the regression
coverage, are both fixed and mutation-proven above; nothing from that review round remains
open.

## Review
