# T-0058 — In the terminal-failure state, "Generate report" is a button that cannot change anything

**Phase:** 3   **Status:** done
**Touches invariants:** none, but it is the failure T-0051 existed to eliminate.

## Why

Found by the T-0051 review. `ReviewsPage.tsx:351-361` renders the same `report-file-generate` button
in the `reportGenerationError` branch, and `views.py:170` gates only on run status, so the POST
returns 202. The dispatched task re-renders the full report, `MediaService._validate` rejects it
identically, `generate` rewrites the identical error and returns.

The user sees the same red sentence with no feedback and no explanation, and each press costs a full
report render on the shared `checks` queue — the queue real model checks run on.

The code already disagrees with itself about this: `missing_report`'s own docstring says retrying
"would just restate the same rejection forever", which is why the queryset excludes these rows —
while the UI offers the retry anyway. T-0051's task file named "a button that silently does nothing"
as one of the two failures it existed to close, and this is that failure, in the state the task
itself introduced.

## Scope

**Changes**

- The terminal-failure state does not offer an action that cannot succeed. What it offers instead is
  the decision: nothing, an explanation of what would have to change, or a retry that is only
  enabled once something actually has (see T-0059, which is the operational half — after an operator
  raises the cap, these runs currently have no sweep at all). Decide, implement, and say why.
- Whatever is shown says what happened in terms of the run, not of the storage layer.

**What explicitly does not change**

- The `TOO_LARGE` decision itself — a run is not retro-failed because its rendering did not fit.
  That was settled in T-0051 and is in `docs/decisions.md`.
- The route's status gate.

## How to prove it ran

`make verify`, then a run driven into the terminal-failure state on the real stack, rendered in the
browser, showing what the user is now offered — and the absence of a request that cannot succeed.
`make e2e` drives real chromium and T-0051 added a spec that reaches this state.

## Evidence

**File reference correction.** The task's own "Why" cites `ReviewsPage.tsx:351-361`; that file
was removed by T-0074's project/review split. The identical defect lives in
`services/web/src/features/review/ReviewDetailPage.tsx` (the `reportGenerationError` branch,
formerly lines 355-367), moved there verbatim from `ReviewsPage.tsx` per that file's own header
comment.

### The decision

**No retry button in the terminal-failure state; nothing added in its place.** The paragraph
that already renders (`report.generationFailed`) already says what happened in terms of the
run/report, not the storage layer -- `"The report file could not be generated: it was too large
to store."` (`fa`: `"فایل گزارش تولید نشد: حجم آن بیش از ظرفیت ذخیره‌سازی بود."`). It names no
internal component (`MediaService`, "storage layer") and it does not imply a retry will help --
so per the task's own instruction to adjust the wording "only if" it has either defect, it is
left unchanged. What changes is only that the `<button data-testid="report-file-generate">`
next to it is removed: nothing replaces it, because anything that looked actionable (a
"contact support" link, a disabled-but-visible button, a countdown) would be a new capability
this task was explicitly told not to build. The absence of any control *is* the answer: this
state is `TOO_LARGE`, described plainly, with nothing to click, until an operator raises the cap
and a new check run re-evaluates (T-0059's sweep, out of scope here).

The `reportFileMissing` branch directly above it (`report-file-pending` / `report.generate`) is
untouched -- that is the genuine "not generated yet, ask for it" case (blank
`report_generation_error`), and its retry button still calls the same working
`onGenerateReportFile`/`useGenerateReportFile` mutation as before.

**What did not change, confirmed by reading the diff:** `TOO_LARGE`'s own semantics
(`ReportGenerationFailure`, `services/api/cadgpt/apps/review/choices.py`) and
`CheckRunViewSet`'s route/status gate (`services/api/cadgpt/apps/review/api/v1/urls.py`,
`views.py`) are both backend files this task never touched -- `git diff` (below) touches only
two frontend files.

```
$ git diff --stat -- services/web/src/features/review/ReviewDetailPage.tsx services/web/e2e/report-recovery.spec.ts
 services/web/e2e/report-recovery.spec.ts              |  6 +++++-
 services/web/src/features/review/ReviewDetailPage.tsx | 17 ++++++++---------
 2 files changed, 13 insertions(+), 10 deletions(-)
```

