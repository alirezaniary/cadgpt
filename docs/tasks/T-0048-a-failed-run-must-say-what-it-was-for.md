# T-0048 — A failed run must say what it was supposed to check, and speak the application's error language

**Phase:** 3   **Status:** open
**Touches invariants:** "never assert compliance we did not establish" — its mirror, a failure
that fails to explain itself.

## Why

Found by the T-0031 review, which executed all three of these against the real stack. A run that
fails currently tells the tenant a Python detail, an internal storage key, or nothing at all.

1. **`_combine_reports([])` raises `IndexError`, and the tenant is shown the traceback fragment.**
   `execution.py`'s `first = reports[0]` is reached whenever a run has `review.rule_set is None`
   and an empty `rule_pack_selection`. Executed: `failed | internal_error | list index out of
   range`. `failure_detail` is on `CheckRunSummarySerializer`, so **"list index out of range" is
   what the user reads**. Not reachable over HTTP today — `ReviewViewSet` has no update mixin and
   `_resolve_selection` refuses an empty selection at request time — but reachable from
   `ReviewService.create(rule_set=None)` plus `create_run`, which is a management command or a
   future task away.

2. **Internal storage keys reach the tenant.** Pack row present, stored file gone. Executed:
   `failed | internal_error | [Errno 2] No such file or directory: 'rule-packs/sample/5d29…ids'`.
   The storage key is shown to the user, and the classification is wrong: `invalid_rule_set` is
   accurate, `internal_error` is not. The `_fail` truncation shape is pre-existing; the catalogue
   path is a new way to reach it.

3. **A failed run never shows what it was supposed to check.** `ReviewsPage.tsx` renders
   `ReportView` only when `run.data?.report` is truthy, and a failed run has no report. The run
   that fails *because* a cited pack vanished shows the reason but never the selection — so the
   one screen where "what was this supposed to cover?" matters most is the one that does not
   answer it.

## Scope

**Changes**

- A run that reaches execution with nothing to check terminates with a named reason rather than
  an `IndexError`. `CheckRunFailure` already models exactly this distinction between a rejected
  input and a crash.
- Storage-layer errors are classified honestly and do not carry internal paths into
  `failure_detail`. The operator still gets the full error in the log; the tenant gets the
  application's language.
- The run's recorded selection is visible on a failed run, not only on a successful one.

**What explicitly does not change**

- `_resolve_selection`'s request-time refusals (T-0031, correct and tested).
- The `_fail` / `failure_detail` mechanism itself, beyond what these three need.

## How to prove it ran

`make verify`, then each of the three reproduced against `make up` and shown fixed, with the
before and after `status | failure_reason | failure_detail` triple pasted for each. The third is
a rendered browser evidence item, not curl.

## Evidence

## Review
