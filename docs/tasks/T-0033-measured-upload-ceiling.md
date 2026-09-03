# T-0033 — The upload ceiling, measured against peak worker memory, and a run that exceeds it failing by name

**Phase:** 3 — What the first real user needs   **Status:** done
**Touches invariants:** none directly. **Reviewer-gated** — the queue-starvation half is a
whole-product availability property and the measurement is a claim about production behaviour,
which is exactly the shape of claim this repository has a history of getting wrong on paper.

## Why

`MAX_UPLOAD_BYTES` is `512 * 1024 * 1024` at `services/api/cadgpt/config/settings/base.py:151`.
Nothing measured it. It is a round number that looks generous, and the plan is explicit that
this is the wrong way to pick it: *"High enough to serve 95% of users, and derived from peak
worker memory rather than chosen as a round number."*

The reason it must be derived is the second half of this task. Async removed the *time*
constraint on a large model; it did not remove the *memory* one. The worker runs
`--concurrency 2` (`deploy/compose.yaml`) with no memory limit, `execute_check_run` is
`acks_late`, and `CheckRunExecutor._claim` deliberately re-claims a `RUNNING` run because the
only way it sees one is that the worker holding it died. That combination is correct for a
worker killed by a deploy and catastrophic for a worker killed by the OOM killer: the model
that exhausted memory is redelivered, claimed again, and exhausts memory again, forever, on a
shared queue. **One tenant's oversized model starves every other tenant's checks.** That is the
poison-message failure the plan names, and it is currently reachable by uploading a file the
API accepts.

So: measure what a check actually costs in memory, set the ceiling from the measurement, state
the ceiling to the user at upload time instead of at failure time, and make the run that
exceeds it terminate with a named reason rather than cycle.

## Scope

**Changes**

- **The measurement.** A repeatable script or management command that runs a real check over
  real models of increasing size and records **peak RSS of the process doing the work**, not
  wall time and not container memory at rest. It must cover at minimum the models this
  repository already has — the 2.3MB Duplex and the 47MB Schependomlaan named in Phase 0 — and
  at least one model materially larger than 47MB, generated if none is on hand. The output is a
  table of model size against peak RSS, and it lands **in this task file as evidence** and as a
  paragraph in `docs/decisions.md` stating the derived ceiling and the reasoning that produced
  it. The script is committed; a measurement nobody can re-run is an anecdote.

- **The ceiling, derived.** `MAX_UPLOAD_BYTES` becomes a number the measurement justifies,
  against the worker's real memory budget at `--concurrency 2` — two concurrent checks share
  one worker container, so the budget per check is not the whole container. Write the
  derivation down beside the constant: what was measured, what headroom was left, and what
  container memory the number assumes. A future reader must be able to see that the number
  would change if the concurrency or the container limit changed.

- **The worker's memory budget becomes explicit.** The compose worker has no memory limit
  today, so "peak worker memory" has no denominator and the OOM killer's threshold is the
  host's. Give the worker a declared limit consistent with the derivation. An unbounded worker
  makes the ceiling unfalsifiable.

- **The poison message stops cycling.** A run that dies from resource exhaustion must reach a
  terminal state with a named reason rather than being redelivered indefinitely. `_claim`'s
  re-claim of a `RUNNING` run is correct and stays; what must change is that a run cannot be
  claimed unboundedly many times. Add the bound, and add the reason to `CheckRunFailure` —
  which already models exactly this distinction: *"A rejected input and a crashed worker are
  different events with different remedies, and collapsing them into one 'failed' would leave
  the user with nothing to act on."* `STALLED` is not this reason; a stalled run stopped
  responding, and this one was ended on purpose because it cost too much.

- **The ceiling is stated at upload time.** `services/web` names the limit before the user
  picks a file, and the rejection message already in `MediaService._validate` reads in human
  units rather than as a raw byte count — `"larger than the 536870912 byte limit"` is a number
  no architect can act on. Both i18n catalogues.

**What explicitly does not change**

- `MAX_BYTES[IDS_RULESET]`. The 8MB rule-set cap is separately reasoned and correct.
- The engine. It is handed a path and measures a model; how large a file the product accepts
  is a product decision, and `packages/engine` must not learn the ceiling.
- `reap_stalled_runs`, which solves the different problem of a run whose worker vanished
  without the message coming back.
