# T-0084 — `reap_stalled_runs` is registered nowhere and has never run in production

**Phase:** 3   **Status:** open
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
