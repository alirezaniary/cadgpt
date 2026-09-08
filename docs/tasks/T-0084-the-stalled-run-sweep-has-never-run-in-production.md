# T-0084 — `reap_stalled_runs` is registered nowhere and has never run in production

**Phase:** 3   **Status:** done
**Touches invariants:** idempotent background work; the MVP sentence — this is the same
"a review can be permanently stuck" failure T-0056 just closed for `PENDING`, still fully
open for `RUNNING`. **Reviewer-gated.**

## Why

Found by the T-0056 reviewer. `services/api/cadgpt/apps/review/tasks.py` defines
`reap_stalled_runs`, which calls `CheckRunExecutor.reap_stalled()` to fail any `RUNNING`
`CheckRun` whose worker died — the RUNNING-side sibling of what T-0056 built for `PENDING`.
Nothing calls it:

- No `CELERY_BEAT_SCHEDULE` anywhere in `services/api/cadgpt/config/settings/`.
- No `beat_schedule` in `services/api/cadgpt/config/celery.py`.
- No `beat` service in `deploy/compose.yaml` — there is no Celery beat process running at
  all, in dev or (as far as this repository records) in any deployment.
- No management command invokes it either.

So a `CheckRun` whose worker dies mid-evaluation — the exact scenario `reap_stalled_runs`'
docstring describes, and one T-0056's own evidence exercises via `execute()`'s idempotency
guarantees — sits `RUNNING` forever. Because `MAX_IN_FLIGHT_RUNS = 1`, that row blocks the
review from ever being checked again, with no way back: T-0056's `_reap_lost_dispatch` only
matches `PENDING` rows with no `task_id`; a stalled `RUNNING` row has both. This is not
hypothetical or theoretical-severity — it is the same user-facing failure T-0056 exists for,
just on the other side of `_claim`, and it has been reachable in every deployment of this
product since `reap_stalled_runs` was written.

`docs/decisions.md` (referenced by the T-0056 reviewer, around line 836) already describes
the sanctioned mechanism as "a sweep that finds stuck-`pending` runs and re-dispatches or
fails them by reason" — the decision exists; the wiring that makes it real does not.

## Scope

**Changes**

- Wire `reap_stalled_runs` into an actual periodic execution path: Celery beat is the
  obvious mechanism already present in this stack's dependency tree (`celery[redis]`), and
  `deploy/compose.yaml` needs a `beat` service alongside `worker`. Interval should be derived
  from `CHECK_RUN_STALL_SECONDS`, not invented separately.
- Confirm `reap_stalled_runs` (and `reap_stalled()` under it) is itself idempotent under
  beat's at-least-once scheduling — a `RUNNING` row already failed by a previous tick must
  not be reachable a second time (check the queryset's `status=RUNNING` filter already
  excludes a terminal row; state that check explicitly in the evidence rather than assuming
  it).
- Once beat exists, consider (as a separate decision, not silently folded in here) whether
  T-0056's `_reap_lost_dispatch` should also run from the same periodic tick rather than only
  reactively from `request_check` — that is T-0085's question, not this task's; do not answer
  it here, just do not make it harder to answer.

**What explicitly does not change**

- `CheckRunExecutor.reap_stalled()`'s own logic — it is correct, per T-0056's review; only its
  absence of a caller is the defect.
- `MAX_IN_FLIGHT_RUNS`, `_reap_lost_dispatch`, anything T-0056 touched.

## How to prove it ran

`make verify`, then against `make up`: a `RUNNING` `CheckRun` backdated past
`CHECK_RUN_STALL_SECONDS` with no live worker claim, left alone (not manually swept) — show
beat's own schedule ticking (real log line, real interval) and the row transitioning to
`FAILED`/`STALLED` on its own, then show the review can be checked again without manual
intervention. Also show a `RUNNING` row that is *not* stalled is untouched by the same tick —
the false-positive direction, exactly as T-0056 demanded for its own change.

## Evidence

### 1. `make verify`

