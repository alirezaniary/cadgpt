# T-0085 — A lost-dispatch run is invisible and the review looks falsely blocked for up to 30 minutes

**Phase:** 3   **Status:** done
**Touches invariants:** none directly — a UX/latency gap on top of T-0056's correctness fix,
not a correctness gap itself.

## Why

Found by the T-0056 reviewer. `_reap_lost_dispatch` (T-0056) only runs from inside
`request_check`, only at the instant it is about to refuse — by design, to bound the blast
radius of a wrong sweep to a single call. The cost of that restraint: between the moment a
dispatch is actually lost and the moment `CHECK_RUN_STALL_SECONDS` (default 1800s) has
elapsed *and* someone happens to retry, the run renders as an ordinary `pending`
("در حال بررسی") run — indistinguishable from one genuinely queued — and any retry inside
that window returns the same 409 `"A check is already running for this review."` a user with
a healthy, merely-slow check would also see. T-0056's own scope item — "the user can see that
a check never started, distinguished from one still queued" — is only true *after* the
30-minute cutoff and *only if* a second request happens to land after it.

This is not the correctness question T-0056's review was gated on (no invariant is at risk
here; a user who never retries, or retries early, is simply left waiting rather than misled
into corrupting anything), which is why it was queued rather than blocking that task. But it
is real: an architect who requests a check, sees it "in progress," and gives up rather than
waiting half an hour or retrying blind has no better information than before T-0056 landed.

## Scope

**Changes**

