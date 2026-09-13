# T-0059 — A run stranded by the size cap has no way back once the cap is raised

**Phase:** 3   **Status:** done
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

**Changes.**

1. `CheckRunQuerySet.generation_failed()` -- `services/api/cadgpt/apps/review/repositories/querysets.py`
   -- the complement of `missing_report`: `SUCCEEDED`, no `report_file`, and
   `report_generation_error` set. `missing_report` itself is untouched (still `status=SUCCEEDED,
   report_file_id__isnull=True, report_generation_error=""`) -- verified by re-reading the method
   after the edit and by `test_the_default_sweep_still_ignores_a_run_the_cap_stranded` below.
2. `backfill_report_files --include-failed` -- `services/api/cadgpt/apps/review/management/commands/
   backfill_report_files.py` -- an opt-in `store_true` flag. `Command.handle` now always prints the
   count of `generation_failed()` rows before doing anything (the "see before you sweep" requirement),
   worded differently depending on whether the flag was passed, and only unions
   `generation_failed()` into the swept queryset (`missing_report() | generation_failed()`) when the
   flag is given. No separate "already has a file" check was added for the opt-in path:
   `generation_failed()` already filters `report_file_id__isnull=True` (same as `missing_report`), and
   `ReportGenerationService.generate` is a no-op for a run that has one regardless -- both idempotence
   guarantees are reused, not reimplemented.
3. Four new tests in `services/api/cadgpt/apps/review/tests/test_report_generation.py` (13 -> 17):
   `test_the_default_sweep_still_ignores_a_run_the_cap_stranded`,
   `test_include_failed_retries_a_run_once_the_cause_has_changed`,
   `test_include_failed_does_not_disturb_a_run_that_already_has_a_report`, and the queryset is
   exercised directly inside the first two.

**Not changed:** `missing_report`'s filter, the `TOO_LARGE` decision (`ReportGenerationService.
generate`/`_record_failure`/`_attach`, untouched), `MAX_BYTES[MediaKind.REPORT]`.

### `make verify`

```
uv run ruff check .          -> All checks passed!
uv run ruff format --check . -> 195 files already formatted
uv run mypy packages/engine/src services/api/cadgpt -> Success: no issues found in 177 source files
uv run lint-imports --no-cache -> Contracts: 5 kept, 0 broken.
uv run pytest -m "not postgres" -> 325 passed, 1 deselected, 37 warnings in 5.94s
cd services/web && pnpm run verify -> lint (2 pre-existing warnings, 0 errors), tsc clean,
  vite build succeeded, storybook build succeeded, 6 unit tests passed, 36 storybook tests passed
```

Pytest equivalent of the real-path proof below, deterministic and isolated (same techniques as
`test_a_report_too_large_to_store_leaves_the_run_succeeded_with_no_file` and
`test_backfill_generates_reports_for_runs_that_were_never_dispatched`):
`test_the_default_sweep_still_ignores_a_run_the_cap_stranded`,
`test_include_failed_retries_a_run_once_the_cause_has_changed`,
`test_include_failed_does_not_disturb_a_run_that_already_has_a_report`.

### Real path, against the live compose stack

`api`, `worker` and `beat` rebuilt from the changed source (`cadgpt-api:latest`, one image for both
services per the Dockerfile's own comment) and recreated, healthy, before any of this ran.

**Setup: a run driven to `TOO_LARGE` under a real, artificially low cap** -- same technique T-0051's
own evidence used (real IFC, real IDS, real engine run, only `MAX_BYTES[MediaKind.REPORT]` turned
down in-process so the real render trips the real `MediaService._validate` check), run inside
`manage.py shell`:

```
$ docker compose exec api python manage.py shell < t0059_setup.py
...
TENANT_SLUG=t0059-1789337478
OWNER_EMAIL=t0059-1789337478@example.test
REVIEW_UUID=e404e663-6b4d-4005-8e44-7fd9f5d2c9ab
RUN_UUID=897dff04-47eb-4902-a0ca-61ac35c81850
[warning] report_generation_failed detail='This file is larger than the 10 bytes limit.' reason=too_large run_id=897dff04-...
status: succeeded
report_file_id: None
report_generation_error: ReportGenerationFailure.TOO_LARGE
matches TOO_LARGE: True
```

**The default sweep, run in a fresh `manage.py` process (real cap, 8 MB) -- still ignores it:**

```
$ docker compose exec api python manage.py backfill_report_files
2 previously-failed run(s) not swept -- rerun with --include-failed once the cause has changed
done: 0 generated, 0 could not be generated, 0 runs considered

