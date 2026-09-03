# T-0057 — The backfill aborts the whole sweep on one raising run, and loses its accounting

**Phase:** 3   **Status:** open
**Touches invariants:** none.

## Why

Found by the T-0051 review. `management/commands/backfill_report_files.py:36-56` has no per-run
`try`. Any exception from `generate` — a storage outage, a `NotFoundError` for a row deleted since
the cursor snapshot, the `ValueError` branch — kills the loop.

The reviewer executed it: with `MediaService.store` raising `OSError` on its second call over three
eligible runs, the command raised, printed only `generated: run 53d72602-…`, **never printed its
`done:` line**, and left two of three unprocessed — including one with nothing wrong with it.

Database state stays coherent, because each `generate` is its own transaction, and re-running
recovers (`done: 2 generated, 0 could not be generated, 2 runs considered`). So this is not
corruption. It is an operator being handed a traceback instead of an account of what happened,
during exactly the incident — a storage outage — when they most need to know which runs are still
outstanding.

Related and in the same file: `failed` (`:43`) is only ever incremented on the `TOO_LARGE` return,
so the summary line's "could not be generated" **can never count a run that raised**. The number is
structurally incapable of reporting the failure mode this task is about.

## Scope

**Changes**

- One run's failure does not end the sweep. Each run is attempted, and the command finishes and
  reports.
- The summary counts what actually happened, including runs that raised. A count that cannot
  express a failure mode is worse than no count.
- The exit status distinguishes "swept cleanly" from "swept, some failed" — an operator scripting
  this needs to know without parsing prose.

**What explicitly does not change**

- `ReportGenerationService.generate` itself, or its per-run transaction boundary, which is what
  makes the sweep safe to re-run.

## How to prove it ran

`make verify`, then the reviewer's exact reproduction: `MediaService.store` raising on the second of
three eligible runs. Show the command completing, all three attempted, the summary counting the
raise, and the exit status reflecting a partial sweep. Paste the before and after.

## Evidence

## Review
