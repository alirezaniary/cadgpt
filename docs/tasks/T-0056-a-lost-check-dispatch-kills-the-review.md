# T-0056 — The same lost dispatch that stranded a report file permanently kills the review

**Phase:** 3   **Status:** open
**Touches invariants:** idempotent background work; the MVP sentence. **Reviewer-gated.**

## Why

Found by the T-0051 review, which closed the lost-`on_commit` hole for the report file and then
found **the identical hole one step upstream, where the consequence is worse.**

`ReviewService.request_check` (`review.py:91`) dispatches `execute_check_run` on commit exactly as
`_succeed` dispatches the report generation. Lose that callback — the worker dying between `COMMIT`
and the callback, which `acks_late` plus `reject_on_worker_lost` make the *designed* hazard — and
the run sits `PENDING` forever:

- `reap_stalled` filters `status=RUNNING` only (`querysets.py:79-84`), and its docstring explicitly
  declines to touch PENDING;
- `missing_report` requires `SUCCEEDED`, so T-0051's backfill cannot see it;
- T-0051's new recovery POST returns 409 for a non-succeeded run (`views.py:170`).

And because `MAX_IN_FLIGHT_RUNS = 1` (`review.py:27,79-83`), **that one dead row blocks the review
from ever being checked again.** The user cannot retry, cannot recover, and is not told why.

The reviewer executed it against the live compose stack: a PENDING run backdated three days →
`reap_stalled()` reaped `0`, still `pending`; `missing_report` → `False`;
`ReviewService.request_check(...)` → `ConflictError: "A check is already running for this review."`

T-0051's own *Why* named this as the designed hazard of `acks_late` and then closed it only for the
report file. This is the other half, and it is the more damaging one: a lost report file leaves a
check that ran and can be re-rendered; a lost dispatch leaves a review that can never be checked.

## Scope

**Changes**

- A `PENDING` run whose dispatch was lost is recoverable. Decide deliberately **how** — reaping it
  to a failed state so the user can request a new check, or re-dispatching it — and say which and
  why in the evidence. Re-dispatch is only safe if `execute_check_run` is genuinely idempotent for
  a run that may or may not have started; it is documented as such, so state whether you are
  relying on that and what would break if it were untrue.
- Whatever the mechanism, it must not fight `MAX_IN_FLIGHT_RUNS`: the user's way out cannot be
  blocked by the very row that is stuck.
- The age threshold is a judgement, not a constant to invent: a run legitimately sits `PENDING`
  while the queue is busy. Derive it from something real and say what.
- The user can see that a check never started, distinguished from one still queued. Both i18n
  catalogues.

**What explicitly does not change**

- `reap_stalled_runs`' existing `RUNNING` behaviour, which solves the different problem of a worker
  that died mid-check.
- T-0051's report recovery path, which is correct and reviewed.
- `MAX_IN_FLIGHT_RUNS` itself.

## How to prove it ran

`make verify`, then against `make up`, reproducing the reviewer's sequence:

1. The hole as it stands: a `PENDING` run with its dispatch dropped, `reap_stalled()` returning 0,
   and `request_check` refusing with `ConflictError` — the user with no way forward. Paste it.
2. The recovery working on that same run, over real HTTP or the real command.
3. That a legitimately queued run is **not** swept — the false-positive direction, which is the one
   that would silently kill healthy work.
4. The user-visible distinction, rendered.

## Evidence

## Review