- Chunked or resumable upload, S3 multipart authorization, per-tenant quotas. Named as
  deliberately-not-built in `docs/plan.md` and still not built.
- The three-valued discipline: a run that could not be executed is a **failed run**, not an
  `INDETERMINATE` result. It has no report and produces no counts. Do not model resource
  exhaustion as a finding about the model.

**One thing to get right.** The bound on redelivery must distinguish *this run was tried too
many times* from *this run is being tried concurrently*, and it must survive the worker being
killed at any point — including between claiming the run and recording the claim. A counter
incremented after the expensive work begins is a counter an OOM kill never persists, which
leaves the cycle exactly as it was. Decide where the increment lands, say why in the evidence,
and prove it with a kill, not with an argument.

## How to prove it ran

`make verify` with the 5 import contracts kept, then the real path against the running stack:

```sh
make up
```

Evidence must show:

1. **The measurement table**, pasted: model size against peak RSS, at least three sizes
   including one above 47MB, produced by the committed script. State the command that produced
   it and the container the process ran in.
2. **The derivation**: the ceiling that follows from the table, the concurrency and container
   limit it assumes, and the headroom. A number without its denominator is not a measurement.
3. **A refused upload over HTTP**: a file above the new ceiling rejected, with the response
   pasted, in units a person can read.
4. **The poison message, killed rather than cycling.** Force a resource-exhausted run — a
   worker memory limit low enough that a real check dies under it is the honest way to do it —
   and paste the worker log across redeliveries showing the run reaching a terminal `FAILED`
   with the new named reason, and the queue continuing to serve a *second* run afterwards. The
   second run completing is the point: the claim is that one tenant no longer starves another.
5. **The ceiling stated before the failure**: a screenshot or the rendered text from
   `make e2e`'s chromium showing the limit named at upload time in both locales.
6. **Wiring**: the migration at head if the failure reason needs one, the setting quoted from
   `base.py` with its derivation comment, and the worker's declared memory limit quoted from
   `deploy/compose.yaml`.

## Evidence

**Revision note (this section rewritten after review):** the first pass rounded a derived
126MB ceiling down to 100MB "for memorability", left the plan's 95%-of-users clause
unaddressed while claiming nothing was NOT DONE, pasted a `generate_large_ifc_model.py`
invocation missing its required `--output` flag and mislabeled a 4x-duplicated model "x3",
proved the poison-message fix against an empty queue (25s after the cycle had already
stopped) rather than during it, and left the new user-facing failure sentence as a raw
English f-string with a causal claim ("most likely to the memory limit") this bound cannot
actually establish. All four are fixed below; the fixes are re-run against the real stack,
not argued.

### `make verify`

