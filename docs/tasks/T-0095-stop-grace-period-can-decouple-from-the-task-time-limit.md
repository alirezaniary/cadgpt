# T-0095 — `stop_grace_period` is a hardcoded literal that can silently decouple from `CELERY_TASK_TIME_LIMIT`

**Phase:** 3   **Status:** open
**Touches invariants:** none — a robustness gap in T-0062's own fix, not a live defect at
default settings.

## Why

Found by T-0062's review. `deploy/compose.yaml`'s `worker.stop_grace_period:
${WORKER_STOP_GRACE_PERIOD:-1860s}` is presented, in its own comment, as derived from
`CELERY_TASK_TIME_LIMIT + 60` — but compose files cannot do arithmetic, so `1860s` is
actually an independent literal that merely happens to equal that sum today. T-0062's own
diff made `CELERY_TASK_TIME_LIMIT` overridable from compose (`${CELERY_TASK_TIME_LIMIT:-1800}`)
for its own evidence-gathering — which means `CELERY_TASK_TIME_LIMIT=3600 docker compose up
-d worker`, with `WORKER_STOP_GRACE_PERIOD` left at its default, silently reintroduces
exactly the bug T-0062 exists to fix: a check now legitimately allowed to run for an hour,
against a grace period still fixed at 1860s, so Docker's SIGKILL fires again on an ordinary
deploy. T-0062's own proof 2 had to set both variables by hand, which is exactly the
manual-coupling risk this task is about. Nothing today asserts the two stay in the
relationship the fix depends on.

## Scope

- A test, following the precedent `test_celery_beat_schedule.py` already set for pinning
  config-derived wiring (rather than trusting a docstring), that fails if
  `stop_grace_period` is not comfortably above `CELERY_TASK_TIME_LIMIT` — this likely means
  reading both values from the same place at runtime (an env var read directly by the test,
  or a shared derivation) rather than duplicating the `1800 + 60` arithmetic as a second
  hardcoded expectation.
- Alternatively (smaller, and worth considering first): derive `stop_grace_period` from
  `CELERY_TASK_TIME_LIMIT` at a layer that *can* do arithmetic — an entrypoint script, or a
  documented convention that only `CELERY_TASK_TIME_LIMIT` is ever meant to be overridden
  in production, with `WORKER_STOP_GRACE_PERIOD` reserved for test/evidence use only. State
  which approach you take and why.

## How to prove it ran

A test or check that fails when the two are set inconsistently (e.g.
`CELERY_TASK_TIME_LIMIT=3600` with `WORKER_STOP_GRACE_PERIOD` left at its default), and
passes at today's paired defaults.

## Evidence

## Review
