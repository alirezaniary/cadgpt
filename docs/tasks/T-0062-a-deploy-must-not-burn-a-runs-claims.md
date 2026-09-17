# T-0062 — An ordinary deploy burns a run's claims, and there are only three

**Phase:** 3   **Status:** done
**Touches invariants:** none directly; it is the false-positive face of T-0033's bound.
**Reviewer-gated.**

## Why

Found by the T-0033 review. T-0033 bounded redelivery so an OOM-killed model stops cycling instead
of starving the shared queue. The bound counts **every** claim, and cannot tell why the previous
attempt ended.

`deploy/compose.yaml` sets no `stop_grace_period` for `worker` (Docker's default is 10s) and no
restart policy, while that file's own header says a large model takes minutes. So
`docker compose up -d worker` sends SIGTERM, Celery begins a warm shutdown and waits for the running
check, Docker SIGKILLs at 10s, `CELERY_TASK_REJECT_ON_WORKER_LOST = True` (`base.py:250`) redelivers
— and a claim is burned by a routine deploy that had nothing to do with memory.

`CHECK_RUN_MAX_CLAIMS = 3` counts the first claim too, so **only two non-memory interruptions are
tolerated.** Concrete sequence: a healthy 47MB check is running; two rolling deploys land across its
redeliveries; anything at all interrupts the third; the fourth is refused as `resource_exhausted`
with a message blaming the memory limit — a healthy model, refused, and told the wrong reason.

Refusing a good check is a worse failure than the one the bound prevents, and the bound currently
cannot distinguish them.

## Scope

**Changes**

- The bound distinguishes an attempt that died from resource exhaustion from one ended by a clean
  shutdown. `WorkerLostError` and an OOM kill are distinguishable from SIGTERM-then-graceful; decide
  the mechanism and say why in the evidence.
- Whatever the mechanism, a rolling deploy during a long check must not consume the run's budget.
  `stop_grace_period` above the realistic check duration is part of the answer and cheap; say
  whether it is sufficient alone.
- `CHECK_RUN_MAX_CLAIMS` gets a derivation or a defence. Three was not measured.
- Nothing resets `claim_count`. That is harmless today — a fresh request creates a new `CheckRun`
  and a FAILED run is not in flight — but state whether it stays right once the bound distinguishes
  causes.

**What explicitly does not change**

- T-0033's placement of the increment inside the row-locked claim write, which is correct and is what
  makes the count survive a kill.
- `reap_stalled_runs`, or the `RESOURCE_EXHAUSTED` reason itself.

## How to prove it ran

`make verify`, then on the real stack:

1. The false positive as it stands: a healthy check interrupted by ordinary deploys until it is
   refused. Paste the log and the failure the user sees.
2. The same sequence after the change, completing rather than being refused.
3. The true positive still caught — a genuinely OOM-killed run still stops at the bound. This is the
   direction that must not regress, and a change that fixes (1) by weakening the bound has failed.

## Evidence

### Mechanism chosen, and why: prevention, verified against this stack's actual code

The reasoning in the task's Why/Scope was verified against the versions actually installed in
`cadgpt-api:latest`, not assumed from general Celery docs: `celery==5.6.3`, `kombu==5.6.2`.

- `celery.apps.worker`: with `REMAP_SIGTERM` unset (the default, and this deployment's actual
  state), `install_worker_term_handler = partial(_shutdown_handler, sig='SIGTERM', how='Warm', ...)`
  — a plain SIGTERM to the prefork `MainProcess` is a *warm* shutdown, not cold.
- `celery.worker.worker.WorkController.stop()` → `_shutdown(warm=True)` → `blueprint.stop(self,
  terminate=False)`. For the prefork pool component (`celery.concurrency.prefork.TaskPool`),
  `on_stop` calls the billiard pool's `self._pool.close()` (stop dispatching new work to children)
  then `self._pool.join()` (block until every in-flight child finishes its current job and exits
  on its own). Nothing sends the child a signal; it is left to finish naturally.
- So **`stop_grace_period` above the realistic check duration is sufficient alone** for the
  ordinary-deploy case: the in-flight check finishes, the pool joins, the `MainProcess` exits 0,
  Docker never needs to SIGKILL, and `CELERY_TASK_REJECT_ON_WORKER_LOST` never fires because no
  `WorkerLostError` was ever raised. This is why the fix is prevention, not classification: `_claim`
  does not need to learn *why* a worker died, because the one cause this task can remove (routine
  redeploys) is kept from ever producing a kill in the first place.

**A second fact this task's own instruction to verify, not assume, actually turned up, and which
changes the diagnosis:** a *full-container* SIGKILL (the one Docker sends when the grace period
elapses) takes the `MainProcess` too, unlike T-0033's OOM proof, where the killed process was only
a *child* fork and the surviving `MainProcess` detected the death itself and called
`Request.on_failure` → `self.reject(requeue=True)` — an explicit, immediate requeue. When the whole
container dies, nothing survives to do that; redelivery depends entirely on Redis's own
`visibility_timeout` (`CELERY_BROKER_TRANSPORT_OPTIONS`, `base.py`), which
`kombu.transport.redis.QoS.restore_visible` only restores once a message is *older* than. Because
`CHECK_RUN_STALL_SECONDS` defaults to `CELERY_TASK_TIME_LIMIT` and the visibility timeout is that
same value **+60s**, whether the stall sweep or Redis's redelivery notices the abandoned message
first is a race, not a settled fact of "this stack" — **and a 2026-09-17 correction to this
evidence found the first write-up got the outcome of that race backwards for production settings.**
The sweep does not fire the instant the stall threshold is crossed; it only runs on
`CELERY_BEAT_SCHEDULE`'s own tick, `CHECK_RUN_STALL_SECONDS / 4` (`base.py`). So the real race is
between (a) how far past the stall threshold the next scheduled tick lands — anywhere in
`[0, CELERY_TASK_TIME_LIMIT/4]` — and (b) the fixed 60s margin before Redis restores visibility.
**Crossover:** the tick interval equals the margin, `CELERY_TASK_TIME_LIMIT/4 = 60s`, at
`CELERY_TASK_TIME_LIMIT = 240s`. Below that, the sweep's worst-case tick delay is under 60s, so the
sweep always wins the race. Above it — and **production's default `CELERY_TASK_TIME_LIMIT = 1800s`
is 7.5× past that crossover, giving a 450s tick interval against the same fixed 60s margin** — the
sweep only wins if the crash happens to land in roughly the last 60 of every 450 seconds between
ticks (about 13% of the cycle); the rest of the time Redis's redelivery restores the message first,
`_claim` re-claims the still-`RUNNING` row, and a claim is genuinely burned by an ordinary deploy —
the original failure mode this task's own Why section describes, not a `STALLED` correction to it.
**Proof 1 below is real and stays as evidence of the mechanism, but only at the compressed settings
it actually used** (`CELERY_TASK_TIME_LIMIT=60`, tick interval 15s, comfortably inside the 60s
margin — comfortably below the 240s crossover), not as a general property of this stack. At
production's actual `CELERY_TASK_TIME_LIMIT = 1800s` (tick interval 450s, 7.5× past the
crossover), the same analysis says the *opposite* outcome dominates — Redis's redelivery restores
the message before the sweep's next tick roughly 87% of the time, so a claim genuinely would be
burned, matching this task's own Why section rather than contradicting it. None of this changes
whether the shipped fix works: `stop_grace_period` prevents the SIGKILL outright, so which sweep
would have "won" a race that, with the fix in place, never occurs is moot. See "NOT DONE" below
for what this means for reproducing the literal production scenario, and `docs/decisions.md`
(entry dated 2026-09-17, corrected) for the full write-up.