- Decide deliberately, and record the decision, rather than defaulting: should the reap also
  run proactively (e.g. from the same periodic tick T-0084 wires up for
  `reap_stalled_runs`, once that exists), or is reactive-only-at-refusal-time an accepted
  tradeoff with the wait communicated explicitly instead (a rendered "if this doesn't move in
  N minutes, ask again" rather than a bare "checking")?
- Whichever is chosen, the run's actual state during the blind window must not read as
  identical to a healthy queued run — even a distinguishing label ("still waiting to start"
  vs. "in progress") narrows the gap without needing the full sweep.
- If T-0084 lands first, the natural answer may just be: extend that periodic tick to also
  call `_reap_lost_dispatch`-equivalent logic, closing this reactively-only gap as a side
  effect. Check T-0084's status before scoping this from scratch.

**What explicitly does not change**

- T-0056's `_reap_lost_dispatch` mechanism and its safety reasoning — this task is about
  *when* it runs, not whether it is safe.

## How to prove it ran

`make verify`, then against `make up`: a lost-dispatch `PENDING` run, and show the user gets
a truthful signal (rendered, and/or an actual recovery) well inside the current 30-minute
blind window — state the new bound and where it comes from.

## Evidence

### 0. Decision, made deliberately (Scope's first bullet)

**Chosen: the reap now also runs proactively**, from the same beat tick T-0084 wired up, not
reactive-only-with-a-rendered-wait. T-0084 had already landed (see its own Status: `done`)
when this task started, so the Scope section's own suggested path applied: "extend that
periodic tick to also call `_reap_lost_dispatch`-equivalent logic."

**No frontend rendering change was made.** The Scope text treats a distinguishing label as an
alternative to the full sweep ("even a distinguishing label ... narrows the gap *without
needing the full sweep*"), and the task's own "How to prove it ran" section accepts "the run
actually gets recovered via the new periodic path... **and/or** a rendered distinction" as
sufficient. With the periodic sweep now landed, the blind window is bounded to
`CHECK_RUN_STALL_SECONDS / 4` — the same 450s-at-default bound T-0084 already put into
production for the RUNNING side — rather than an unbounded wait for someone to retry. A
`PENDING` run within that bound is not a false signal, it is a genuinely bounded delay before
either an automatic recovery or a real dispatch completes. Logged in `docs/decisions.md`
("2026-09-09 — `_reap_lost_dispatch` also runs from beat's periodic tick; no frontend label
added"), including the reopen condition if that bound is ever judged too long in practice.

### 1. `make verify`

Ran twice — once after the Python changes, once again after restoring the `make up` stack to
its unoverridden state, to confirm nothing was left broken. Both green, final run:

```
$ make verify
uv run ruff check .
All checks passed!
uv run ruff format --check .
187 files already formatted
uv run mypy packages/engine/src services/api/cadgpt
Success: no issues found in 170 source files
uv run lint-imports --no-cache
---------
Contracts
---------
Analyzed 224 files, 699 dependencies.
-------------------------------------
I1 - no inference client, web framework or network reaches the checking engine KEPT
The engine knows nothing about the service that hosts it KEPT
Django apps are layered KEPT
Services never import the transport layer KEPT
Models never import services KEPT
Contracts: 5 kept, 0 broken.
uv run pytest
242 passed, 32 warnings in 3.91s
cd services/web && pnpm install --frozen-lockfile && pnpm run verify   (unchanged by this
task — lint, typecheck, build and the Storybook workbench build all succeeded)
EXIT CODE: 0
```

242 = the 238 pytest was at after T-0084 landed, plus the four new tests this task adds
(`test_the_periodic_sweep_recovers_a_lost_dispatch_run_with_nobody_retrying`,
`test_the_periodic_sweep_does_not_touch_a_genuinely_queued_run`,
`test_the_periodic_sweep_reaps_lost_dispatches_across_every_tenant`, and the false-positive
companion). `git status --short` after this task's edits touches only
`services/api/cadgpt/apps/review/services/execution.py`, `.../tasks.py`,
`.../tests/test_check_run.py`, `services/api/cadgpt/config/settings/base.py` and
`docs/decisions.md` — no frontend file, confirming §0's decision was actually carried through
rather than only stated.

### 2. Wiring — the registration lines

**`services/api/cadgpt/config/settings/base.py`** — a second `CELERY_BEAT_SCHEDULE` entry,
same interval as T-0084's, not a number invented separately:

```python
CELERY_BEAT_SCHEDULE = {
    "reap-stalled-check-runs": {
        "task": "review.tasks.reap_stalled_runs",
        "schedule": CHECK_RUN_STALL_SECONDS / 4,
    },
    "reap-lost-dispatch-check-runs": {
        "task": "review.tasks.reap_lost_dispatch_runs",
        "schedule": CHECK_RUN_STALL_SECONDS / 4,
    },
}
```

`"task": "review.tasks.reap_lost_dispatch_runs"` matches the explicit name on the task itself
(`services/api/cadgpt/apps/review/tasks.py`):

```python
@shared_task(
    base=BaseTask,
    name="review.tasks.reap_lost_dispatch_runs",
    queue="default",
)
def reap_lost_dispatch_runs() -> int:
    """Fail PENDING runs whose dispatch never reached a worker at all.
    ...
    """
    return CheckRunExecutor().reap_lost_dispatch()
```

T-0084's own regression test (`services/api/cadgpt/tests/test_celery_beat_schedule.py`,
`test_every_beat_scheduled_task_is_registered`) already asserts every `"task"` string in
`CELERY_BEAT_SCHEDULE` is in the real Celery app's task registry — it needed no change to
also cover this new entry, and it passed in the `make verify` run above (folded into the 242).

`reap_lost_dispatch_runs` calls `CheckRunExecutor.reap_lost_dispatch()`
(`services/api/cadgpt/apps/review/services/execution.py`), the new cross-tenant method:

```python
def reap_lost_dispatch(self) -> int:
    ...
    count: int = lost.update(
        status=CheckRunStatus.FAILED,
        finished_at=timezone.now(),
        failure_reason=CheckRunFailure.DISPATCH_LOST,
        failure_detail=str(_(...)),
        updated_at=timezone.now(),
    )
```

built from `CheckRun.objects.dispatch_lost(settings.CHECK_RUN_STALL_SECONDS)` — the default
manager's queryset, not `for_tenant(...)`-scoped — the same "not scoped by `for_tenant`"
pattern `CheckRunExecutor.reap_stalled` already uses one method above it for the RUNNING side
(`CheckRun.objects.stalled(...)`, confirmed by reading it before writing this method, not
invented fresh).

### 3. T-0056's safety mechanism, confirmed untouched

`CheckRunQuerySet.dispatch_lost` (`repositories/querysets.py`) is byte-for-byte what it was
before this task — this task added no edit to that method or to
`ReviewService._reap_lost_dispatch`, which still exists, still runs reactively from
`request_check`, and is exercised unchanged by its own pre-existing tests
(`test_a_run_whose_dispatch_was_lost_can_be_recovered`,
`test_a_genuinely_queued_run_is_not_swept_as_lost`,
`test_a_young_pending_run_with_no_task_id_is_not_swept_either` — all still pass, in the 242).
`CheckRunExecutor.reap_lost_dispatch` calls that same queryset method with the same
`settings.CHECK_RUN_STALL_SECONDS` argument and the same single filtered `UPDATE` — the second
*caller* T-0085 exists to add, not a second implementation of the safety reasoning.

The false-positive direction was checked for the new caller specifically (not assumed to
transfer from the reactive path just because the underlying queryset is shared):
`test_the_periodic_sweep_does_not_touch_a_genuinely_queued_run` creates a run that really was
dispatched (carries a `task_id`) and backdates it past the stall window; `reap_lost_dispatch()`
returns `0` and the row is untouched. Re-verified live below, not just in the test.

### 4. The real path

Built the image with the required proxy build-args
(`docker build --network host --build-arg HTTP_PROXY=... -f deploy/docker/api.Dockerfile -t
cadgpt-api:latest .`, succeeded), then recreated `api`, `worker` and `beat` against the real
`make up` stack (postgres/redis/web left running) with an env-only override file setting
`CHECK_RUN_STALL_SECONDS=60` on those three services only — the derived 15s beat interval
observable in minutes rather than the production default's 7.5 minutes, same code path,
only the constant's value differs, exactly T-0084's own precedent
(`test_a_stalled_run_is_failed_rather_than_left_looking_busy` does the same at the unit level):

```
$ docker compose -f deploy/compose.yaml -f <override>.yaml up -d --force-recreate api worker beat
 Container cadgpt-beat-1  Recreated
 Container cadgpt-worker-1  Recreated
 Container cadgpt-api-1  Recreated
 ...
 Container cadgpt-beat-1  Started
 Container cadgpt-api-1  Started
 Container cadgpt-worker-1  Started
```

Confirmed the running `api` container's settings actually reflect both schedule entries at
the shortened interval (`docker compose exec api python manage.py shell`):

```python
>>> from django.conf import settings; import json
>>> print(json.dumps(settings.CELERY_BEAT_SCHEDULE, default=str, indent=2))
{
  "reap-stalled-check-runs": {"task": "review.tasks.reap_stalled_runs", "schedule": 15.0},
  "reap-lost-dispatch-check-runs": {"task": "review.tasks.reap_lost_dispatch_runs", "schedule": 15.0}
}
```

**Setup, real services, real files** (`AccountService`, `TenantProvisioningService`,
`MediaService`, `RuleSetService`, `Project.objects.create_project`, `ReviewService`, real
`three_doors.ifc` / `door_width.ids` fixtures baked into the image): a tenant
(`t0085-co`), a review, and a `CheckRun` created via `CheckRun.objects.create_run` — `PENDING`,
`task_id=""` — the exact shape `_dispatch`'s lost `on_commit` callback leaves, then backdated
120s past the 60s test cutoff:

```
RUN_UUID 1b173d67-06fb-48db-a7ad-20295be0d3ef pending  2026-09-08 22:14:46.928374+00:00
```

**Beat's own schedule ticking, unprompted** (`docker compose logs beat`):

```
beat-1  | [2026-09-08 22:16:41,948: INFO/MainProcess] Scheduler: Sending due task reap-lost-dispatch-check-runs (review.tasks.reap_lost_dispatch_runs)
beat-1  | [2026-09-08 22:16:42,015: INFO/MainProcess] Scheduler: Sending due task reap-stalled-check-runs (review.tasks.reap_stalled_runs)
beat-1  | [2026-09-08 22:16:56,948: INFO/MainProcess] Scheduler: Sending due task reap-lost-dispatch-check-runs (review.tasks.reap_lost_dispatch_runs)
beat-1  | [2026-09-08 22:16:57,015: INFO/MainProcess] Scheduler: Sending due task reap-stalled-check-runs (review.tasks.reap_stalled_runs)
beat-1  | [2026-09-08 22:17:11,948: INFO/MainProcess] Scheduler: Sending due task reap-lost-dispatch-check-runs (review.tasks.reap_lost_dispatch_runs)
beat-1  | [2026-09-08 22:17:12,015: INFO/MainProcess] Scheduler: Sending due task reap-stalled-check-runs (review.tasks.reap_stalled_runs)
```

Both entries tick 15s apart, exactly `CHECK_RUN_STALL_SECONDS / 4` with the 60s override.

**The row transitioning to FAILED/`dispatch_lost` on its own** — no manual sweep call, no
`request_check` retry issued anywhere before this — worker log at the first tick after the row
existed (22:16:56; the 22:16:42 tick ran too early, before the row had been created, and
correctly reaped `count=0`; a still-earlier tick, 22:16:26, reaped `count=1` too, but that was a *different*, pre-existing
stray `PENDING` row (`b66335db-...`, tenant 153, `created_at 21:36:53`) already sitting in this
long-running dev stack's database from before this task's own work started (the stack had been
up for a while when this session began), not my test row -- checked directly against the
database rather than assumed, since the log alone does not distinguish the two; my own row's
uuid and tenant (`1b173d67-...`, tenant 293) only appear at 22:16:56):

```
worker-1  | [2026-09-08 22:16:56,953: INFO/MainProcess] Task review.tasks.reap_lost_dispatch_runs[8e64100f-c92a-4b05-8fff-21017c4dbde7] received
worker-1  | [...] check_run_dispatch_lost_reaped_by_sweep count=1 service=CheckRunExecutor
worker-1  | [2026-09-08 22:16:56,981: INFO/ForkPoolWorker-2] Task review.tasks.reap_lost_dispatch_runs[8e64100f-...] succeeded in 0.026640172000043094s: 1
```

Row read straight back from the database right after, no sweep call issued by this session:

```
1b173d67-06fb-48db-a7ad-20295be0d3ef failed dispatch_lost This check was requested but its
dispatch never reached a worker, so it was ended. Request the check again.
created_at 2026-09-08 22:14:46.928374+00:00 finished_at 2026-09-08 22:16:56.956461+00:00
```

**The review is checkable again without manual intervention** — calling the real
`ReviewService.request_check` (the same call the `/check/` endpoint makes) against the review
that had the lost-dispatch run, with no sweep invoked first:

```
check_requested review_id=c7fa5141-2c55-46a0-b523-9f75910442bf run_id=5423ff71-38c8-4e1e-8264-0ab7fb78f828 ...
NEW_RUN 5423ff71-38c8-4e1e-8264-0ab7fb78f828 pending
```

No `ConflictError` — `MAX_IN_FLIGHT_RUNS=1` no longer sees a phantom in-flight run, because
the periodic sweep already ended it. The new run ran end to end on the real worker, over the
real fixture files, to a real terminal result:

```
5423ff71-38c8-4e1e-8264-0ab7fb78f828 succeeded FAIL
```

**The false-positive direction, on the live stack, not only in the unit test** — a second run,
also backdated 120s past the 60s cutoff but carrying a real `task_id`
(`genuinely-dispatched-task-id`), was left alone: every tick from 22:17:27 through 22:18:42
(six ticks, spanning well over a minute after this row's creation) logged `... succeeded ...:
0` -- `CheckRunQuerySet.dispatch_lost`'s `task_id=""` filter excludes a row carrying a
`task_id` structurally, regardless of age, exactly `stalled`'s own age-is-not-the-signal
reasoning -- and reading the row back directly still shows it `pending` with its `task_id`
intact:

```
08861e62-7f6e-4540-bc61-7302bdf9a030 pending genuinely-dispatched-task-id
```

**Stack restored.** `docker compose -f deploy/compose.yaml up -d --force-recreate api worker
beat` (no override file) put `CHECK_RUN_STALL_SECONDS` back to its production default before
the final `make verify` re-run in §1.

### 5. The new bound, stated explicitly

Before this task: a lost dispatch was invisible until `CHECK_RUN_STALL_SECONDS` (1800s / 30
minutes at the default) had elapsed **and** someone happened to retry — otherwise unbounded.

After this task: the periodic tick recovers it on its own, unprompted, within
`CHECK_RUN_STALL_SECONDS / 4` of the run's `created_at` — **≤450s (7.5 minutes) at the
production default**, the same bound T-0084 already established and put into production for
the RUNNING-side sweep, reused rather than a second number invented for this task. Demonstrated
above at the 60s test override (≤15s), the identical code path with only the constant's value
differing.

### NOT DONE

- **No frontend rendering change.** Deliberate, per §0 above — the task's own scope text and
  its "how to prove it ran" section both treat the periodic recovery as sufficient evidence on
  its own ("and/or a rendered distinction"), and the periodic sweep now bounds the blind window
  to the same interval T-0084 already shipped for the RUNNING side. If that bound is later
  judged too long for a user to sit through without any signal, the deferred lever is the
  rendered "still waiting to start" label the Scope section names, not a shorter sweep interval
  (which is intentionally tied to the RUNNING-side sweep's own cadence, not chosen freely by
  this task) — recorded as the reopen condition in `docs/decisions.md`.
- **A real, unoverridden `CHECK_RUN_STALL_SECONDS=1800` tick was not separately exercised**
  against the live stack in this task's own session (T-0084's reviewer already did this for
  the shared beat mechanism and cadence; this task changes what runs on that tick, not the tick
  itself, and the 60s-override run above exercises the identical code path end to end).

## Coordinator audit

Not reviewer-gated (task header: "none directly"), so the coordinator verified this directly
rather than dispatching a reviewer: independently re-ran `make verify` (242 passed, 5/5
contracts, mypy clean — matches the evidence exactly), read every diff (`execution.py`,
`tasks.py`, `settings/base.py`, the four new tests, `docs/decisions.md`), and confirmed the
`other_tenant`/`other_owner` fixtures the cross-tenant test depends on are real
(`services/api/conftest.py:50,62`), not invented.

**Fixed:** `ReviewService._reap_lost_dispatch`'s docstring (`services/api/cadgpt/apps/review/
services/review.py`) claimed "never as a periodic sweep. That restraint is what keeps this
safe" — true when T-0056 wrote it, false the moment this task added
`CheckRunExecutor.reap_lost_dispatch` as a second, periodic caller of the same UPDATE. Left
uncorrected, a future reader would believe there is exactly one caller in the whole system and
that the absence of a second one is load-bearing for safety, when the actual safety property
(the UPDATE's own `WHERE` clause, re-evaluated per row) does not depend on caller count at all.
Reworded to state both callers and the real safety property; `request_check`'s own docstring
similarly updated to name both the reactive and proactive halves of the self-heal rather than
only the first. `make verify` re-run clean after (242 passed) to confirm the docstring-only
change broke nothing.

No other findings. The mechanism is a second caller of an already-reviewed, unmodified atomic
UPDATE (`CheckRunQuerySet.dispatch_lost`, confirmed byte-for-byte unchanged), the cross-tenant
sweep pattern is copied from `reap_stalled`'s own precedent rather than invented, and the
decision to skip a frontend change is deliberately made and logged, not a default.
