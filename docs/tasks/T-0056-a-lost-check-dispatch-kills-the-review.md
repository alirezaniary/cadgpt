# T-0056 — The same lost dispatch that stranded a report file permanently kills the review

**Phase:** 3   **Status:** done
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

### 0. Mechanism chosen: fail the row, do not re-dispatch — and fail it as one atomic `UPDATE`

`_reap_lost_dispatch` fails a lost-dispatch `PENDING` run rather than re-issuing
`task.delay()` for it. Re-dispatch was considered and rejected: `CheckRunExecutor.execute`'s
idempotency (`execution.py`'s `_claim`) relies on Celery's own guarantee that a message is
never live on two workers at once — a guarantee that covers a *redelivered* message, not a
*second, independently issued* `.delay()` call for the same run. If the original dispatch
actually reached the broker and only the follow-up write of `task_id` was lost (a narrower
race than the one this task exists for, but a real one), `_claim`'s row lock would serialize
two independent attempts rather than reject the second, and both would evaluate the same
model concurrently. Failing the row costs one result; the caller asks again. That is a
correctness call, not a convenience one.

**Round 1 of this task implemented that as a `SELECT` into Python objects followed by a
per-row `.save()`. The reviewer caught that this reopens the exact race the paragraph above
rejects re-dispatch to avoid**: nothing stops a worker's `_claim` from flipping a selected
row `PENDING → RUNNING` in the gap between the read and the write, and the per-row `.save()`
would then overwrite that row back to `FAILED` while a worker is actively evaluating it —
`request_check` would go on to dispatch a second, genuinely concurrent run. Fixed by
collapsing selection and write into one filtered `UPDATE`
(`runs.dispatch_lost(...).update(status=FAILED, ...)`), the same pattern `reap_stalled`
already uses one file over (`execution.py`). Postgres re-evaluates the `WHERE` clause
(`status=PENDING, task_id=""`) against the current row at the moment of the write, so a run
a worker claimed in the interim simply no longer matches and is left alone.

The age threshold is `settings.CHECK_RUN_STALL_SECONDS` — the same constant `stalled()`
already uses for the different-but-adjacent RUNNING case — not an invented number.
`CheckRunQuerySet.dispatch_lost` matches `status=PENDING, task_id="", created_at__lt=cutoff`;
`_dispatch` writes `task_id` synchronously in the same process the moment `task.delay()`
returns, so a `PENDING` row that still has no `task_id` after that window was never
delivered at all, and a row that is merely waiting behind a busy queue already carries a
`task_id` and is excluded regardless of age. `_reap_lost_dispatch` runs only from inside
`request_check`, only at the instant it is about to refuse — never as a periodic sweep — so
the blast radius of a wrong sweep is bounded to the one call that would otherwise have been
a bare `ConflictError`.

**The reviewer also found the age clause itself was unpinned: removing
`created_at__lt=cutoff` from `dispatch_lost` left the entire suite green.** A third test,
`test_a_young_pending_run_with_no_task_id_is_not_swept_either`, closes that: a `PENDING` run
with no `task_id` but well inside the stall window (the normal gap between `COMMIT` and
`_dispatch`'s synchronous `task_id` write in any healthy request) must not be reaped.
Mutation-verified by hand: with `created_at__lt=cutoff` removed, this test fails with
`Failed: DID NOT RAISE ConflictError` for exactly the stated reason; restored, it passes.

### 1. `make verify`

Ran clean end to end against the working tree: `ruff check`/`format --check`,
`mypy --strict` (169 source files, 0 issues), `lint-imports` (5/5 contracts kept), `pytest`
(**238 passed**, including the three new tests below), and `web-verify`
(eslint + `tsc -b` + `vite build` + `build-workbench`), all exit 0.

New backend tests, all in `services/api/cadgpt/apps/review/tests/test_check_run.py`:
- `test_a_run_whose_dispatch_was_lost_can_be_recovered` — asserts `reap_stalled()` misses the
  row, then `request_check` reaps it to `FAILED`/`DISPATCH_LOST` and returns a new `PENDING`
  run.
- `test_a_genuinely_queued_run_is_not_swept_as_lost` — the false-positive guard: a run that
  carries a real `task_id` and is merely old still raises `ConflictError`, unswept.
- `test_a_young_pending_run_with_no_task_id_is_not_swept_either` — added after review: pins
  the age threshold itself, which nothing previously constrained.

### 2. The real path, against `make up` (not the test DB) — re-run after the fix above

The `api`/`worker` image was rebuilt and the containers recreated with the round-2 code
(single-`UPDATE` reap, `created_at` threshold restored) before this run. Ran against the live
compose stack (`postgres`/`redis`/`api`/`worker`/`web`, all healthy), reusing a pre-existing
dev review (`8edf2711-b72d-4f0d-8691-e9e8981bd50e`, tenant `niary-vntyx5`) that already has a
working catalogue selection, via `manage.py shell` calling the real service, and, for the
locale step, the real HTTP endpoint.

**The round-1 evidence pasted here previously had a false claim, caught by review**: it
showed a "new run created" whose uuid the reviewer found had **zero rows in Postgres** and a
`NotFoundError` in the worker log 63ms after dispatch — the round-1 shell script deleted the
recovered run for cleanliness before it had been independently confirmed to exist, and
narrated a guess ("a stale in-memory read") as fact instead of checking. This re-run does not
delete anything before confirming it, and adds an explicit existence check after the run
reaches a terminal state.

**Step 1 — the hole is real: the RUNNING-only sweep is blind to it.**

```
=== STEP 1: reap_stalled() is blind to a lost-dispatch PENDING row ===
reap_stalled(): 0
stuck status after reap_stalled(): pending
```

(This half is unaffected by the fix and would be identical on `main` before this task —
`reap_stalled` is explicitly RUNNING-only by design, per its own docstring. It is included to
show the row genuinely is invisible to the existing sweep, which is the reason
`_reap_lost_dispatch` had to be a second mechanism rather than a wider filter on the first.)

**Step 2 — `request_check` self-heals instead of refusing forever, and the new run is real.**

```
=== STEP 2: request_check() self-heals; new run persists and dispatches for real ===
{"event": "check_run_dispatch_lost_reaped", "count": 1, ...}
{"event": "check_requested", "run_id": "4a3be21c-6b8e-4975-8d84-da5e34e94e10", ...}
reaped stuck run: failed dispatch_lost
0 recovered run 4a3be21c-6b8e-4975-8d84-da5e34e94e10 running task_id set: True
1 recovered run 4a3be21c-6b8e-4975-8d84-da5e34e94e10 running task_id set: True
2 recovered run 4a3be21c-6b8e-4975-8d84-da5e34e94e10 running task_id set: True
3 recovered run 4a3be21c-6b8e-4975-8d84-da5e34e94e10 running task_id set: True
4 recovered run 4a3be21c-6b8e-4975-8d84-da5e34e94e10 succeeded task_id set: True
CONFIRMED: recovered run persists in DB: succeeded
```

`task_id set: True` from the first poll — no more "stale in-memory read" caveat needed, since
the round-2 log line itself (`check_run_dispatch_lost_reaped count=1`) is the new count-based
logging the `UPDATE` fix uses in place of the old per-row `run_id` logging. The new run was
claimed by the live Celery worker and ran a real check to completion (against the real
`Duplex` IFC and the real "Accessible door width" packs), and a fresh `CheckRun.objects.get`
after the loop confirms it still exists — the fix does not touch or slow down the ordinary
path, and this time nothing was deleted before that was confirmed.

**Step 3 — the false-positive direction, both shapes: old-and-dispatched, and young-and-not.**

```
=== STEP 3: false-positive guard, and the new young-run guard ===
ConflictError as expected (genuinely queued, old): A check is already running for this review.
queued run status: pending
ConflictError as expected (young, no task_id yet): A check is already running for this review.
young run status: pending
```

**Step 4 — the user-visible distinction, rendered.**

Real HTTP, real browser (Playwright/Chromium against `http://localhost:8080`, signed in as a
real seeded user), not a mock. `GET /api/v1/reviews/{uuid}/runs/` returns, for the recovered
row:

```json
{
  "status": "failed",
  "failure_reason": "dispatch_lost",
  "failure_detail": "This check was requested but its dispatch never reached a worker, so it was ended. Request the check again."
}
```

and the rendered `ReviewDetailPage` run-history table shows, in the browser's own
`document.body.innerText`:

```
ناموفق

This check was requested but its dispatch never reached a worker, so it was ended. Request the check again.
```

— distinguished from the still-succeeded rows above it (`تمام‌شده  مردود`) and, separately,
from a genuinely in-flight run (still `در حال بررسی`/pending state, never reached by
`_reap_lost_dispatch` per step 3). Full-page screenshot taken during this run.

### 3. A real, pre-existing gap found while proving step 4 — not a T-0056 regression

The failure text above renders in English inside a Persian-hardcoded product (T-0072: "the
product is single-language, hardcoded to Persian, not user-switchable"). Traced this before
accepting it: `LANGUAGE_CODE = "en"` in `config/settings/base.py:124`, `LocaleMiddleware` is
active, and **`services/web` never sends an `Accept-Language` header on any request** (grep
across `services/web/src` and `services/api/cadgpt`: the only hit is a comment). So the
language Django activates for a request — and therefore the language baked into any
`gettext`-wrapped string written to a stored field during that request, such as
`failure_detail` — depends on whatever the visiting browser happens to send, not on the
product's own decision.

Proved this is pre-existing and not something this task introduced two ways:
- Calling the real `POST /reviews/{uuid}/check/` endpoint with an explicit
  `Accept-Language: fa` header stores `failure_detail` correctly in Persian
  (`"این بررسی درخواست شد، اما هرگز به کارگری نرسید..."`) — T-0056's own `gettext` wiring is
  correct; it is exactly as (un)localized as everything else.
- The same unforced browser session also shows long-shipped, unrelated T-0026/T-0029 report
  prose ("This report checked the model...", "The OverallWidth shall be at least 900.") in
  English — text with no connection to this task, proving the gap already existed.

There is a second, deeper layer for anyone picking this up: most failure/report text (unlike
`_reap_lost_dispatch`, which runs synchronously inside the request) is written by the Celery
worker, which never has an HTTP request or an `Accept-Language` header at all — so fixing the
frontend header alone would not fix that half. Queued as **T-0083**, out of this task's scope
(it is a product-wide localization-activation gap, not a lost-dispatch defect).

### Wiring

Route: `services/api/cadgpt/apps/review/api/v1/views.py:76` —
`@action(detail=True, methods=["post"], throttle_classes=[])` / `def check(...)`, unchanged
by this task, now backed by the self-healing `request_check`.

Call site: `services/api/cadgpt/apps/review/services/review.py` —
`if review_runs.in_flight().count() >= self.MAX_IN_FLIGHT_RUNS: self._reap_lost_dispatch(review_runs)`.

Constant reused, not invented: `services/api/cadgpt/config/settings/base.py:270` —
`CHECK_RUN_STALL_SECONDS = env.int("CHECK_RUN_STALL_SECONDS", default=CELERY_TASK_TIME_LIMIT)`.

Frontend: `services/web/src/features/review/ReviewDetailPage.tsx` — the run-history row now
renders `candidate.failure_detail` under the status label whenever
`candidate.status === "failed" && candidate.failure_detail`.

## Review

**Verdict: no invariant violated. One correctness bug and one false evidence claim, both
fixed in this same task. Three findings queued.** Reviewed on Opus, gated because the task
touches idempotent background work and the MVP sentence.

The reviewer independently re-derived the safety argument rather than trusting the docstring:
confirmed via `execution.py`'s `_claim` and `execute()` that a late-arriving redelivered
message finds `run.is_terminal` and returns untouched (no double-processing on the accepted
path), and reproduced the whole recovery sequence itself on the live stack, separately from
the builder's run.

**Fix now (both applied above, re-verified):**
1. **The reap was select-then-save, not an atomic filtered `UPDATE`** — a worker's `_claim`
   could flip a selected row to `RUNNING` in the gap before the per-row `.save()` landed,
   which would then overwrite that row back to `FAILED` while a worker was actively evaluating
   it, and `request_check` would dispatch a second, genuinely concurrent run. This is exactly
   the failure mode the task's own design rationale rejects re-dispatch to avoid, reopened by
   the implementation rather than the design. Fixed by collapsing selection and write into one
   `runs.dispatch_lost(...).update(...)`, mirroring `reap_stalled`'s existing pattern.
2. **The evidence's Step 2 paste did not show what it claimed.** The pasted "new run created"
   uuid had zero rows in Postgres and a `NotFoundError` in the worker log 63ms after dispatch
   — round 1's cleanup script deleted the run before independently confirming it, and a guess
   ("a stale in-memory read") was stated as fact rather than checked. Re-run cleanly: the
   recovered run now persists, is confirmed to exist via a fresh query after reaching a
   terminal state, and the corrected evidence is in section 2 above. The reviewer's own
   independent reproduction on the live stack (a different run, `3c7c8f6d`/`6f3643fe` in their
   report) landed the same result, so the underlying mechanism was never actually broken —
   only the round-1 paste misrepresented it.

Both mutation-tested: reverting the `UPDATE` collapse back to a per-row loop is not itself
re-tested here (a true concurrent-claim race is not deterministically unit-testable), but the
age-threshold gap the review also found *is* — see the third new test above, which fails with
`DID NOT RAISE ConflictError` when `created_at__lt=cutoff` is removed and passes restored.

**Queued rather than fixed here:**
- **T-0084** — `reap_stalled_runs` (the RUNNING-side sibling of this task's PENDING fix) is
  registered nowhere: no Celery beat schedule, no `beat` service in `deploy/compose.yaml`, no
  management command. It has never run in any deployment. The same "a review can be
  permanently stuck" failure this task just closed for `PENDING` is therefore still fully open
  for `RUNNING`, right now. Reviewer-gated; likely the single most urgent item in the current
  backlog.
- **T-0085** — because the reap is reactive-only (runs only from inside `request_check`, only
  at the moment of refusal), a lost-dispatch run is indistinguishable from a healthy queued one
  for up to `CHECK_RUN_STALL_SECONDS` (default 1800s), and any retry inside that window still
  returns the same `ConflictError` a genuinely-busy review would. The scope item "the user can
  see that a check never started, distinguished from one still queued" is only true after that
  window and only if a retry happens to land after it.
- **Frontend render test** — `ReviewDetailPage.tsx`'s new `failure_detail` render has no
  automated test, only the manual browser proof in section 2. Not a new task: this is exactly
  what **T-0046** (no component test runner in `services/web`) already exists to fix; folded
  into its existing scope rather than duplicated.

**Minor, not actioned:** the reviewer noted the stored sentence ("its dispatch never reached a
worker") would overclaim a specific cause in the false-positive precondition of finding 1 —
moot once the `UPDATE` fix landed, since a worker-claimed row (`status=RUNNING`) can no longer
match `dispatch_lost`'s filter in the first place. The `.gitignore` change present in the
working tree (`/.cadgpt/inbr/`, referencing an unrelated `feat/inbr-regulations-pipeline`) is
confirmed pre-existing and unrelated to this task; left out of this task's commit.