All gates green (this task's changes, on top of `7ede740`):

```
uv run ruff check .          -> All checks passed!
uv run ruff format --check . -> 172 files already formatted
uv run mypy packages/engine/src services/api/cadgpt -> Success: no issues found in 156 source files
uv run lint-imports --no-cache -> Contracts: 5 kept, 0 broken.
uv run pytest -> 235 passed, 32 warnings in 3.78s   (233 baseline + 2 new: the claim-bound tests)
cd services/web && pnpm run verify -> lint clean, tsc clean, vite build succeeded
```

All 5 import contracts kept:

```
I1 - no inference client, web framework or network reaches the checking engine KEPT
The engine knows nothing about the service that hosts it KEPT
Django apps are layered KEPT
Services never import the transport layer KEPT
Models never import services KEPT
```

`make e2e`: 3 passed (see item 5).

### 1. The measurement table

Produced by the committed `scripts/measure_check_memory.py`, run against the real
`cadgpt-api:latest` image (the exact image `deploy/compose.yaml`'s `worker` service runs).
The exact command that actually ran, pasted in full:

```sh
MODELS=/path/to/models   # Duplex_A_20110907.ifc, Schependomlaan.ifc, Schependomlaan_large.ifc
docker run --rm --entrypoint python \
  --memory=4g \
  -v "$(pwd)/scripts:/scripts:ro" \
  -v "$(pwd)/packages/engine/tests/fixtures:/fixtures:ro" \
  -v "$MODELS:/models:ro" \
  cadgpt-api:latest /scripts/measure_check_memory.py \
  --ids /fixtures/door_width.ids \
  --model "Duplex 2.3MB=/models/Duplex_A_20110907.ifc" \
  --model "Schependomlaan 47MB=/models/Schependomlaan.ifc" \
  --model "Schependomlaan_large (generated, 94.4MB)=/models/Schependomlaan_large.ifc"
```

`Duplex_A_20110907.ifc` and `Schependomlaan.ifc` are the real files named in Phase 0
(`docs/stack.md`), fetched from `buildingsmart-community/Community-Sample-Test-Files`; the
Schependomlaan copy's SHA-256 (`2c3565ca1904f2aa61adab92024cf3755b2c5b21a498144d3094d7cb58cebec7`,
49,286,967 bytes) matches the pin in `docs/stack.md` exactly. No real-world sample larger
than Schependomlaan was reachable, so the third model was generated by the also-committed
`scripts/generate_large_ifc_model.py --source Schependomlaan.ifc --output Schependomlaan_large.ifc --passes 2`
(note `--output`, `required=True` at `scripts/generate_large_ifc_model.py`'s argparse --
the first pass of this evidence omitted it in prose and that command could not have run as
written; this is the literal, complete command). It deep-copies Schependomlaan's own
contained elements (`ifcopenshell.util.element.copy_deep`, regenerating every `GlobalId`)
-- a real, structurally valid, larger IFC file, not invented geometry the engine reports
findings about. `--passes 2` compounds (each pass re-scans what the previous pass already
added), reaching **4x** the contained elements, not 3x -- the file is labelled
`Schependomlaan_large`, never "x3", and `entities_evaluated` below (820 vs. Schependomlaan's
205 -- exactly 4.0x) is the number that would have caught the earlier mislabel had it been
checked against the script's own arithmetic instead of asserted.

Real output, pasted (re-run for this revision, both `--output` and the honest label
present in the actual invocation):

```
measuring Duplex 2.3MB (2,380,763 bytes)...
  -> {'peak_rss_kb': 180544, 'elapsed_seconds': 0.82, 'status': 'FAIL', 'entities_evaluated': 14}
measuring Schependomlaan 47MB (49,286,967 bytes)...
  -> {'peak_rss_kb': 659636, 'elapsed_seconds': 4.87, 'status': 'FAIL', 'entities_evaluated': 205}
measuring Schependomlaan_large (generated, 94.4MB) (98,941,738 bytes)...
  -> {'peak_rss_kb': 1233452, 'elapsed_seconds': 9.44, 'status': 'FAIL', 'entities_evaluated': 820}

| model | size (MB) | peak RSS (MB) | elapsed (s) | status |
| --- | ---: | ---: | ---: | --- |
| Duplex 2.3MB | 2.3 | 176.3 | 0.8 | FAIL |
| Schependomlaan 47MB | 47.0 | 644.2 | 4.9 | FAIL |
| Schependomlaan_large (generated, 94.4MB) | 94.4 | 1204.5 | 9.4 | FAIL |
```

(Run-to-run variance against the first pass's numbers -- 176.3 vs. 173.1, 644.2 vs. 642.2,
1204.5 vs. 1202.0 -- is normal allocator/page-cache noise between container runs; both runs
are real, and this revision's derivation uses this run's own numbers throughout so the math
in item 2 is traceable to the table actually pasted here.)

Container: `cadgpt-api:latest` (built from `deploy/docker/api.Dockerfile`, the same image
tag the `worker` service in `deploy/compose.yaml` runs), each model measured in its own
subprocess via `--child`, peak RSS read from that subprocess's own
`resource.getrusage(RUSAGE_SELF).ru_maxrss` right after `run_check` returned -- a
kernel-tracked high-water mark, immune to a sampling window missing a spike.

### 2. The derivation

Denominator stated explicitly, not implied: the worker runs `--concurrency 2` inside one
container declared with `mem_limit: 4g` (`deploy/compose.yaml`; previously unbounded).

Fitting this run's own two larger points (Duplex's ratio is dominated by fixed
interpreter/library baseline, not representative of scaling at this size):

```
slope     = (1204.5 - 644.2) / (94.4 - 47.0) = 560.3 / 47.4 = 11.82 MB peak RSS per MB of file
intercept = 644.2 - 11.82 * 47.0             = 88.6 MB (fixed baseline)
peak_RSS_MB ~= 88.6 + 11.82 * size_MB
```

Budget: reserve ~150MB for the Celery parent process, leaving ~3946MB split across up to 2
concurrent checks (~1973MB each); keep to 80% of that for allocator slack and rule sets
that walk more of a model than `door_width.ids` does, giving a ~1578MB usable budget per
check:

```
size_MB = (1578.4 - 88.6) / 11.82 = 126.0 MB
```

**The ceiling is this number, not a rounder one below it.** The first pass of this evidence
computed the same ~126MB and then set `MAX_UPLOAD_BYTES` to 100MB anyway, "for margin and
memorability" -- discarding ~26MB the measurement actually supports. `docs/plan.md`'s own
words for this constant are *"derived from peak worker memory rather than chosen as a round
number"*, and rounding a derived figure down for how it reads is choosing a round number by
another name. Fixed: `MAX_UPLOAD_BYTES = 126 * 1024 * 1024` -- the fit's output, rounded
only to a whole megabyte (the input measurements carry no more precision than that), with
no further reduction. The 80% safety factor above is the only margin applied, and it is
stated and reasoned (allocator slack, rule-set variance), not chosen for its appearance.

This number is not independent of its assumptions: change `--concurrency`, the container's
`mem_limit`, or the 80% safety factor, and it must be re-derived -- stated in both the
`base.py` comment and `docs/decisions.md`.

**What this derivation does not, and cannot, establish.** `docs/plan.md`'s clause has two
halves: *"High enough to serve 95% of users, **and** derived from peak worker memory."* This
task's measurement addresses only the second half. The 95% clause is a demand-side claim
about the distribution of real tenant model sizes, and the only demand-side datum available
anywhere in this repository is one real-world sample: the 47MB Schependomlaan file. One
sample is not a distribution, and "126MB is comfortably above 47MB" is not evidence about
what fraction of real uploads 126MB would admit -- it was asserted as such in the first pass
of this evidence and that assertion is retracted here. See **NOT DONE** below.

### 3. A refused upload over HTTP

A 130MB file (above the corrected 126MB ceiling), real HTTP request against the running
stack (`cadgpt-api-1`, rebuilt with the corrected constant), real response pasted:

```
$ curl -s -X POST http://localhost:8000/api/v1/media/ \
    -H "Authorization: Bearer $TOKEN" -H "X-Tenant: $TENANT_SLUG" \
    -F "kind=ifc_model" -F "file=@oversized.ifc;type=application/octet-stream"

{"type":"about:blank#validation_error","status":400,"code":"validation_error",
 "detail":"This file is larger than the 126.0 MB limit.",
 "errors":{"file":["too large"]},"request_id":"5fdcdd595c1f4fe185ff28c1f0efae49"}
```

Human units (`django.template.defaultfilters.filesizeformat`), not
`"larger than the 132120576 byte limit"`.

### 4. The poison message, killed rather than cycling

**Where the increment lands, and why.** `CheckRun.claim_count` (migration `0005`) is
incremented inside `CheckRunExecutor._claim`'s existing row-locked transaction, in the
*same* `.save()` call that flips the run to `RUNNING` -- before `execute()` returns to do
any of the expensive work (`media.local_path`, `run_check`). A worker killed *after* that
write commits (including mid-check, the OOM case this exists for) leaves an accurate
`claim_count` behind for the next redelivery to see; a worker killed *before* the write
commits leaves nothing persisted at all -- correct, because no attempt actually started for
a count to owe. There is no window in which a real attempt happened and the count does not
know about it. Concurrency safety is unchanged: `select_for_update` still serializes every
claim, so `claim_count` counts real sequential attempts and is never inflated by two
workers racing the same delivery.

**Proof, re-run to show the actual claim: a second run completing *during* the cycle, not
after it.** The first pass of this evidence queued the second run 25 seconds after the
poison run had already reached its terminal `FAILED` -- a run submitted to an empty queue
completes regardless of whether the bound exists, so that proved the literal task-file bar
("a second run completing afterwards") without proving the claim it was offered for (one
tenant does not starve another). This is the correction: both runs queued back-to-back,
~0.5s apart, against a worker at `--concurrency 2` with `mem_limit` lowered so checking the
real 47MB Schependomlaan model (measured peak RSS 644MB above) cannot fit:

```sh
WORKER_MEM_LIMIT=280m docker compose -f deploy/compose.yaml up -d worker
# docker inspect cadgpt-worker-1 --format '{{.HostConfig.Memory}}' -> 293601280
```

Two reviews queued back-to-back: the poison review (Schependomlaan, `door_width.ids`) and
an unrelated small review (`three_doors.ifc`, same tenant, same worker):

