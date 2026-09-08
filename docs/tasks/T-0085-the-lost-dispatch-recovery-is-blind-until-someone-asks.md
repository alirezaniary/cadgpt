# T-0085 — A lost-dispatch run is invisible and the review looks falsely blocked for up to 30 minutes

**Phase:** 3   **Status:** open
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