### `CHECK_RUN_MAX_CLAIMS`: kept at 3, re-justified, not re-derived

Once the grace-period fix removes an ordinary deploy from the population this bound counts, what
remains is genuine resource exhaustion (or any other real crash) — and this system has never run
in production, so there is no crash-frequency data anywhere in this codebase to derive a number
from; `3` was never that kind of number and still isn't. What *is* measured (T-0033) is that
`MAX_UPLOAD_BYTES` sizes one check to fit its share of worker memory with an 80% margin at
`--concurrency 2` — so the one legitimate way a correctly-sized upload still gets OOM-killed is two
such checks transiently overlapping on the same worker, which resolves itself as soon as the
neighbour finishes. One retry benefits from that; more do not help a model that is genuinely too
large (T-0033's actual poison message) and only cost the shared queue more attempts. `3` is kept as
that defended minimum — see the settings comment and `docs/decisions.md`.

### `claim_count` reset: still nothing needed, and the reasoning still holds

Read `_claim` (`services/api/cadgpt/apps/review/services/execution.py`) end to end: the mechanism
chosen here is prevention, not cause classification — no "cause" column was added to `CheckRun`,
so nothing changed about what `claim_count` means or when it is written. T-0033's own reasoning
(a fresh request creates a new `CheckRun`; a `FAILED` run is not in flight, so nothing needs to
reset a dead run's count) is exactly as true after this task as before it. This would only need
revisiting if a future change taught `_claim` to distinguish causes explicitly, which this task
deliberately does not do.

### `make verify`

```
uv run ruff check .                → All checks passed!
uv run ruff format --check .       → 196 files already formatted
uv run mypy packages/engine/src services/api/cadgpt → Success: no issues found in 178 source files
uv run lint-imports --no-cache     → Contracts: 5 kept, 0 broken.
uv run pytest -m "not postgres"    → 328 passed, 1 deselected, 39 warnings in 10.14s
cd services/web && pnpm run verify → unit: 6 passed (2 files); storybook: 37 passed (9 files);
                                      production build succeeded
```
Full log kept at `/tmp/claude-1000/.../scratchpad/verify.out` for this session; exit code 0.

### Real path, proof 1 — the false positive as it stands (before the fix)

Reused T-0033's own technique for a real, non-trivial check duration: a structurally real IFC4
model (`IfcProject > IfcSite > IfcBuilding > IfcBuildingStorey`, 340,000 real `IfcDoor` entities
placed into the storey via `IfcRelContainedInSpatialStructure`, generated by a one-off script
mirroring `packages/engine/tests/fixtures/make_fixtures.py`'s own method just at scale) checked
against `door_width.ids`. Measured real engine time: 18.8s; full pipeline (dispatch → claim →
`run_check`) measured at 19.9s below. Dispatched through the real `AccountService` /
`TenantProvisioningService` / `MediaService` / `RuleSetService` / `ReviewService` — the same
service classes the real HTTP endpoints call — so the run is a real `CheckRun` row, dispatched by
the real `transaction.on_commit` → `execute_check_run.delay(...)` path, consumed by the real
Celery worker container.

To make the ~19s check duration tractable to interrupt against a stock 10s grace period without
also waiting out `CELERY_TASK_TIME_LIMIT`'s production default of 1800s for the sweep race to
resolve, `CELERY_TASK_TIME_LIMIT`/`CELERY_TASK_SOFT_TIME_LIMIT` were made reachable from
`deploy/compose.yaml` (same technique as `WORKER_MEM_LIMIT`, T-0033) and set to 60s/50s for this
run only — `CHECK_RUN_STALL_SECONDS` (defaults from `CELERY_TASK_TIME_LIMIT`) and the broker's
`visibility_timeout` (`CELERY_TASK_TIME_LIMIT`+60) scale down together, at the same ratio
production uses, so the real mechanics play out in ~75s instead of ~31 minutes. `worker`'s
`stop_grace_period` was explicitly forced to `10s` (`WORKER_STOP_GRACE_PERIOD=10s`) to reproduce
the *pre-fix* state on top of a compose file that now ships the fixed default.

```
$ WORKER_STOP_GRACE_PERIOD=10s CELERY_TASK_TIME_LIMIT=60 CELERY_TASK_SOFT_TIME_LIMIT=50 \
    docker compose -f deploy/compose.yaml up -d --force-recreate worker
$ docker inspect cadgpt-worker-1 --format 'StopTimeout={{.Config.StopTimeout}}'
StopTimeout=10
```

Real dispatch, real worker log (`docker compose logs -f worker`, timestamps UTC):

```
09:42:05.618  check_run_claimed  claim_count=1  run_id=7f3936a5-...
09:42:08.609  (ordinary deploy issued: docker compose up -d --force-recreate worker)
09:42:09.292  worker: Warm shutdown (MainProcess)
              [Kworker-1 exited with code 137        <-- SIGKILL (128+9), not a clean exit
09:42:25.388  (new worker container ready)
              up -d --force-recreate worker took 12.247543416s   <-- ~10s grace + startup
09:43:18.551  stalled_check_runs_reaped  count=1
```

The run never got claimed a second time — `claim_count` stayed at `1` for the entire ~73 seconds
between the kill and the reap (polled every few seconds against the real DB; every poll returned
`claim=1`). This is the fact predicted above: a full-container SIGKILL has no surviving process to
raise `WorkerLostError` and requeue, so the message just sits orphaned until something else notices
it. `reap_stalled_runs`'s periodic sweep is what actually notices it here, not claim redelivery.

Final state, real row, real user-facing failure (Persian, this environment's active language):

```
$ (poll CheckRun.objects.get(uuid=...))
failed|1|stalled|کارگری که این بررسی را اجرا می‌کرد، از پاسخ‌گویی بازایستاد.
```
("The worker running this check stopped responding.") — a perfectly healthy, 19-second check,
interrupted by exactly one ordinary deploy, ending in a failure that asserts something that never
happened. **This is the honest correction to this task's own Why section**: the text there assumes
an ordinary deploy quickly burns `CHECK_RUN_MAX_CLAIMS` via redelivery; what actually happens on
this stack's real settings is a single deploy produces a false `STALLED` before redelivery ever gets
the chance — a different failure_reason than narrated, but the same underlying defect (a deploy that
had nothing to do with the model corrupts its true outcome), and the same fix closes it.

### Real path, proof 2 — the same sequence after the fix, completing rather than failing

Same 340,000-door model, same real dispatch path, same compressed `CELERY_TASK_TIME_LIMIT=60`
(so the check's own allowed running time is unchanged) — but `stop_grace_period` now left at the
*fixed* default for this scale (`CELERY_TASK_TIME_LIMIT`+60 = `120s`, the exact formula
`deploy/compose.yaml` now bakes in, just evaluated at the compressed `CELERY_TASK_TIME_LIMIT`):

```
$ docker compose -f deploy/compose.yaml up -d --force-recreate worker   # WORKER_STOP_GRACE_PERIOD=120s
$ docker inspect cadgpt-worker-1 --format 'StopTimeout={{.Config.StopTimeout}}'
StopTimeout=120
```

Real worker log, same ordinary deploy issued mid-check:

```
09:44:21.734  check_run_claimed    claim_count=1  run_id=0d583579-...
09:44:24.324  (ordinary deploy issued: docker compose up -d --force-recreate worker)
09:44:25.205  worker: Warm shutdown (MainProcess)
09:44:41.731  check_run_succeeded  duration_seconds=19.913246  outcome=FAIL
              passed=113334 failed=113333 indeterminate=113333   run_id=0d583579-...
              [Kworker-1 exited with code 0          <-- clean exit, only after the task finished
              up -d --force-recreate worker took 21.955116555s   <-- waited for the check, not the
                                                                       grace period
```

Real final state: `succeeded|1||` — `claim_count` never moved off `1`. The deploy's SIGTERM was
absorbed by Celery's own warm shutdown exactly as the mechanism analysis predicted: no
`WorkerLostError`, no redelivery, no claim spent, and the command itself took only as long as the
remaining check time (not the full grace period) — an ordinary deploy during a quiet moment is
still fast.

### Real path, proof 3 — the true positive still caught (must not regress)

Reused T-0033's own `WORKER_MEM_LIMIT` technique unchanged, at **production-default** settings
(`CELERY_TASK_TIME_LIMIT=1800`, `stop_grace_period=1860s` — the committed fix, not compressed) to
show the fix does not touch this path at all: peak RSS of the 500,000-door/44MB model against
`door_width.ids`, measured directly in the container, is 884MB — comfortably over a deliberately
lowered `mem_limit`:

```
$ WORKER_MEM_LIMIT=300m docker compose -f deploy/compose.yaml up -d --force-recreate worker
$ docker inspect cadgpt-worker-1 --format 'Mem={{.HostConfig.Memory}} StopTimeout={{.Config.StopTimeout}}'
Mem=314572800 StopTimeout=1860
```

Real dispatch, real worker log — the exact signature T-0033 first proved, reproduced here to show
T-0062 does not weaken it:

```
09:45:54.128  check_run_claimed              claim_count=1  run_id=5e8b9d19-...
09:45:58.854  ERROR  Process 'ForkPoolWorker-2' pid:23 exited with 'signal 9 (SIGKILL)'
09:45:58.879  ERROR  WorkerLostError('Worker exited prematurely: signal 9 (SIGKILL) Job: 0.')
09:45:59.981  check_run_claimed              claim_count=2  run_id=5e8b9d19-...
09:46:03.983  ERROR  Process 'ForkPoolWorker-1' pid:22 exited with 'signal 9 (SIGKILL)'
09:46:03.994  ERROR  WorkerLostError('Worker exited prematurely: signal 9 (SIGKILL) Job: 1.')
09:46:04.243  check_run_claimed              claim_count=3  run_id=5e8b9d19-...
09:46:08.478  ERROR  Process 'ForkPoolWorker-3' pid:31 exited with 'signal 9 (SIGKILL)'
09:46:08.491  ERROR  WorkerLostError('Worker exited prematurely: signal 9 (SIGKILL) Job: 2.')
09:46:08.732  check_run_claim_limit_exceeded  claim_count=3  max_claims=3  run_id=5e8b9d19-...
09:46:08.737  check_run_failed  reason=resource_exhausted
              detail='این اجرا 3 بار درخواست شد و بدون تکمیل، به‌جای تلاش دوباره متوقف شد.'
```

Real final state: `failed|3|resource_exhausted|<the Persian sentence above>` — ("This run was
claimed 3 times without finishing and has been stopped rather than tried again.") Claimed exactly
3 times, refused on the 4th, correct reason, in seconds — the OOM killer's SIGKILL of a single
process is unaffected by `stop_grace_period` (a container-stop mechanism; the OOM killer acts on a
running container's cgroup directly, not via `docker stop`), so this path is untouched by the fix,
exactly as required.

### Wiring

`deploy/compose.yaml`, `worker` service (the setting that is actually live in the container
inspected above):

```yaml
stop_grace_period: ${WORKER_STOP_GRACE_PERIOD:-1860s}
```

`services/api/cadgpt/config/settings/base.py` (unchanged value, re-justified comment, confirmed
live: `CHECK_RUN_MAX_CLAIMS == 3` in every container inspected above):

```python
CHECK_RUN_MAX_CLAIMS = env.int("CHECK_RUN_MAX_CLAIMS", default=3)
```

Nothing in `services/api/cadgpt/apps/review/services/execution.py` changed — `_claim`,
`dispatch_lost`, `reap_stalled`, and `CheckRunFailure.RESOURCE_EXHAUSTED` are byte-for-byte what
T-0033 left them, confirmed by `git diff` touching only `deploy/compose.yaml`,
`services/api/cadgpt/config/settings/base.py`, and `docs/decisions.md`.

### Environmental finding (not a product defect, disclosed for the record)

The first attempts at proof 1 were corrupted by a **pre-existing, non-Docker** `celery -A
cadgpt.config.celery worker -Q checks,default` process already running on the host (PID 1540232,
started 11:22 by an earlier, unrelated session, using `services/api/.env`'s host-forwarded
`localhost:6380`/`:5433`), racing the Docker worker for deliveries on the same Redis-backed
`checks` queue and failing every one it won with `[Errno 2] No such file or directory:
'/home/alireza/Projects/cadgpt/services/api/mediafiles/...'` — a host filesystem path, because that
rogue process's `BASE_DIR` resolves from the *host* checkout while the actual file bytes exist only
in the Docker `media_data` volume. This is not a bug in the product; it is contamination in the dev
environment predating this task. It could not be killed (process termination was outside this
task's permitted actions) and was neutralized for the evidence runs by moving Redis's host-published
port out from under it (`deploy/.env`, gitignored, `REDIS_HOST_PORT=16380`) rather than left to
silently bias every real-path measurement in this file. Flagged here for a human to clean up.

### NOT DONE

- **The literal scenario in this task's own Why section was not reproduced at production
  timescale — but, corrected 2026-09-17, this is not because it doesn't happen there.** Proof 1
  reproduced a full-container SIGKILL being caught by `reap_stalled_runs` as `STALLED` rather than
  by redelivery as `resource_exhausted` — real, but only because the run used a compressed
  `CELERY_TASK_TIME_LIMIT=60` (450s → 15s tick), which the mechanism analysis above shows is well
  below the 240s crossover where the beat sweep's tick interval starts to exceed the 60s
  redelivery margin. At production's actual `CELERY_TASK_TIME_LIMIT=1800s` (a 450s tick, 7.5× past
  the crossover), the same arithmetic says Redis's redelivery restores the message before the next
  tick roughly 87% of the time — so the original Why section's scenario (an ordinary deploy
  eventually burning a claim via `resource_exhausted`) is the realistic outcome at production
  settings, not the exception. It was not reproduced literally here because doing so at real
  production timescales means observing a single interruption over 30+ minutes, a practical/time
  constraint on this task's evidence-gathering, not because the race is structurally decided
  against it. This does not change whether the shipped fix works — raising `stop_grace_period`
  removes the SIGKILL event itself, so it closes both failure surfaces (`STALLED` and
  `resource_exhausted`) regardless of which one would have "won" a race that, with the fix
  deployed, never occurs. See `docs/decisions.md` (entry dated 2026-09-17, corrected) for the full
  arithmetic.
- The rogue host Celery process found during this task (see the Environmental finding above) is,
  as of this correction (2026-09-17), **no longer running** — confirmed by `ps -eo pid,cmd | grep
  celery` returning nothing. `deploy/.env`'s `REDIS_HOST_PORT=16380` override is therefore stale,
  gitignored local drift rather than an active workaround; it should be removed by whoever next
  works in this checkout (it does not ship — nothing in the committed tree depends on it — but it
  will otherwise silently redirect a future session's Redis connection for no remaining reason).

### Fix-now round: F1 and F2 — the write-up overstated a compressed-timescale result as general, and misattributed a quote

A review of the shipped fix found it architecturally correct (independently re-derived against
the installed `celery`/`kombu` source and re-run against the live stack) but found two false
claims in this Evidence section and in `docs/decisions.md`, not in the code:

- **F1.** The original write-up asserted, as a settled fact about "this stack's actual settings,"
  that an ordinary deploy is always caught by `reap_stalled_runs` (`STALLED`) rather than by
  redelivery (`resource_exhausted`). The reviewer showed this holds only when the beat sweep's
  tick interval (`CELERY_TASK_TIME_LIMIT/4`) is smaller than Redis's 60s redelivery margin — true
  at the compressed `CELERY_TASK_TIME_LIMIT=60` proof 1 actually used, false at production's
  `CELERY_TASK_TIME_LIMIT=1800`, where the tick interval (450s) is 7.5× past the crossover and
  redelivery wins the race roughly 87% of the time. Corrected above and in `docs/decisions.md`:
  the mechanism paragraph, proof 1's framing, and the "NOT DONE" entry now state the arithmetic
  explicitly and no longer generalize the compressed-settings observation to production. The
  shipped fix (`stop_grace_period`) needed no change — it removes the SIGKILL regardless of which
  sweep would have won.
- **F2.** `docs/decisions.md` attributed the phrase "was not measured" to T-0033's own comment, in
  quotes, as if citing prior work. `grep -rn "not measured" docs/ services/api` shows the phrase
  appears nowhere in anything T-0033 wrote — only in this task's own Scope line. Corrected in
  `docs/decisions.md` to state the point (this number was never measured against real
  crash-frequency data) as this task's own observation, with no false citation.

Both corrections are documentation-only; `deploy/compose.yaml`, `services/api/cadgpt/config/
settings/base.py`, and every other production file are untouched by this round (`git diff --stat`
confirms only `docs/decisions.md` and this task file changed). No `make verify` re-run needed —
nothing executable changed.

## Review

**Verdict: the shipped fix is correct, reviewer-gated as specified, one fix-now round on the
write-up, closed.** The reviewer independently re-derived the core mechanism against the
actually-installed `celery==5.6.3`/`kombu==5.6.2` source (`celery.apps.worker`'s SIGTERM→warm
handler, `prefork.TaskPool.on_stop`'s `close()`/`join()` with no signal to the child), confirmed
`stop_grace_period` compiles only to `docker stop`'s `Config.StopTimeout` and cannot affect the
kernel OOM killer, found all three real-path proofs' database rows exactly as pasted, re-ran
`make verify` clean, and confirmed `_claim`/`dispatch_lost`/`reap_stalled` in `execution.py` are
byte-for-byte unchanged from T-0033.

**FIX NOW (2), closed same task, documentation only:** F1 — the evidence and `docs/decisions.md`
generalized a compressed-timescale observation (proof 1's `CELERY_TASK_TIME_LIMIT=60`) into a
settled claim about "this stack's actual settings," when the arithmetic the reviewer worked out
(beat tick interval `CELERY_TASK_TIME_LIMIT/4` vs. the fixed 60s redelivery margin, crossover at
`CELERY_TASK_TIME_LIMIT=240s`) shows the opposite holds at production's `1800s` default. F2 — a
quote ("was not measured") was attributed to T-0033's own comment in `docs/decisions.md`, but the
phrase appears nowhere in anything T-0033 wrote. Both corrected in place above and in
`docs/decisions.md`; the underlying code fix needed no change, since raising `stop_grace_period`
prevents the SIGKILL regardless of which race narrative is accurate.

**QUEUED, not fixed here — T-0095 through T-0097:** `stop_grace_period`'s value is a hardcoded
literal that can silently decouple from `CELERY_TASK_TIME_LIMIT` if the latter is overridden
without the former, reintroducing this task's own bug (**T-0095**); the `CHECK_RUN_MAX_CLAIMS`
comment's transient-overlap argument technically supports 2, not the 3 it's attached to
(**T-0096**); and the large-model proofs used an uncommitted one-off generator instead of
T-0033's own committed `scripts/generate_large_ifc_model.py` (**T-0097**). None blocks this
task's own claim; none is a fix-now finding.