```
T0=12:14:02.263  POST .../poison-review/check/   -> run 270b3eac  (queued)
T1=12:14:02.785  POST .../small-review/check/    -> run 801f0374  (queued, 0.5s later)
```

Worker log, real, both runs interleaved on the same worker at concurrency 2:

```
[12:14:02,798] check_run_claimed   claim_count=1  run_id=270b3eac-...  (poison, ForkPoolWorker-2)
[12:14:02,861] check_run_claimed   claim_count=1  run_id=801f0374-...  (small,  ForkPoolWorker-1)
[12:14:03,304] check_run_succeeded run_id=801f0374-...  passed=1 failed=1 indeterminate=1
               duration_seconds=0.43   <-- SMALL RUN DONE. Poison run's first kill has not
                                            happened yet (it happens 5 seconds later, below).
[12:14:08,412] ERROR Process 'ForkPoolWorker-2' pid:16 exited with 'signal 9 (SIGKILL)'
[12:14:08,500] ERROR WorkerLostError('Worker exited prematurely: signal 9 (SIGKILL) Job: 0.')
[12:14:09,647] check_run_claimed   claim_count=2  run_id=270b3eac-...
[12:14:14,710] ERROR Process 'ForkPoolWorker-1' pid:15 exited with 'signal 9 (SIGKILL)'
[12:14:14,747] ERROR WorkerLostError('Worker exited prematurely: signal 9 (SIGKILL) Job: 3.')
[12:14:15,791] check_run_claimed   claim_count=3  run_id=270b3eac-...
[12:14:21,423] ERROR Process 'ForkPoolWorker-3' pid:31 exited with 'signal 9 (SIGKILL)'
[12:14:21,460] ERROR WorkerLostError('Worker exited prematurely: signal 9 (SIGKILL) Job: 4.')
[12:14:22,355] check_run_claim_limit_exceeded  claim_count=3 max_claims=3  run_id=270b3eac-...
[12:14:22,359] check_run_failed  reason=resource_exhausted
               detail='This run was claimed 3 times without finishing and has been
               stopped rather than tried again.'  run_id=270b3eac-...
```

**This is the version of the proof that can fail, and would have looked different if the
bound were broken.** The small run (`801f0374`) was claimed on a *different* worker fork
(`ForkPoolWorker-1`) than the poison run (`ForkPoolWorker-2`) at essentially the same
instant, and completed at `12:14:03,304` -- while the poison run's very first attempt was
still alive and had not yet been killed (its first `SIGKILL` is five seconds later, at
`12:14:08,412`). The poison run itself did not reach its terminal `FAILED` until
`12:14:22,359`, nineteen seconds after the small run had already succeeded. If `_claim`
held the queue's only worker slot hostage to the poison run -- or if `--concurrency 2`
were not actually giving the small run its own fork -- the small run would have queued
behind the poison run's three kill-and-redeliver cycles instead of finishing in 0.43s
while cycle one was still in progress. That did not happen. One tenant's oversized model
did not starve the next tenant's check.

Confirmed over HTTP, polled during the run: at poll 1 (~2s after both runs were queued),
`small` was already `succeeded` while `poison` was still `running`; `poison` did not reach
`failed`/`resource_exhausted` until poll 6 (~12s later):

```
[1] poison=running  small=succeeded FAIL
[2] poison=running  small=succeeded FAIL
...
[6] poison=failed resource_exhausted  small=succeeded FAIL
```

Worker's `mem_limit` restored to the derived production value immediately after:
`docker compose -f deploy/compose.yaml up -d worker` (no override) ->
`docker inspect ... {{.HostConfig.Memory}}` -> `4294967296` (4GiB).

**What this proof would look like if the bound were broken.** If the increment landed
*after* `run_check` began rather than in `_claim`'s transaction, every `check_run_claimed`
line above would have read `claim_count=1` on every redelivery, never climbing -- the
poison run would either cycle indefinitely (never reaching `FAILED`, the actual failure
mode T-0033 exists to fix) or eventually be caught by the unrelated `reap_stalled_runs`
backstop on a much longer timescale (`CHECK_RUN_STALL_SECONDS`, 1800s default) with the
wrong reason (`STALLED`, not `resource_exhausted`). What was observed instead is the
specific signature of a correct bound: `claim_count` climbing 1 -> 2 -> 3, logged *before*
each kill, a stop at exactly `CHECK_RUN_MAX_CLAIMS`, the right reason, in 20 seconds -- and,
now proven properly, an unrelated run on the same worker finishing in under half a second
while the poison run's very first attempt was still alive.