$ docker compose exec api python manage.py shell -c "print(CheckRun.objects.get(uuid='897dff04-...').report_file_id, CheckRun.objects.get(uuid='897dff04-...').report_generation_error)"
None too_large
```

Confirms the invariant this task must not break: an unchanged cause is never retried automatically.
The "cause changed" here is exactly what happens in production between one `manage.py` invocation
and the next once an operator raises `MAX_BYTES[MediaKind.REPORT]` and redeploys -- the constant is
read fresh by every new process, which is why no explicit "raise the cap back" step was needed
beyond starting a new process; the low value only ever lived inside the one throwaway shell process
that manufactured `TOO_LARGE` above.

**The opt-in sweep, `--include-failed`, in that same fresh-cap process -- retries and succeeds:**

```
$ docker compose exec api python manage.py backfill_report_files --include-failed
2 previously-failed run(s) included in this sweep
[info] media_stored kind=report ... tenant_id=99c39e4b-... size_bytes=1773
[info] report_file_generated run_id=1da7349b-... service=ReportGenerationService
generated: run 1da7349b-0ca4-4f90-9605-8bc42ffebeaa
[info] media_stored kind=report ... tenant_id=75baa655-... size_bytes=1348
[info] report_file_generated run_id=897dff04-... service=ReportGenerationService
generated: run 897dff04-47eb-4902-a0ca-61ac35c81850
done: 2 generated, 0 could not be generated, 2 runs considered
```

(`1da7349b-...` is a second run this same live database already carried in `TOO_LARGE` from an
earlier evidence session, not something this task's setup created -- the sweep is not scoped to
only what the setup script made, exactly like T-0051's backfill proof.)

```
$ docker compose exec api python manage.py shell -c "..."
report_file_id: 135
report_generation_error: ''
report_file.kind: report
```

`report_generation_error` cleared and a real `report_file` attached, exactly what `_attach`'s own
comment ("cleared, not merely left alone... a retry that succeeds after an earlier permanent-looking
failure") anticipates.

**Idempotent: a second `--include-failed` sweep finds nothing left and touches nothing:**

```
$ docker compose exec api python manage.py backfill_report_files --include-failed
0 previously-failed run(s) included in this sweep
done: 0 generated, 0 could not be generated, 0 runs considered
```

**The file, fetched over authenticated HTTP** -- real JWT login, real tenant header, the same route
`CheckRunViewSet.report_file` every other report is served from:

```
$ TOKEN=$(curl -s -X POST http://localhost:8000/api/v1/auth/login/ \
    -H "Content-Type: application/json" \
    -d '{"email":"t0059-1789337478@example.test","password":"correct-horse-battery-t0059"}' \
    | python3 -c "import sys,json;print(json.load(sys.stdin)['access'])")

$ curl http://localhost:8000/api/v1/reviews/e404e663-.../runs/897dff04-.../ \
    -H "Authorization: Bearer $TOKEN" -H "X-Tenant: t0059-1789337478"
{"status": "succeeded", ..., "report_file_url": "/api/v1/reviews/e404e663-.../runs/897dff04-.../report-file/",
 "report_generation_error": ""}

$ curl -w "\nHTTP_STATUS:%{http_code}\n" \
    http://localhost:8000/api/v1/reviews/e404e663-.../runs/897dff04-.../report-file/ \
    -H "Authorization: Bearer $TOKEN" -H "X-Tenant: t0059-1789337478"
# Accessible door width

three_doors.ifc . Model schema IFC4 . Engine 0.2.0

**Status:** Fail
...
HTTP_STATUS:200
```

### Wiring

- Management command registered by Django's standard discovery (unchanged mechanism, same as
  `seed_rule_packs` and the pre-existing `backfill_report_files`), runnable and run above as
  `manage.py backfill_report_files [--include-failed]`:
  `services/api/cadgpt/apps/review/management/commands/backfill_report_files.py`.
- New flag registered on that same command's `Command.add_arguments`:
  `parser.add_argument("--include-failed", action="store_true", ...)`.
- Queryset method backing the opt-in sweep, on the same manager the default sweep already uses
  (`CheckRun.objects`, `CheckRunManager(Manager.from_queryset(CheckRunQuerySet))` in
  `services/api/cadgpt/apps/review/repositories/custom_managers.py`):
  `CheckRunQuerySet.generation_failed()` in
  `services/api/cadgpt/apps/review/repositories/querysets.py`.
- No new route, model field, or migration -- this task adds a command flag and a queryset method
  over data the schema (T-0051's `0004_checkrun_report_generation_detail_and_more`) already carries.

### NOT DONE

Nothing. Both required behaviours (the default sweep still ignoring an unchanged cause; the opt-in
sweep recovering a run once the cause changed, ending with a real, fetchable report file) are proven
against the real compose stack above, plus their deterministic pytest equivalents; `make verify` is
green end to end.

## Review

Not reviewer-gated — no invariant, small diff (48 lines in the command, 21 in the queryset,
the rest tests), fully read by the coordinator. `generation_failed()` is the exact
complement of `missing_report()` (partitioning "never tried" from "tried and terminally
rejected"), the opt-in flag adds nothing to the default sweep's queryset, and idempotence is
reused from `generate()`'s own no-op-on-existing-file contract rather than re-implemented.
Composes cleanly with T-0057's per-run try/except and T-0058's removed frontend retry
button — read alongside both diffs before writing this one, per instruction, and neither was
disturbed. Verified against a real run driven to `TOO_LARGE`, a fresh process standing in
for the cap being raised (the default sweep still ignoring it, `--include-failed` recovering
it with a real fetchable report file over authenticated HTTP), and a second `--include-failed`
run confirmed as a genuine no-op.