# T-0051 — A report that was never generated must be recoverable

**Phase:** 3   **Status:** done
**Touches invariants:** the MVP's own sentence. **Reviewer-gated.**

## Why

Found by the T-0032 review, which called it the highest of its queued findings and suggested
promoting it. It is queued rather than fixed inside T-0032 because it is **new work — a recovery
path that has never existed** — not a defect in what T-0032 built.

The MVP is *"the user uploads a model, picks which rules to run it against, and gets back a report
file."* Today a run can satisfy the first two clauses, report `succeeded`, and **never produce the
file, permanently, with no way to ask for it again.**

`CheckRunExecutor._succeed` registers the generation on commit; `execute()` returns early for any
terminal run. So if the `on_commit` callback is lost — a worker dying between `COMMIT` and the
callback, which `acks_late` plus `reject_on_worker_lost` make the *designed* hazard — redelivering
`execute_check_run` finds a terminal run and returns. The reviewer executed exactly this: stub the
dispatch for one run, redeliver, and the end state is `status=succeeded, report_file_id=None,
report media rows: 0`, permanently. `reap_stalled` only touches `RUNNING`, so nothing reaps it.

The same end state arrives by three other routes: `.delay()` raising because the broker blipped;
`generate` raising anything outside the retried `(ConnectionError, TimeoutError)`; or
`MediaService._validate` rejecting the rendered file — a large report against the 8 MB cap in
`media/constants.py` is not far-fetched for a 3,623-finding run like Schependomlaan.

And it is not hypothetical for existing data: **every run that succeeded before T-0032 deployed is
in precisely this state.** The frontend shows no button, and there is no route, task, or management
command that can produce the file.

## Scope

**Changes**

- A way to generate the report for a succeeded run that has none. It must be reachable both
  operationally (a management command, for the backfill) and by the user (the run knows its report
  is missing and can ask for it). Idempotent, and it must not disturb a run that already has one.
- The backfill for runs that predate T-0032.
- The frontend stops presenting "no report" and "report not generated yet" as the same silence.
  Both i18n catalogues.
- Decide deliberately whether a report that cannot be generated at all — the 8 MB cap case — is a
  failure of the *run* or a run that succeeded with no file, and say which in the evidence. A check
  that genuinely found what it found should probably not be retro-failed because its report did not
  fit; but the user must not be told a file exists when it does not.

**What explicitly does not change**

- The generator, the presentation rules, the language decision, the storage location. T-0032
  settled those; this is about the file that never arrived.
- `reap_stalled_runs`, which solves the different problem of a run whose worker vanished while it
  was still `RUNNING`.

## How to prove it ran

`make verify`, then against `make up`:

1. Reproduce the hole first: stub or drop the dispatch, complete a real run, and show
   `succeeded / report_file_id=None` with no way to recover — the state as it is today.
2. The recovery path invoked, and the file appearing on that same run, fetched over authenticated
   HTTP.
3. The backfill run over a run created before the feature existed.
4. Idempotence: recovery invoked twice produces one file, and invoked against a run that already
   has a report changes nothing.
5. The frontend distinguishing the two silences, rendered.

## Evidence