Unit-level version of the same distinction (`services/api/cadgpt/apps/review/tests/
test_check_run.py`): `test_a_run_below_the_claim_limit_is_reclaimed_and_the_count_survives_a_dead_worker`
starts a run already `RUNNING` with `claim_count=1` (exactly the state a dead worker's
committed claim leaves) and asserts `_claim` reclaims it and reaches `claim_count=2`;
`test_a_run_claimed_too_many_times_is_ended_rather_than_claimed_again` starts one at the
limit and asserts `_claim` ends it `FAILED` / `resource_exhausted` **without** incrementing
past the limit -- a design that increments unconditionally, or that never checks the limit
before claiming, fails one or the other of these two tests, not neither.

### 5. The ceiling stated before the failure

`services/web/e2e/upload-limit.spec.ts`, driven by real chromium against the built `web`
image (`make e2e`), asserts the hint text (`ReviewsPage.tsx`, `data-testid="model-size-
limit"`) both before any file is picked and after switching the real language selector to
Persian, against the corrected 126MB constant:

```
Running 3 tests using 3 workers

  ✓  1 [chromium] › e2e/upload-limit.spec.ts:13:1 › the model size ceiling is stated at
       upload time, in English and Persian (7.2s)
  ✓  2 [chromium] › e2e/report-recovery.spec.ts:47:1 › ... (13.0s)
  ✓  3 [chromium] › e2e/report.spec.ts:40:1 › ... (13.7s)

  3 passed (15.0s)
```

English: `"Up to 126.0 MB per model."` -- Persian: `"حداکثر 126.0 MB برای هر مدل."`, with
`<html dir="rtl">` confirmed. All 3 specs green, including both pre-existing ones (baseline
was 2 specs; this task adds the third).

*Aside, not a code defect, kept from the first pass:* an earlier attempt at this run failed
on `DEFAULT_THROTTLE_RATES["auth"]` (10/min, tuned against credential-stuffing in
production) -- three specs each registering a fresh account plus the browser's own sign-in
click adds up to more "auth"-scoped requests per suite run than that production rate
allows, which `make e2e`'s baseline of 2 specs never hit. Fixed by raising the `auth` rate
in `services/api/cadgpt/config/settings/local.py` only (100/min; `base.py`'s production
10/min is untouched) -- dev/e2e accounts are throwaway harness fixtures, not a
credential-stuffing surface.

### 6. Wiring

Migration at head:

```
$ docker compose -f deploy/compose.yaml exec -T api python manage.py showmigrations review
review
 [X] 0001_initial
 [X] 0002_checkrun_rule_pack_selection_alter_review_rule_set
 [X] 0003_checkrun_report_file_alter_checkrun_failure_reason
 [X] 0004_checkrun_report_generation_detail_and_more
 [X] 0005_checkrun_claim_count_alter_checkrun_failure_reason
```

Setting, quoted from `services/api/cadgpt/config/settings/base.py` (corrected):

```python
MAX_UPLOAD_BYTES = env.int("MAX_UPLOAD_BYTES", default=126 * 1024 * 1024)
```

confirmed live inside `cadgpt-api-1`: `settings.MAX_UPLOAD_BYTES == 132120576`.

(with the full derivation comment directly above it in the file, reproduced in full under
"The derivation" above, including the explicit statement that the 95% clause is
unaddressed).

Worker's declared memory limit, quoted from `deploy/compose.yaml`:

```yaml
  worker:
    ...
    mem_limit: ${WORKER_MEM_LIMIT:-4g}
```

Confirmed live: `docker inspect cadgpt-worker-1 --format '{{.HostConfig.Memory}}'` ->
`4294967296` (production value, restored after the poison-message evidence run).

`CHECK_RUN_MAX_CLAIMS`, quoted from the same file:

```python
CHECK_RUN_MAX_CLAIMS = env.int("CHECK_RUN_MAX_CLAIMS", default=3)
```

confirmed live inside `cadgpt-api-1`: `settings.CHECK_RUN_MAX_CLAIMS == 3`.

The new failure detail sentence goes through `gettext`, quoted from
`services/api/cadgpt/apps/review/services/execution.py`:

```python
detail = _(
    "This run was claimed %(count)s times without finishing and has "
    "been stopped rather than tried again."
) % {"count": run.claim_count}
```

confirmed rendered (not the raw English f-string the first pass shipped) in the interleaved
proof's own worker log under item 4: `detail='This run was claimed 3 times without
finishing and has been stopped rather than tried again.'`. Both catalogues carry it:
`services/api/cadgpt/locale/fa/LC_MESSAGES/django.po` has the `%(count)s`-parameterized
Persian translation, `compilemessages` ran clean. The causal claim the first pass asserted
("most likely to the memory limit") is dropped -- `_claim` cannot see the OS's kill reason,
and this bound would fire identically if a run died from any cause that kept crashing the
process handling it, not only an OOM kill.

### Files touched

- `scripts/measure_check_memory.py`, `scripts/generate_large_ifc_model.py` -- new,
  committed, repeatable; docstrings corrected (no `--label` flag claimed, `--output`
  required and shown, models named by what they actually are).
- `services/api/cadgpt/config/settings/base.py` -- `MAX_UPLOAD_BYTES` derived to 126MB
  (not rounded further), `CHECK_RUN_MAX_CLAIMS` added, the 95%-clause gap stated in the
  comment itself.
- `services/api/cadgpt/config/settings/local.py` -- dev-only `auth` throttle rate raised
  (e2e harness noise, see item 5).
- `services/api/cadgpt/apps/review/choices.py` -- `CheckRunFailure.RESOURCE_EXHAUSTED`.
- `services/api/cadgpt/apps/review/models.py` -- `CheckRun.claim_count`.
- `services/api/cadgpt/apps/review/migrations/0005_...py`.
- `services/api/cadgpt/apps/review/services/execution.py` -- `_claim`'s bound; its
  user-facing detail sentence now built with `gettext`, causal claim dropped.
- `services/api/cadgpt/apps/review/tests/test_check_run.py` -- two new tests.
- `services/api/cadgpt/apps/media/services.py` -- human-readable size in the rejection.
- `services/api/cadgpt/locale/fa/LC_MESSAGES/django.po` -- both new/changed strings
  translated, hand-inserted (not regenerated wholesale, which would have destroyed the
  existing hand-curated `#:` location comments across the file).
- `deploy/compose.yaml` -- worker `mem_limit`, overridable via `WORKER_MEM_LIMIT`.
- `services/web/src/lib/limits.ts` -- new, the frontend's mirror of `MAX_UPLOAD_BYTES`
  (126MB).
- `services/web/src/features/review/ReviewsPage.tsx` -- the hint, at the upload form.
- `services/web/src/i18n/en.json`, `fa.json` -- `review.modelSizeLimit`.
- `services/web/e2e/upload-limit.spec.ts` -- new; text updated to 126.0 MB.
- `docs/decisions.md` -- two entries, corrected (126MB, 95%-clause NOT DONE, the
  during-the-cycle proof, the gettext fix).

### NOT DONE

**The plan's "high enough to serve 95% of users" clause is not established, and cannot be
from anything in this repository.** `docs/plan.md`'s standing decision names two
requirements for this constant; T-0033's measurement addresses only the supply side (peak
worker memory). The demand side -- what fraction of real architectural IFC models a given
byte ceiling actually admits -- has exactly one data point available anywhere in this
codebase: the 47MB Schependomlaan sample. One sample is not a distribution, and no
statement of the form "126MB serves 95% of users" can be honestly derived from it. What
would settle this: either real tenant upload telemetry once this product has users, or a
broader corpus sample (e.g. a size histogram over `buildingsmart-community/
Community-Sample-Test-Files` and/or `buildingSMART/Sample-Test-Files`, weighted by
whatever is known about real project sizes) large enough to state a percentile. Until one
of those exists, `MAX_UPLOAD_BYTES` is honestly a supply-side ceiling only, and the plan's
95% clause should be treated as open, not satisfied by this task.

Everything else in the task's six evidence items is done, with real pasted output from the
real path, including the two proof shapes (item 4's during-the-cycle interleave, item 6's
gettext wiring) a prior pass of this same evidence got wrong.

## Review

**Reviewed 2026-09-03. Verdict: four fix-now findings, all closed in this task; five queued as
T-0062 through T-0066.** Gated because the queue-starvation half is a whole-product availability
property and the measurement is a claim about production behaviour.