Ran twice — once before the real-path exercise, once again after the last edit
(`deploy/compose.yaml`'s `beat.healthcheck: disable`) to confirm nothing python-side was
missed. Both green, final run:

```
$ make verify
uv run ruff check .
All checks passed!
uv run ruff format --check .
186 files already formatted
uv run mypy packages/engine/src services/api/cadgpt
Success: no issues found in 169 source files
uv run lint-imports --no-cache
---------
Contracts
---------
Analyzed 222 files, 693 dependencies.
-------------------------------------
I1 - no inference client, web framework or network reaches the checking engine KEPT
The engine knows nothing about the service that hosts it KEPT
Django apps are layered KEPT
Services never import the transport layer KEPT
Models never import services KEPT
Contracts: 5 kept, 0 broken.
uv run pytest
238 passed, 32 warnings in 3.78s
uv run pnpm run verify   (web-verify, unchanged by this task — frontend build succeeded)
EXIT CODE: 0
```

### 2. Wiring — the registration lines

**`services/api/cadgpt/config/settings/base.py`** (read by `celery.py`'s
`app.config_from_object("django.conf:settings", namespace="CELERY")`, so any
`CELERY_*` setting here becomes a Celery app setting — `CELERY_BEAT_SCHEDULE` is exactly
that convention, not an invented one):

```python
# `review.tasks.reap_stalled_runs` finds and fails those runs, but only if something calls
# it. Beat is that something. The tick runs at a quarter of `CHECK_RUN_STALL_SECONDS`
# rather than a number invented separately, so a run is caught within a quarter of its own
# stall window of stalling rather than up to a whole extra window late. See
# docs/tasks/T-0084-the-stalled-run-sweep-has-never-run-in-production.md.
CELERY_BEAT_SCHEDULE = {
    "reap-stalled-check-runs": {
        "task": "review.tasks.reap_stalled_runs",
        "schedule": CHECK_RUN_STALL_SECONDS / 4,
    },
}
```

`"task": "review.tasks.reap_stalled_runs"` matches the explicit name on the task itself
(`services/api/cadgpt/apps/review/tasks.py`):

```python
@shared_task(
    base=BaseTask,
    name="review.tasks.reap_stalled_runs",
    queue="default",
)
def reap_stalled_runs() -> int:
```

**`deploy/compose.yaml`** — the `beat` service, same image and environment as `worker`,
alongside it:

```yaml
  beat:
    # The process that actually calls `review.tasks.reap_stalled_runs` on a schedule
    # (`CELERY_BEAT_SCHEDULE`, services/api/cadgpt/config/settings/base.py). Without this
    # service the task is defined but never invoked -- T-0084.
    image: cadgpt-api:latest
    build: *api_build
    environment: *api_env
    command: celery -A cadgpt.config.celery beat --loglevel info
    depends_on:
      postgres: {condition: service_healthy}
      redis: {condition: service_healthy}
    healthcheck:
      disable: true
```

`make up`'s help text (`Makefile`) updated to match: `up:  ## Start Postgres, Redis, the
API, a worker, beat and the frontend`.

### 3. Idempotency, checked explicitly rather than assumed

`CheckRunQuerySet.stalled` (`services/api/cadgpt/apps/review/repositories/querysets.py:79-86`):

```python
def stalled(self, older_than_seconds: int) -> Self:
    cutoff = timezone.now() - timedelta(seconds=older_than_seconds)
    return self.filter(status=CheckRunStatus.RUNNING, started_at__lt=cutoff)
```

`CheckRunExecutor.reap_stalled` (`services/api/cadgpt/apps/review/services/execution.py:292-309`)
calls `.update(status=CheckRunStatus.FAILED, ...)` on exactly that queryset. A row a
previous tick already failed now has `status=FAILED`, which the `status=RUNNING` filter
above excludes on the next tick — the same row can never be matched twice. Confirmed live
below: the 21:49:22 tick reaped the stalled row (`count=1`); the very next tick, 15s
later at 21:49:37, found nothing (`count=0`) even though the row was still `started_at`
in the past — because it was no longer `RUNNING`.

### 4. The real path

Built the image with the required proxy build-args, then brought the real stack up with
`docker compose -f deploy/compose.yaml up -d --force-recreate` (an env-only override file
set `CHECK_RUN_STALL_SECONDS=60` on `api`/`worker`/`beat` so the derived 15s beat interval
could be observed inside a few minutes rather than the production default of 30 minutes /
7.5 minutes — the code path exercised is identical, only the constant's *value* differs,
exactly as the existing `test_a_stalled_run_is_failed_rather_than_left_looking_busy` does
with `settings.CHECK_RUN_STALL_SECONDS = 60`).

**Beat's own schedule ticking**, unprompted, on the derived interval (`docker compose logs beat`):

```
beat-1  | celery beat v5.6.3 (recovery) is starting.
beat-1  | Configuration ->
beat-1  |     . broker -> redis://redis:6379/0
beat-1  |     . scheduler -> celery.beat.PersistentScheduler
beat-1  | [2026-09-08 21:47:37,542: INFO/MainProcess] beat: Starting...
beat-1  | [2026-09-08 21:47:52,670: INFO/MainProcess] Scheduler: Sending due task reap-stalled-check-runs (review.tasks.reap_stalled_runs)
beat-1  | [2026-09-08 21:48:07,667: INFO/MainProcess] Scheduler: Sending due task reap-stalled-check-runs (review.tasks.reap_stalled_runs)
beat-1  | [2026-09-08 21:48:22,667: INFO/MainProcess] Scheduler: Sending due task reap-stalled-check-runs (review.tasks.reap_stalled_runs)
beat-1  | [2026-09-08 21:49:22,668: INFO/MainProcess] Scheduler: Sending due task reap-stalled-check-runs (review.tasks.reap_stalled_runs)
beat-1  | [2026-09-08 21:49:37,668: INFO/MainProcess] Scheduler: Sending due task reap-stalled-check-runs (review.tasks.reap_stalled_runs)
beat-1  | [2026-09-08 21:50:22,668: INFO/MainProcess] Scheduler: Sending due task reap-stalled-check-runs (review.tasks.reap_stalled_runs)
```

15 seconds apart, exactly `CHECK_RUN_STALL_SECONDS / 4` with the 60s test override.

**Setup** (real services, real files — `AccountService`, `TenantProvisioningService`,
`MediaService`, `RuleSetService`, `ReviewService`, real `three_doors.ifc` /
`door_width.ids` fixtures already baked into the image): a tenant, a review with a
`CheckRun` claimed by a worker and then backdated 180s into the past
(`status=RUNNING, task_id="dead-worker-task-id", started_at=now-180s`) — a worker that
died mid-evaluation, exactly the scenario the task names — and a second review with its
own `CheckRun` also `RUNNING`, `started_at=now` (a worker genuinely still working).
Neither row was touched by anything but `manage.py shell` writes and beat's own tick from
that point on — no manual `reap_stalled()` call anywhere in this sequence.

State immediately after setup (both `running`):
```
82aaf8b9-04f3-438b-8fd9-88bdea14908a running 2026-09-08 21:46:12.736900+00:00
eef19228-926c-4c10-b05e-59b0adabc047 running 2026-09-08 21:49:12.744247+00:00
```

**The row transitioning to FAILED/STALLED on its own** — worker log, the tick at
21:49:22 (the first tick after the stalled row existed and beat was running):

```
worker-1  | [2026-09-08 21:49:22,735: INFO/MainProcess] Task review.tasks.reap_stalled_runs[8aefaf59-...] received
worker-1  | [2026-09-08 21:49:22,805: WARNING/ForkPoolWorker-2] stalled_check_runs_reaped count=1 service=CheckRunExecutor
worker-1  | [2026-09-08 21:49:22,806: INFO/ForkPoolWorker-2] Task review.tasks.reap_stalled_runs[8aefaf59-...] succeeded in 0.069s: 1
```

Row state read straight back from the database right after, with no sweep call issued by
this session:

```
82aaf8b9-04f3-438b-8fd9-88bdea14908a failed 2026-09-08 21:46:12.736900+00:00 2026-09-08 21:49:22.741698+00:00 stalled \
  "The worker running this check stopped responding."
```

**The false-positive direction** — at that same 21:49:22 tick, the second, genuinely
young `RUNNING` row (10s old, well inside the 60s cutoff) was left alone:

```
eef19228-926c-4c10-b05e-59b0adabc047 running 2026-09-08 21:49:12.744247+00:00
```

confirmed again at the next three ticks (21:49:37, 21:49:52, 21:50:07 — all
`reap_stalled_runs[...] succeeded ...: 0`) while it remained inside the window. It was
only ever reaped once it, too, genuinely crossed the 60s cutoff at the 21:50:22 tick with
no worker having ever finished it — which is the sweep working correctly a second time
on a second row, not a false positive: nothing in this system distinguishes "a live
worker is still running this" from "a worker died holding this" except elapsed time past
`CHECK_RUN_STALL_SECONDS`, which is the entire, documented contract of `stalled()`.

**The review can be checked again without manual intervention** — calling the real
`ReviewService.request_check` (the same call the `/check/` endpoint makes) against the
review that had the stalled run, with no sweep invoked first:

```
check_requested review_id=dd2bb3a2-2bd0-4940-b267-2f1ff2d7bae6 run_id=8e1dfd8f-15b3-4c44-9d23-ebb1b357cef1
NEW_RUN_UUID 8e1dfd8f-15b3-4c44-9d23-ebb1b357cef1 STATUS pending
```

No `ConflictError` — `MAX_IN_FLIGHT_RUNS=1` no longer sees a phantom in-flight run,
because beat already ended it. The new run ran end to end on the real worker, over the
real fixture files, to a real terminal result:

```
8e1dfd8f-15b3-4c44-9d23-ebb1b357cef1 succeeded FAIL 2026-09-08 21:50:03.377567+00:00 2026-09-08 21:50:03.665080+00:00
```

### NOT DONE

- Whether `_reap_lost_dispatch` (T-0056's PENDING-side sweep) should also run from this
  same beat tick is explicitly out of scope here per the task's own text — left for
  T-0085.
- The beat scheduler used is Celery's built-in file-backed `PersistentScheduler` (its
  default, visible in the log as `. scheduler -> celery.beat.PersistentScheduler`), which
  keeps its due-time bookkeeping in a local file inside the `beat` container rather than a
  shared store. A `beat` container restart re-triggers already-due tasks a few seconds
  early rather than skipping a tick — harmless here because `reap_stalled_runs` is
  idempotent (see §3), but worth naming: this is not `django-celery-beat`'s
  database-backed scheduler, which was not introduced because nothing in this task
  needed cross-restart schedule persistence beyond what idempotency already covers.

## Review

**Verdict:** no invariant violated. The wiring, the idempotency claim, and every log/DB
excerpt in the evidence were independently re-verified against the live stack rather than
taken on trust -- the reviewer re-derived the beat→worker→DB path from scratch, including
one thing the builder's own evidence never exercised: a real, unoverridden
`CHECK_RUN_STALL_SECONDS=1800` tick (beat started `21:53:02`, first tick `22:00:32`, exactly
`1800/4 = 450s` later, consumed by the worker). Two hazards the reviewer went looking for on
their own initiative -- `CELERY_TASK_ROUTES` globbing the reap task onto the wrong queue
behind CPU-bound checks, and `acks_late` redelivery resurrecting a row the reaper had already
failed -- were both checked against the real routing config and `_claim`/`execute()` and
disproven, not just asserted safe.

**Fixed now:**

1. **No regression test tied the beat schedule to the task registry.** `CELERY_BEAT_SCHEDULE`'s
   `"task"` string and `tasks.py`'s `name=` are two independently-editable strings that nothing
   in `make verify` compared -- a rename or typo on either side would make beat dispatch a
   message nothing answers, the worker would log `NotRegistered`, and the review would go back
   to being permanently stuck with a fully green test suite. Added
   `services/api/cadgpt/tests/test_celery_beat_schedule.py`, asserting every task named in
   `settings.CELERY_BEAT_SCHEDULE` is in the Celery app's task registry. Mutation-verified: a
   temporary typo in the `"task"` string made the new test fail for the stated reason
   (`AssertionError` on `scheduled <= app.tasks.keys()`); restored, passes. The first version of
   the test relied on `app.tasks` already being populated by import side effects from whatever
   pytest happened to collect first -- passed alone, but that was order-dependent, not a real
   check. Fixed by calling `app.loader.import_default_modules()` in the test itself, the same
   call a real worker's bootstep makes, so the test's discovery matches production's rather than
   an accident of collection order. `make verify` re-run clean after: 239 passed (238 + this
   one), 5/5 contracts, mypy clean.
2. **Two decisions the task settled were undocumented outside the task file.** The scheduler
   choice (`PersistentScheduler` over `django-celery-beat`) and the interval derivation
   (`stall/4`) are exactly the kind of thing CLAUDE.md requires in `docs/decisions.md` so they
   survive context loss. Logged as "`reap_stalled_runs` gets a Celery beat schedule, on Celery's
   built-in scheduler" (2026-09-08), including the single-instance `beat` assumption the
   reviewer surfaced (`--scale beat=2` would double every tick -- harmless because idempotent,
   but undocumented until now).

**Queued, not fixed here:**

- **T-0085** already exists and already covers "should this same tick also run T-0056's
  `_reap_lost_dispatch`" -- explicitly out of this task's scope per its own text, unaffected by
  the review.

**Noted, no action:**

- The stray `.gitignore` change (four lines for `/.cadgpt/inbr/`, an unrelated in-progress
  branch's artifact) is pre-existing in the working tree, not part of this task's diff, and is
  excluded from this task's commit -- same disposition as in T-0056's review.
- `docs/plan.md` still listed T-0084 under backlog at review time; the coordinator updates it
  as part of closing this task out, not as a finding against the builder.