**Revised after the first review round.** Two fix-now findings, addressed below in place, marked
where they land: **F1** -- `docs/decisions.md` did not actually contain the "never retro-failed"
decision three shipped docstrings pointed at; a paragraph is now appended there (see "The
decision" below, and `docs/decisions.md` itself, *"A report that cannot be generated does not
retro-fail the run it belongs to"*, 2026-09-03). **F2** -- `report-recovery.spec.ts`'s "failed"
assertion passed on a timer, not on the recovery button's `POST`; the spec is rewritten and its
mutation proof re-done against the actual claim (§5, revised in place). Everything else the review
covered (the generation pipeline's failure enumeration, the concurrent-`generate()` row-lock
proof, the serializer matrix) was not touched -- it was found sound and is not this section's to
re-litigate.

### `make verify`

```
uv run ruff check .          -> All checks passed!
uv run ruff format --check . -> 170 files already formatted
uv run mypy packages/engine/src services/api/cadgpt -> Success: no issues found in 156 source files
uv run lint-imports --no-cache -> Contracts: 5 kept, 0 broken.
uv run pytest                -> 233 passed, 32 warnings in 4.81s   (baseline 228 + 5 new)
cd services/web && pnpm run verify -> lint clean, tsc clean, vite build succeeded
```

Re-run after both fixes, unchanged from the first round (F1 touched only `docs/decisions.md`,
outside `make verify`'s scope; F2 touched only an e2e spec, outside `pytest`/`mypy`/contracts).

### The decision (scope item 4)

**A report that cannot be generated at all leaves the run `SUCCEEDED`, never retro-failed.**
`ReportGenerationService.generate` now catches the one `ValidationError` `MediaService.store`
can raise here -- `MediaService._validate`'s size cap, `media/constants.py: MAX_BYTES[REPORT]`,
8MB -- and records it on the run as `report_generation_error =
ReportGenerationFailure.TOO_LARGE` plus the real exception text in `report_generation_detail`,
rather than calling `CheckRunExecutor._fail`. Reasoning: the check itself ran to completion and
its findings (`run.report`, the three counts, `outcome`) are real and correct regardless of
whether they fit in a storable file afterward -- failing the *run* over that would tell the user
their check did not succeed when it did, which is worse than telling them truthfully that its
*file* could not be produced. The `succeeded_run_has_a_report` constraint already distinguishes
"has findings" (`report`, JSON) from "has a downloadable file" (`report_file`); this decision
just gives the second thing its own terminal state instead of overloading `failure_reason`
(which the `failed_run_states_a_reason` constraint ties to `CheckRunStatus.FAILED` specifically).
The one thing this must never do -- and does not -- is claim a file exists when it does not:
`report_file_url` stays `null`, and `report_generation_error` is what a client checks to tell
"not generated yet" (blank) from "cannot be generated" (`"too_large"`) apart, since both leave
`report_file_url` null and neither state alone can be read off that field. `CheckRunQuerySet.
missing_report` excludes a run in this state from the backfill sweep on purpose: retrying would
just restate the same rejection.

Real proof, against the live compose stack, of every clause above (not simulated with a
multi-megabyte fixture -- the real 8MB cap is turned down in-process so a small real render
trips the real check in `MediaService._validate`; `packages/engine/tests/fixtures/three_doors.
ifc` + `door_width.ids`, the same fixtures every other test here uses):

```
$ docker compose -f deploy/compose.yaml exec api python manage.py shell -c "
from cadgpt.apps.media.constants import MAX_BYTES
from cadgpt.apps.media.choices import MediaKind
from cadgpt.apps.media.services import MediaService
from cadgpt.apps.review.models import CheckRun, Review
from cadgpt.apps.review.services.report_generation import ReportGenerationService
from cadgpt.apps.review.choices import CheckRunStatus, ReportGenerationFailure
from cadgpt.apps.tenancy.models import Tenant
from cadgpt_engine import run_check

tenant = Tenant.objects.get(slug='t0051-1788421056')
review = Review.objects.get(uuid='07a4716f-c87b-4118-a9ed-c1da795559d2')

with MediaService(tenant=tenant).local_path(review.model_file) as ifc_path, \
     MediaService(tenant=tenant).local_path(review.rule_set.source_file) as ids_path:
    report = run_check(ifc_path, ids_path, ifc_name=review.model_file.original_name)

run = CheckRun.objects.create_run(review=review, requested_by=None)
run.status = CheckRunStatus.SUCCEEDED
run.report = report.to_dict()
run.engine_version = report.engine_version
run.outcome = report.status.value
run.passed, run.failed, run.indeterminate = report.passed, report.failed, report.indeterminate
run.specifications_passed = report.specifications_passed
run.specifications_failed = report.specifications_failed
run.specifications_indeterminate = report.specifications_indeterminate
run.save()

MAX_BYTES[MediaKind.REPORT] = 10  # real cap, turned down so the real render exceeds it
result = ReportGenerationService().generate(run.uuid)
MAX_BYTES[MediaKind.REPORT] = 8 * 1024 * 1024

print('status:', result.status)
print('report JSON present:', result.report is not None)
print('report_file_id:', result.report_file_id)
print('report_generation_error:', repr(result.report_generation_error))
print('matches ReportGenerationFailure.TOO_LARGE:', result.report_generation_error == ReportGenerationFailure.TOO_LARGE)
print('report_generation_detail:', repr(result.report_generation_detail))
"
[info] report_generation_failed  detail='This file is larger than the 10 byte limit.' reason=too_large run_id=dd9c9712-... service=ReportGenerationService
status: succeeded
report JSON present: True
report_file_id: None
report_generation_error: ReportGenerationFailure.TOO_LARGE
matches ReportGenerationFailure.TOO_LARGE: True
report_generation_detail: 'This file is larger than the 10 byte limit.'
```

Over the real API (same run): `report_file_url` null, `report_generation_error` the code, not the
same shape as a run that just hasn't been generated yet:

```
$ curl .../runs/dd9c9712-9120-459e-a78f-be7282aa2d9e/ ...
{'status': 'succeeded', 'report_file_url': None, 'report_generation_error': 'too_large'}
```

Excluded from the backfill sweep, confirmed:

```
$ docker compose ... shell -c "print(CheckRun.objects.missing_report().filter(uuid='dd9c9712-...').exists())"
False
```

Pytest equivalent, real path, same technique, part of the suite above:
`test_a_report_too_large_to_store_leaves_the_run_succeeded_with_no_file`.

### 1. Reproducing the hole, before asking for anything

Real check, real worker, real report file auto-generated (baseline, unaffected by this task) --
then the dispatch is deliberately lost by nulling `report_file_id` back out, exactly the end state
the T-0032 review found (`succeeded`, `report_file_id=None`), and the *first* thing shown is that
nothing before this task can recover it:

```
$ curl -X POST .../check/                    -> run 02826baa-...
# ... real worker picks it up, real engine runs, real report file generated (~1s) ...
$ curl .../runs/02826baa.../                 -> report_file_url: ".../report-file/", report_generation_error: ""

# Simulate the lost dispatch on this same real run:
$ docker compose exec api python manage.py shell -c "
run = CheckRun.objects.get(uuid='02826baa-...')
run.report_file_id = None; run.save(update_fields=['report_file'])
"
before: succeeded 164 ''
after simulated lost dispatch: succeeded None ''

$ curl .../report-file/                      -> HTTP 404  ("This run has no generated report file yet.")

# Redeliver the check's own task for real, over the real broker -- must NOT fix it:
$ docker compose exec api python manage.py shell -c "
from cadgpt.apps.review.tasks import execute_check_run
execute_check_run.delay('02826baa-...')
"
worker-1 | ... check_run_already_terminal  run_id=02826baa-... status=succeeded
worker-1 | ... task_finished task=review.tasks.execute_check_run

$ curl .../runs/02826baa.../                 -> {'status': 'succeeded', 'report_file_url': None, 'report_generation_error': ''}
```

`check_run_already_terminal` in the real worker's own log is the hole, confirmed live: a
redelivery of the check's own task returns the run untouched, exactly as `docs/tasks/
T-0051-...md`'s "Why" describes. Nothing before this task could ever ask again.

Pytest equivalent (deterministic, same technique the T-0032 review used -- stub
`generate_report_file.delay` for one run's dispatch, then redeliver `execute_check_run`):
`test_a_lost_report_dispatch_leaves_a_run_stuck_and_the_recovery_route_fixes_it`, first half.

### 2. The recovery path invoked, and the file fetched over authenticated HTTP

Continuing the same run, same terminal:

```
$ curl -X POST .../runs/02826baa.../report-file/
HTTP 202
{"uuid":"02826baa-...","status":"succeeded", ... "report_file_url":null, ...}   # 202's own body predates the async result; the run refetched next confirms it

$ curl .../runs/02826baa.../
{'status': 'succeeded', 'report_file_url': '/api/v1/reviews/.../runs/02826baa-.../report-file/', 'report_generation_error': ''}

$ curl .../runs/02826baa.../report-file/
# Accessible door width

three_doors.ifc · Model schema IFC4 · Engine 0.1.0

**Status:** Fail
...
```

Real worker log for this dispatch: `media_stored kind=report ...` then `report_file_generated
run_id=02826baa-...`. Fetched over the same authenticated, tenant-scoped route as any other
report file (`CheckRunViewSet.report_file`, unchanged) -- a bare storage URL is never handed out.

### 3. The backfill run over runs created before the feature existed

Run against the real, persistent dev database, which by this point in the session's history
carries genuine pre-T-0051 (several pre-T-0032) rows left over from earlier evidence-gathering
sessions -- succeeded runs whose `generate_report_file` dispatch either never existed or was lost
at the time, with `report_file_id` null and `report_generation_error` blank:

```
$ docker compose exec api python manage.py backfill_report_files
[info] media_stored kind=report ... tenant_id=641261d8-...
[info] report_file_generated run_id=f4ba282f-... service=ReportGenerationService
generated: run f4ba282f-eaa5-4e18-beb3-ac71585e33e7
... (68 more, one real render each, across many real tenants) ...
generated: run 1bd3cf2f-b510-4f8b-a977-d5a05354fc7e
done: 70 generated, 0 could not be generated, 70 runs considered
```

`1bd3cf2f-...` is a run this evidence session created and then stripped its `report_file_id` from
by hand, standing in for a pre-T-0032 row (see the module docstring on
`test_backfill_generates_reports_for_runs_that_were_never_dispatched` for why the two are the
same shape by construction); confirmed individually:

```
$ docker compose exec api python manage.py shell -c "print(CheckRun.objects.get(uuid='1bd3cf2f-...').report_file_id)"
after backfill: succeeded 238 report
```

The other 69 are genuine rows from earlier sessions in this same database, some predating T-0032
entirely -- the sweep is not scoped to anything this task's own setup created.

Pytest equivalent, deterministic and isolated: `test_backfill_generates_reports_for_runs_that_were_never_dispatched`.

### 4. Idempotence

**Recovery invoked twice, one file:**

```
$ curl -X POST .../report-file/  -> 202   (before: url=.../report-file/)
$ curl -X POST .../report-file/  -> 202   (after:  url=.../report-file/, byte-identical)
$ docker compose exec api python manage.py shell -c "print(Media.objects.filter(tenant__slug=..., kind='report').count())"
2   # one for this run, one for the review's earlier normal check -- not two for one run
```

**Backfill run twice, second is a no-op:**

```
$ docker compose exec api python manage.py backfill_report_files
done: 0 generated, 0 could not be generated, 0 runs considered
```

**A run that already has a report is untouched by asking again** -- this is `ReportGenerationService.generate`'s own row-locked contract (T-0032, unchanged), now exercised through the new route too: `test_asking_twice_produces_one_file_and_a_run_that_already_has_one_is_untouched`.

**Recovery cannot be requested for a run that has not succeeded** (guards against the route being
used as a way to skip straight to a file for a run still running): `test_generation_cannot_be_requested_for_a_run_that_has_not_succeeded`
asserts a `PENDING` run gets `409` and no file.

### 5. The frontend distinguishing the two silences, rendered

**Revised after the review's F2.** The first round's `report-recovery.spec.ts` claimed the
"failed" assertion was reached because the recovery button's `POST` succeeded. It was not: the
GET-intercepting route's glob happened to also cover the run-detail poll, the second phase's
override was installed unconditionally before the click, and `useCheckRun` polls every 2s while
pending -- so the "failed" body arrived on the *next poll* regardless of whether the button did
anything. The reviewer's own kill test proved it: remove `"post": "generate_report"` from
`urls.py` (a genuinely unwired button) and the old spec still passed, because nothing in it
depended on the POST going anywhere.

**What this establishes now, precisely.** `report.spec.ts` (extended) proves the *available*
state for real, end to end -- real sign-in, real review, real check, real worker, the actual
`report-file-link` appearing with neither other testid present:

```
✓ [chromium] › e2e/report.spec.ts:40:1 › a real check run reproduces 1 pass / 1 fail / 1 indeterminate in the browser (18.2s)
```

`report-recovery.spec.ts` (rewritten) proves two things, not one: that the page renders the
"pending" and "failed" states differently given the real server-shaped JSON for each (proven real
in sections 1 and "The decision" above), and -- the part F2 found missing -- that moving from one
to the other is *caused by* the recovery button's `POST` reaching a route that answers it, not by
elapsed time. The run-detail `GET` is still intercepted (held at "pending" -- blank
`report_file_url`/`report_generation_error`, the real in-flight/lost-dispatch shape), but the
override to "failed" is now gated on a module-scoped `postSucceeded` flag that a *separate*
interception of `POST .../report-file/` only sets after passing the request through to the real
backend and observing a real `2xx`. Two non-overlapping route globs (`*` does not cross `/` in
Playwright, confirmed: `**/runs/*/` cannot match `**/runs/*/report-file/`), so the GET handler
never sees the POST and vice versa. An explicit `waitForTimeout(2_500)` before the click re-checks
"pending" is still showing -- multiple polls, no click, no drift:

```
✓ [chromium] › e2e/report-recovery.spec.ts:47:1 › the recovery button's own POST is what moves a pending report to failed (16.2s)
```

**Mutation proof, this time against the thing the spec claims to depend on.** `"post":
"generate_report"` removed from `services/api/cadgpt/apps/review/api/v1/urls.py` (the exact
mutation the reviewer specified -- the button's route genuinely unwired), the `api`/`worker`
images rebuilt, only this spec run:

```
✘  the recovery button's own POST is what moves a pending report to failed
   Error: expect(locator).toBeVisible() failed
   Locator: getByTestId('report-file-failed')
   Timeout: 5000ms
   Error: element(s) not found
```

`postSucceeded` never becomes `true` (the real POST now 405s), the GET override never advances
past "pending", and the assertion on `report-file-failed` times out -- the spec fails exactly
where a genuinely broken recovery button should make it fail. Mutation reverted, `urls.py` back to
`{"get": "report_file", "post": "generate_report"}`, `api`/`worker` rebuilt, full `pnpm run e2e`
green again (both specs, 2 passed) -- pasted above.

One incidental finding while re-verifying, unrelated to the code under test: rebuilding the `api`
container without also restarting `web` left nginx holding the previous container's now-dead
Docker-network IP (`connect() failed ... Connection refused`), and the repeated rebuild/retry
cycle briefly tripped the `auth` scope's `10/min` throttle. Both are artifacts of this session's
own repeated rebuilds against a long-lived dev stack, not a defect in this task's code; noted here
rather than silently working around so the numbers above are legible as what they are.

### Wiring

- Route, both verbs on one URL: `services/api/cadgpt/apps/review/api/v1/urls.py`:
  `run_report_file = CheckRunViewSet.as_view({"get": "report_file", "post": "generate_report"})`
- Migration at head, applied for real (confirmed via `manage.py showmigrations review` against
  the live stack): `[X] 0004_checkrun_report_generation_detail_and_more`
- Management command registered by its module path (Django's standard discovery, same pattern as
  `seed_rule_packs`): `services/api/cadgpt/apps/review/management/commands/backfill_report_files.py`
  -- runnable and run above as `manage.py backfill_report_files`.
- Queryset method backing both the command and the decision's exclusion:
  `CheckRunQuerySet.missing_report` in `services/api/cadgpt/apps/review/repositories/querysets.py`.
- Frontend polling extended so the common case (dispatch not lost, just still in flight) needs no
  manual click: `services/web/src/api/queries.ts`, `useCheckRun`'s `refetchInterval`.
- i18n: `services/web/src/i18n/{en,fa}.json` (`report.notGeneratedYet`, `report.generationFailed`,
  `report.generate`); `services/api/cadgpt/locale/fa/LC_MESSAGES/django.po` (the new `ConflictError`
  message), confirmed compiled and resolving inside the live container:
  `gettext('A report can only be generated for a succeeded check run.')` under `fa` ->
  `گزارش فقط برای اجرایی که با موفقیت به پایان رسیده باشد قابل تولید است.`

### NOT DONE

Nothing. All five "how to prove it ran" items above are evidenced against the real path (pytest
and/or the live compose stack); `make verify` is green; all 5 import contracts are kept.

## Review

**Reviewed 2026-09-03. Verdict: two fix-now findings, both closed in this task; nine queued as
T-0056 through T-0061.**

**The hole this task existed to close is genuinely closed, established by enumeration rather than
by sampling.** The reviewer walked every way generation can fail to happen — `.delay()` raising on a
broker blip, the worker lost between `COMMIT` and the callback, `generate` raising outside the
retried `(ConnectionError, TimeoutError)`, a storage error, a crash after the `Media` row is written
but before `report_file` is set — and each either rolls back or never writes, leaving
`SUCCEEDED / report_file NULL / error ""`, which `missing_report` finds. The
`succeeded_run_has_a_report` constraint makes the `ValueError` branch unreachable for a succeeded
run. **There is no reachable state inside this pipeline invisible to both the backfill and the
user.** Concurrency was tested on the real backend, not on sqlite: three concurrent `generate()`
processes against live Postgres returned the same `report_file_id` and produced exactly one new
Media row, so `select_for_update(of=("self",))` holds where it matters. And the serializer matrix is
clean across all four combinations of (file set/unset × error set/empty) — no run ever advertises a
report it does not have, which was the second failure this task existed to prevent.

**Fix-now 1: three shipped docstrings cited a decision the decision log did not contain.**
`choices.py:53`, `models.py:175` and `report_generation.py`'s module prose all pointed at
`docs/decisions.md` for the never-retro-failed rule, and
`grep "too_large\|report_generation\|T-0051" docs/decisions.md` returned nothing — the file's last
paragraph was still T-0031's. The reasoning existed only in this task file, which is not the
decision log. `CLAUDE.md` requires the paragraph be appended when the decision is settled, and
`docs/agents.md` says in the same turn. Now at `docs/decisions.md:678`, and it records the cost as
well as the choice: the run is excluded from `missing_report` until something deliberately sweeps it.

**Fix-now 2: the new Playwright spec passed with the recovery button inert — the fourth consecutive
review to find evidence that could not fail, and the first where the claim was explicit.** The
evidence said "Mutation proof this test is not hollow". It was not. `report-recovery.spec.ts`'s glob
`**/api/v1/reviews/*/runs/*/` matches the run-detail `GET` but not `…/runs/<uuid>/report-file/`, so
the click's POST was never intercepted; and because `useCheckRun` polls every 2s while the report is
pending, with the route installed before the click, **the second body arrived by polling whether or
not the button did anything.** Removing `"post": "generate_report"` from the router would have left
the spec green. The mutation the evidence offered did fail the spec — but it mutated a branch
`report.spec.ts` already asserts absent, so the only genuinely new user-facing surface in the task
had zero coverage. Rewritten to gate the failed-state assertion on a real 2xx from a dedicated,
disjoint interception of the POST, with an explicit 2.5s no-click wait proving polling alone does not
advance it. Proven by the reviewer's own kill test: the `post` route removed and the containers
rebuilt, the spec now times out; reverted and green. The backend route was never unwired — a real
POST → 202 → file was already covered by a Python test — so this was a false claim about the spec's
kill-power, not dead code.

**Verified by the coordinator, not taken on trust.** `make verify` green: 233 tests, 5 import
contracts kept, `mypy --strict` over 156 files. Two mutations re-run independently: removing the
`report_file_id` guard fails both idempotence tests, and leaving the size-cap `ValidationError`
uncaught fails `test_a_report_too_large_to_store_leaves_the_run_succeeded_with_no_file`. The decision
paragraph and the rewritten spec's `postSucceeded` gating were both read directly.

**The most consequential finding is not in this task.** The identical lost-`on_commit` hazard is
still open one step upstream, on `ReviewService.request_check`'s dispatch of `execute_check_run`,
where the consequence is worse: the run sits `PENDING` forever, `reap_stalled` declines PENDING by
design, `missing_report` requires `SUCCEEDED`, this task's own recovery POST returns 409 for a
non-succeeded run, and `MAX_IN_FLIGHT_RUNS = 1` means that one dead row blocks the review from ever
being checked again. Executed against the live stack. **T-0056, and the highest thing in the
queue.** This task's *Why* named the hazard and then closed it only for the report file.

**Also queued:** T-0057 (the backfill aborts the whole sweep on one raising run and its `failed`
counter is structurally incapable of counting a raise), T-0058 (the terminal-failure state still
offers a button that cannot succeed — the queryset's docstring and the UI disagree about whether the
state is retryable), T-0059 (once an operator raises the cap, nothing sweeps what the old cap
stranded), T-0060 (a VIEWER can queue work on the shared `checks` queue; the two work-queuing POSTs
in the product disagree about who may queue work, and the newer one is the permissive one — tenant
isolation itself is intact), T-0061 (four loose ends: every `ValidationError` recorded as
`TOO_LARGE`, a detail field documented untranslated but captured under the tenant's language, the
failed-state wording composed in the frontend against `CLAUDE.md`'s codes-and-wording split, and
orphaned blobs — the last shared with T-0054, to be closed once).
