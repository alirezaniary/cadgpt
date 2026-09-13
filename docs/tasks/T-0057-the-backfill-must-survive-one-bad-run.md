# T-0057 — The backfill aborts the whole sweep on one raising run, and loses its accounting

**Phase:** 3   **Status:** done
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

### Changes

`services/api/cadgpt/apps/review/management/commands/backfill_report_files.py`:

- Each `service.generate(run.uuid)` call is now wrapped in its own `try/except Exception`.
  A raise (storage outage, `NotFoundError`, the `ValueError` branch) is caught, logged as a
  failure for that one run, and the loop `continue`s to the next eligible run instead of
  propagating out of `handle`.
- `failed` is now incremented both when `generate` raises and when it returns a run with
  `report_file_id` still `None` (the pre-existing `TOO_LARGE`-style path) — one counter that
  can express both failure modes, not a counter that structurally excludes the one this task
  is about.
- The `done:` summary line is unchanged in shape and still always printed, now including the
  raise-derived count.
- After printing `done:`, `Command.handle` raises `django.core.management.base.CommandError`
  if `failed > 0`. **Exit-status decision:** `CommandError` (not `sys.exit`), because Django's
  own `execute_from_command_line`/`ManagementUtility.execute()` already catches it, prints
  `Error: <message>` to stderr, and calls `sys.exit(1)` — exactly the "swept, some failed"
  signal a script needs, for free, under the real `manage.py` entry point. Under
  `django.core.management.call_command` (every test, and any other in-process caller), the
  same `CommandError` propagates as an ordinary Python exception instead of killing the
  interpreter, which `sys.exit` would have done to the calling process. A clean sweep
  (`failed == 0`) raises nothing and exits 0.

`services/api/cadgpt/apps/review/tests/test_report_generation.py`: added
`test_a_run_that_raises_does_not_abort_the_sweep_and_the_summary_counts_it` — the reviewer's
exact scenario (three eligible runs, `MediaService.store` raising `OSError` on the second
call), asserting all three are attempted, the summary counts `2 generated, 1 could not be
generated, 3 runs considered`, and `CommandError` propagates through `call_command`.

`ReportGenerationService.generate` and its transaction boundaries: untouched, as scoped.

### `make verify`

```
uv run ruff check .          -> All checks passed!
uv run ruff format --check . -> 195 files already formatted
uv run mypy packages/engine/src services/api/cadgpt -> Success: no issues found in 177 source files
uv run lint-imports --no-cache -> Contracts: 5 kept, 0 broken.
uv run pytest -m "not postgres" -> 322 passed, 1 deselected, 37 warnings in 5.74s   (baseline 321 + 1 new)
cd services/web && pnpm run verify -> lint clean (2 pre-existing warnings, unrelated files),
                                       tsc clean, vite build succeeded, 6+36 vitest passed
```
Full `make verify` exit code: `0`.

### Real path: the reviewer's exact scenario, before and after

Run against the live `make up` stack (`cadgpt-api-1`, real Postgres, real worker). Three real
succeeded `CheckRun`s were produced first — a real tenant, a real IFC (`three_doors.ifc`) and
IDS (`door_width.ids`) upload, three sequential real checks dispatched through
`ReviewService.request_check` and executed by the real Celery worker — then each run's
`report_file_id` was nulled back out by hand, the same technique T-0051's own evidence used
to stand in for a lost dispatch / pre-T-0032 row:

```
$ docker compose exec api python manage.py shell -c "<create tenant/review, run 3 real checks, null report_file_id on all 3>"
TENANT_SLUG t0057-1789335017
RUN_UUIDS [UUID('ead2ece8-...'), UUID('30df0c68-...'), UUID('95f11c72-...')]
missing_report count 3
```

`MediaService.store` is monkeypatched, in-process, to raise `OSError` on its second call —
the reviewer's exact injection point — then the real entry point is invoked via
`execute_from_command_line(["manage.py", "backfill_report_files"])`, the same call
`manage.py` itself makes.

