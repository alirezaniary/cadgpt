# T-0051 — A report that was never generated must be recoverable

**Phase:** 3   **Status:** open
**Touches invariants:** the MVP's own sentence. **Reviewer-gated.**

## Why

Found by the T-0032 review, which called it the highest of its queued findings and suggested
promoting it. It is queued rather than fixed inside T-0032 because it is **new work — a recovery
path that has never existed** — not a defect in what T-0032 built.

The MVP is *"the user uploads a model, picks which rules to run it against, and gets back a report
file."* Today a run can satisfy the first two clauses, report `succeeded`, and **never produce the
file, permanently, with no way to ask for it again.**

`CheckRunExecutor._succeed` registers the generation on commit; `execute()` returns early for any
terminal run. So if the `on_commit` callback is lost — a worker dying between `COMMIT` and the
callback, which `acks_late` plus `reject_on_worker_lost` make the *designed* hazard — redelivering
`execute_check_run` finds a terminal run and returns. The reviewer executed exactly this: stub the
dispatch for one run, redeliver, and the end state is `status=succeeded, report_file_id=None,
report media rows: 0`, permanently. `reap_stalled` only touches `RUNNING`, so nothing reaps it.

The same end state arrives by three other routes: `.delay()` raising because the broker blipped;
`generate` raising anything outside the retried `(ConnectionError, TimeoutError)`; or
`MediaService._validate` rejecting the rendered file — a large report against the 8 MB cap in
`media/constants.py` is not far-fetched for a 3,623-finding run like Schependomlaan.

And it is not hypothetical for existing data: **every run that succeeded before T-0032 deployed is
in precisely this state.** The frontend shows no button, and there is no route, task, or management
command that can produce the file.

## Scope

**Changes**

- A way to generate the report for a succeeded run that has none. It must be reachable both
  operationally (a management command, for the backfill) and by the user (the run knows its report
  is missing and can ask for it). Idempotent, and it must not disturb a run that already has one.
- The backfill for runs that predate T-0032.
- The frontend stops presenting "no report" and "report not generated yet" as the same silence.
  Both i18n catalogues.
- Decide deliberately whether a report that cannot be generated at all — the 8 MB cap case — is a
  failure of the *run* or a run that succeeded with no file, and say which in the evidence. A check
  that genuinely found what it found should probably not be retro-failed because its report did not
  fit; but the user must not be told a file exists when it does not.

**What explicitly does not change**

- The generator, the presentation rules, the language decision, the storage location. T-0032
  settled those; this is about the file that never arrived.
- `reap_stalled_runs`, which solves the different problem of a run whose worker vanished while it
  was still `RUNNING`.

## How to prove it ran

`make verify`, then against `make up`:

1. Reproduce the hole first: stub or drop the dispatch, complete a real run, and show
   `succeeded / report_file_id=None` with no way to recover — the state as it is today.
2. The recovery path invoked, and the file appearing on that same run, fetched over authenticated
   HTTP.
3. The backfill run over a run created before the feature existed.
4. Idempotence: recovery invoked twice produces one file, and invoked against a run that already
   has a report changes nothing.
5. The frontend distinguishing the two silences, rendered.

## Evidence

## Review
