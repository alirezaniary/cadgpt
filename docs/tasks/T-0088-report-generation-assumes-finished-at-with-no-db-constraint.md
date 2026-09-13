# T-0088 — the report generator's `finished_at` assumption is a convention, not a constraint

**Phase:** 3   **Status:** open
**Touches invariants:** none — a robustness gap in an already-narrow failure path.

## Why

Found by T-0055's review. `services/api/cadgpt/apps/review/services/report_generation.py:140`
now asserts `run.finished_at is not None` before generating a report, reasoning that
`finished_at` is always set in the same transaction that flips a run to `SUCCEEDED`
(`execution.py`'s `_succeed`). That is true of every writer in the codebase today, but it is
enforced only by convention: `CheckRun`'s model
(`services/api/cadgpt/apps/review/models.py:227-234`) carries a
`succeeded_run_has_a_report` constraint but no equivalent `SUCCEEDED ⇒ finished_at NOT NULL`
constraint at the database level.

The assert also sits outside `generate()`'s own `try` block, so if some future writer (a data
migration, a manual admin fix, a new code path) ever produced a `SUCCEEDED` run with a null
`finished_at`, the `AssertionError` would abort the entire `backfill_report_files` sweep rather
than fail just that one run — a batch job taking down the whole batch over one bad row, exactly
the class of defect T-0057 (the backfill's own robustness) exists to prevent for other failure
modes.

## Scope

- Add the `CHECK` constraint at the database level:
  `SUCCEEDED ⇒ finished_at IS NOT NULL` (mirroring `succeeded_run_has_a_report`'s own shape),
  via a migration.
- Either keep the assert (now backed by a real constraint, so it can only fire on a genuine
  invariant violation, which is exactly what an assert is for) or move the check inside
  `generate()`'s `try` so one malformed row fails that row's generation rather than the whole
  sweep — pick whichever this codebase's existing pattern for per-row failure in a sweep
  already establishes (check `backfill_report_files`'s other per-row error handling first).

## How to prove it ran

`make verify` with the migration applied and at head. A test attempting to construct a
`SUCCEEDED` run with `finished_at=None` and showing the database rejects it (an `IntegrityError`
at the constraint, not at the application layer). If the batch-vs-single-row handling is
changed, a test demonstrating one bad row no longer aborts the rest of a `backfill_report_files`
sweep.

## Evidence

## Review
