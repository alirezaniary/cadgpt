# T-0059 — A run stranded by the size cap has no way back once the cap is raised

**Phase:** 3   **Status:** open
**Touches invariants:** none.

## Why

Found by the T-0051 review, and it is the operational half of T-0058.

`report_generation.py:143-146` explicitly anticipates a later attempt succeeding — its own comment
names "a code change lowering the rendered size, or an operator raising the cap" — and clears
`report_generation_error` on success. But `missing_report` (`querysets.py:73-77`) excludes rows with
a non-empty `report_generation_error` **permanently**, and `backfill_report_files` has no
`--include-failed`.

So the moment an operator does the thing the code anticipates — raise `MAX_BYTES[REPORT]` — there is
no supported way to sweep the runs the old cap stranded. The command's docstring tells them to call
`ReportGenerationService.generate` directly, which means `manage.py shell` against production, one
uuid at a time, with no list of which uuids.

The exclusion is right for the default sweep: retrying an unchanged cause would restate the same
rejection forever, which is what `missing_report`'s docstring says. What is missing is the
deliberate, operator-driven sweep for when the cause *has* changed.

## Scope

**Changes**

- A supported way to re-attempt runs whose report generation failed terminally, opt-in rather than
  part of the default sweep, so the meaning of `missing_report` does not change.
- The operator can see which runs are in that state before deciding — a count or a listing, not a
  blind sweep.
- Idempotent, and it must not disturb runs that already have a report.

**What explicitly does not change**

- `missing_report`'s semantics or the default backfill's behaviour.
- The `TOO_LARGE` decision, settled in T-0051.
- The size cap itself. Whether `MAX_BYTES[REPORT]` is the right number is T-0033's kind of question,
  measured rather than chosen — this task is about recovering from whatever it is.

## How to prove it ran

`make verify`, then on the real stack: a run driven to `TOO_LARGE` under a low cap, the cap raised,
the opt-in sweep run, and that same run ending with a real report file fetched over authenticated
HTTP. Show also that the default sweep still ignores it, so nothing retries a genuinely unchanged
cause on its own.

## Evidence

## Review