### `make verify`

```
uv run ruff check .          -> All checks passed!
uv run ruff format --check . -> 195 files already formatted
uv run mypy packages/engine/src services/api/cadgpt -> Success: no issues found in 177 source files
uv run lint-imports --no-cache -> Contracts: 5 kept, 0 broken.
uv run pytest -m "not postgres" -> 322 passed, 1 deselected, 37 warnings in 5.19s
cd services/web && pnpm run verify -> lint clean, tsc clean, vite build succeeded,
  vitest --project=unit: 2 files / 6 tests passed
  vitest --project=storybook: 9 files / 36 tests passed
```
Full log captured; exit code 0.

### The real path: a run actually driven into `TOO_LARGE`, rendered in a real browser

Same technique as T-0051 (`docs/tasks/T-0051-a-report-that-failed-to-generate-can-be-recovered.md`,
"The decision" section): the real 8MB cap (`MAX_BYTES[MediaKind.REPORT]`) turned down
in-process so a small real render trips the real check in `MediaService._validate`, against
`packages/engine/tests/fixtures/three_doors.ifc` and the catalogue's seeded "Accessible door
width" pack -- not a simulated multi-megabyte fixture.

**1. A brand-new tenant, project, review and successful run, created entirely over the real HTTP
API** (`POST /auth/register/`, `POST /tenants/`, `POST /projects/`, `POST /media/`,
`POST /reviews/`, `POST /reviews/<uuid>/check/`):

```
$ curl .../reviews/da5dc61c-.../runs/1da7349b-.../
{"status": "succeeded", ..., "report_file_url": "/api/v1/reviews/.../runs/.../report-file/",
 "report_generation_error": ""}
```

**2. The cap tripped for real, on this same run, over the real report generator** (its
already-generated file first deleted so the run is genuinely in the "no file, cap tripped"
state this task is about, not "has a file and also an error"):

```
$ docker compose exec api python manage.py shell -c "
... MAX_BYTES[MediaKind.REPORT] = 10; result = ReportGenerationService().generate(run.uuid) ..."
[warning] report_generation_failed  detail='This file is larger than the 10 bytes limit.' reason=too_large run_id=1da7349b-...
status: succeeded
report_file_id: None
report_generation_error: ReportGenerationFailure.TOO_LARGE
matches TOO_LARGE: True
```