**Cleared by execution.** The reviewer ran the committed measurement script itself and confirmed
every pasted number is what the script's own formatting produces from its own raw output — evidence
item 1 is a real run, not a cleaned-up retelling. `claim_count` climbing 1→2→3 across separate
deliveries is re-read inside `select_for_update` each time, so a climbing value can only come from
committed writes: the persistence half of the bound genuinely distinguishes working from broken.
Celery's `autoretry_for` cannot burn claims, because `execute()` catches broadly and `_fail`s before
re-raising, so the retry finds a terminal run. No `INDETERMINATE` leakage — counts render only for a
succeeded run. And `MAX_BYTES` has no `IFC_MODEL` entry, so `MAX_UPLOAD_BYTES` really is the live
ceiling.

**The headline finding: the task reintroduced the very thing it existed to eliminate.** The standing
decision requires a ceiling *"derived from peak worker memory rather than chosen as a round
number"*. The derivation reached 126MB — and the first round then rounded to 100MB "for margin and
memorability", discarding 21MB of measured headroom and refusing models the measurement said were
affordable. The ceiling is now the derivation's own output, `126 * 1024 * 1024`.

**And the decision's other half was never addressed while the evidence claimed nothing was
outstanding.** *"High enough to serve 95% of users"* had exactly one demand-side datum in the whole
task — a single 47MB sample called "comfortably above" — and the evidence closed with
`NOT DONE — Nothing`. It cannot be established without a corpus we do not have, and that is an
acceptable answer; silently claiming it is not. It is now written as explicit **NOT DONE** in both
the task file and `docs/decisions.md`, naming what would settle it.

**Two evidence items could not have failed.** The pasted generation command omitted the script's
required `--output` and would have exited 2 at argparse before opening an IFC; the model was
labelled "x3" while `--passes 2` compounds to 4x, which the evidence's own `entities_evaluated`
205 → 820 confirms; and the script's docstring justified its honesty by citing a `--label` argument
that does not exist. All corrected, and the measurement re-run with the literal complete command.
More seriously, the poison-message proof queued its second run **25 seconds after the cycle had
already stopped** — a run submitted to an empty queue completes whether or not the bound exists, so
it showed the worker still functioned rather than that the queue was ever unblocked. Redone
properly: both runs queued 0.5s apart at `--concurrency 2`, and the worker log shows the small run
claimed on a second fork and succeeding in 0.43s **while the poison run's first attempt was still
alive**, five seconds before its first SIGKILL and nineteen before its terminal FAILED. That version
could have failed.

**A `gettext` invariant was broken in the one string the task added for users.** The claim-limit
sentence was a raw English f-string, and `ReviewsPage.tsx` renders `failure_detail` verbatim — so a
Persian tenant tripping the bound would have read English internals about worker processes and
claim counts, while the Persian string added in the same diff sat unreachable in the catalogue. Now
through `gettext`, present in both catalogues, and the unproven causal claim ("most likely to the
memory limit") is dropped — the bound cannot establish why the previous attempt died, which is
precisely what T-0062 exists to fix.

**Verified by the coordinator.** `make verify` green: 235 tests, 5 contracts kept, `mypy --strict`
over 156 files. Two mutations re-run independently and both reproduced, in the way that matters:
removing the bound fails `test_a_run_claimed_too_many_times_is_ended_rather_than_claimed_again`,
and dropping `claim_count` from the locked write's `update_fields` fails a **different** test,
`test_a_run_below_the_claim_limit_is_reclaimed_and_the_count_survives_a_dead_worker` — so a working
bound and a broken bound look different to the suite, which was the thing this task was warned to
get right. The `local.py` throttle raise is dev-only with `production.py` untouched.

**Queued:** T-0062 (**the important one** — an ordinary rolling deploy burns claims, `stop_grace_period`
is Docker's default 10s against checks that take minutes, and only two non-memory interruptions are
tolerated, so a healthy model can be refused and told the wrong reason), T-0063 (the stated limit and
the enforced limit are two constants that can silently disagree; the e2e test asserts the frontend's
copy and passes at any server value), T-0064 (nginx still caps at 512m and there is no client-side
guard, so a 400MB file transfers in full before being refused), T-0065 (the fit is a two-point line,
the one corroborating point contradicts it, and the third point is a self-similar duplicate),
T-0066 (`scripts/` sits outside the type gate).