**Before the fix** (this same command against the pre-T-0057 code, still deployed in the
running container's image at the time):

```
$ docker compose exec api python manage.py shell -c "<patch MediaService.store, run backfill>"
=== invoking the real entry point: manage.py backfill_report_files ===
[info] media_stored kind=report ... tenant_id=eb6c39ca-...
[info] report_file_generated run_id=d202e529-... service=ReportGenerationService
generated: run 62fdf4c6-5352-4919-ac60-45fc845ffb66
Traceback (most recent call last):
  ...
  File ".../backfill_report_files.py", line 38, in handle
    result = service.generate(run.uuid)
  File ".../report_generation.py", line 116, in generate
    media = MediaService(tenant=run.tenant).store(
  File "<string>", line 15, in _flaky_store
OSError: simulated storage outage (T-0057 reproduction)
EXIT STATUS: 1
```

Confirmed: crashed with a raw traceback, printed exactly one `generated:` line, **never
printed `done:`**, and the third run was never attempted at all — exactly the defect this
task describes.

**After the fix** (fixed file copied into the same running container; fresh batch of 3
eligible runs, same injection):

```
$ docker compose exec api python manage.py shell -c "<patch MediaService.store, run backfill>" \
    1>stdout.txt 2>stderr.txt
$ echo $?
1
```

stdout:
```
=== invoking the real entry point: manage.py backfill_report_files ===
[info] media_stored kind=report ... tenant_id=0018713f-...
[info] report_file_generated run_id=ead2ece8-... service=ReportGenerationService
generated: run ead2ece8-c312-4903-a8d7-b4b51c6caf8f
could not generate: run 30df0c68-723a-49b5-ab1e-2d1d13190c47 (raised OSError: simulated storage outage (T-0057 reproduction))
[info] media_stored kind=report ... tenant_id=0018713f-...
[info] report_file_generated run_id=95f11c72-... service=ReportGenerationService
generated: run 95f11c72-457d-40f4-8051-6e9f8a1836e9
done: 2 generated, 1 could not be generated, 3 runs considered
```

stderr:
```
CommandError: 1 of 3 run(s) could not be generated; see output above. Safe to re-run: each run's own generation is independent and idempotent.
```

Confirmed: all three eligible runs were attempted regardless of the raise on the second one
(the third, which had nothing wrong with it, was generated same as if nothing had happened),
the `done:` summary was printed and counts the raise as one of the `1 could not be
generated`, and the process exited `1` — distinct from a clean sweep.

**Re-running recovers the failed run, and a clean sweep exits 0** — proving the exit status
really distinguishes the two cases, and that the sweep is safe to retry exactly as its own
docstring now claims:

```
$ docker compose exec api python manage.py backfill_report_files
[info] media_stored kind=report ...
[info] report_file_generated run_id=30df0c68-723a-49b5-ab1e-2d1d13190c47 ...
generated: run 30df0c68-723a-49b5-ab1e-2d1d13190c47
done: 1 generated, 0 could not be generated, 1 runs considered
$ echo $?
0
```

Pytest equivalent, deterministic, same technique (three real sequential checks via
`ReviewService.request_check`, `MediaService.store` raising `OSError` on the second of three
eligible runs, invoked through `call_command`):
`test_a_run_that_raises_does_not_abort_the_sweep_and_the_summary_counts_it`, passing:

```
$ uv run pytest services/api/cadgpt/apps/review/tests/test_report_generation.py -k "backfill or raises_does_not_abort" -v
services/api/cadgpt/apps/review/tests/test_report_generation.py ..
2 passed, 12 deselected in 2.25s
```

### Wiring

Nothing new needed registering — this is a fix inside an already-registered management
command's `handle`, discovered by Django's standard module-path convention (unchanged from
T-0051):

```
services/api/cadgpt/apps/review/management/commands/backfill_report_files.py
```

runnable, and run above, as `manage.py backfill_report_files`. No new route, task, or
migration. The only new import is Django's own `CommandError`
(`from django.core.management.base import BaseCommand, CommandError`), which is how
`ManagementUtility.execute()` — the code `manage.py`'s own `execute_from_command_line` calls —
recognizes a command's deliberate non-zero exit, the same mechanism
`cadgpt/apps/rulepack/management/commands/seed_rule_packs.py` already uses for its own fatal
condition.

### NOT DONE

Nothing. All three scope items (per-run isolation, a summary counter that can express a
raise, and a distinguishable exit status) are implemented and evidenced above against the
real entry point, both directly (`docker compose exec api python manage.py
backfill_report_files`) and via `manage.py shell`'s `execute_from_command_line` /
`call_command`. `ReportGenerationService.generate` and its transaction boundary were not
touched.

## Review

Not reviewer-gated — no invariant, small diff (42 lines in the command file, 72 in the test),
fully read by the coordinator. `generate`'s exception is now caught per-run and counted
rather than propagated, the summary counter covers both failure modes, and `CommandError` is
reused from the same pattern `seed_rule_packs.py` already established for a fatal-but-not-
crashing exit. Verified against a real Docker reproduction (three real check runs, a real
storage-layer `OSError` injected on the second): before the fix the command crashed after one
`generated:` line and never printed `done:`; after, all three runs were attempted, the
summary read `2 generated, 1 could not be generated, 3 runs considered`, and the process
exited 1 — then a re-run recovered the failed run and exited 0. A deterministic pytest
equivalent covers the same scenario for `make verify`.