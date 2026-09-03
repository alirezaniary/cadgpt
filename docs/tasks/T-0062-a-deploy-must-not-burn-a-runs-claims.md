# T-0062 — An ordinary deploy burns a run's claims, and there are only three

**Phase:** 3   **Status:** open
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

## Review