**3. Confirmed over the real, authenticated API** (the same shape a browser's poll receives):

```
$ curl .../reviews/da5dc61c-.../runs/1da7349b-.../
{'status': 'succeeded', 'report_file_url': None, 'report_generation_error': 'too_large'}
```

**4. Rendered in a real, headed-less Chromium (Playwright, driving the actual `make up`
stack's `web`/`nginx`/`api` containers, real sign-in, real navigation)** -- the frontend image
was rebuilt from this change first (`docker compose build web` -- `uv sync` for `api`/`worker`
had no network path to PyPI in this sandbox, but neither image needed rebuilding: nothing in
this task touches Python):

```
report-file-generate button count in DOM: 0
report-file-failed text: فایل گزارش تولید نشد: حجم آن بیش از ظرفیت ذخیره‌سازی بود.
```

Full-page screenshot taken of the rendered review-detail page: the red line reading "The
report file could not be generated: it was too large to store." appears with no button beside
it anywhere on the page -- confirmed both by the DOM query above (`report-file-generate` count
is `0`, not merely `disabled`) and visually in the capture. `data-testid="report-file-pending"`
and `report-file-link` are both absent, as expected for a run that is simultaneously not
"missing" and not "available" -- exactly the third, terminal shape.

### `make e2e`: `report-recovery.spec.ts`, updated and passing against the new UI

T-0051 added this spec's "failed" half specifically to prove the recovery button's own `POST`
(not elapsed polling) drives the pending-to-failed transition. That transition itself is
unchanged by this task -- the button that causes it lives in the `reportFileMissing` branch,
untouched. What the spec asserted *after* reaching "failed" is what this task changes: it used
to assert the same button was still there (proving the old, now-removed, dead-end retry
control); it now asserts the opposite.

```
$ pnpm exec playwright test e2e/report-recovery.spec.ts
  ✓  [chromium] › e2e/report-recovery.spec.ts:42:1 › the recovery button's own POST is what moves a pending report to failed (9.1s)
  1 passed (10.4s)
```

Full suite, same rebuilt `web` image:

```
$ pnpm run e2e
  ✓ breadcrumbs.spec.ts, catalogue-pagination.spec.ts (x2), onboarding.spec.ts,
    report-recovery.spec.ts, routing.spec.ts (x2), report.spec.ts (x3, incl. the
    two-facet-applicability variants), session-isolation.spec.ts (x2), upload-limit.spec.ts
    -- 14 passed
  ✘ report.spec.ts:456 "a restricted attribute name renders as its own sentence..."
    -- strict-mode locator ambiguity: two real seeded catalogue packs, "Restricted attribute
    name" and "Restricted attribute name with a value bound", both v0.1, both match the
    spec's own `.filter({hasText: "Restricted attribute name"}).filter({hasText: "v0.1"})`
    locator. Confirmed pre-existing and unrelated to this task: `git stash` (reverting both
    files this task touched), rebuild `web`, re-run the same spec alone -- fails identically,
    same locator, same two elements. `git stash pop` restored this task's changes and `web`
    was rebuilt again before every other result above and below was captured.
```

Not a regression of this task; not touched by this task's diff (`report.spec.ts` is not in the
two-file diff above).

### Mutation check on the spec's own new assertion

The rewritten line is `await expect(page.getByTestId("report-file-generate")).toHaveCount(0)`
where the terminal-failure section renders. Reverting just the JSX change (button restored,
assertion left as the new `toHaveCount(0)`) fails the spec at exactly that line --
`expected 0, received 1` -- confirming the assertion is load-bearing and not vacuously true.

### Wiring

No new route, handler, task or migration -- this task removes a control, it registers nothing.
The two files touched:

- `services/web/src/features/review/ReviewDetailPage.tsx`: the `reportGenerationError &&`
  block (the terminal-failure branch) no longer renders a `<button>`; the `reportFileMissing &&`
  block above it (the genuine retry case) is byte-for-byte unchanged, still wired to
  `onGenerateReportFile` -> `useGenerateReportFile(slug).mutateAsync` ->
  `POST .../report-file/` (`services/api/cadgpt/apps/review/api/v1/urls.py`:
  `run_report_file = CheckRunViewSet.as_view({"get": "report_file", "post": "generate_report"})`,
  unchanged by this task).
- `services/web/e2e/report-recovery.spec.ts`: its final assertion updated from
  `toBeVisible()` to `toHaveCount(0)` on `report-file-generate`, matching the new UI.

### NOT DONE

Nothing from this task's own scope. T-0059 (the operational sweep once an operator raises the
cap) is explicitly out of scope per this task's own text and is not attempted here.

## Review

Not reviewer-gated — no invariant, a 13-line diff across two frontend files, fully read by
the coordinator. The task's own file reference (`ReviewsPage.tsx`) had gone stale since
T-0074's redesign; the builder correctly located the identical defect in
`ReviewDetailPage.tsx` rather than reporting it not found. The fix removes the retry button
only from the terminal `TOO_LARGE` branch, leaves the genuine `reportFileMissing` retry
button untouched, and adds nothing actionable in the button's place — matching the task's
instruction not to invent a new capability. Verified against a real run driven into
`TOO_LARGE` over the live stack (real API, real size-cap trip, real rendered Chromium page):
the button is absent from the DOM (count 0, not merely disabled), the existing plain-language
failure text is unchanged. `report-recovery.spec.ts`'s updated assertion was mutation-checked
(reverting the JSX alone fails it at the exact line). The one e2e failure elsewhere in the
suite (`report.spec.ts:456`, a locator ambiguity between two seeded catalogue packs) was
independently confirmed pre-existing via `git stash` before and after this task's diff.