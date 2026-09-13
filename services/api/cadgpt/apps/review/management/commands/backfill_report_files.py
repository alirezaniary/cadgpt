"""Generate the Markdown report file for every succeeded run that has none.

Every run that succeeded before T-0032 deployed the generator has no `report_file` and
never will unless something asks for one -- there was no recovery path until
`docs/tasks/T-0051-a-report-that-failed-to-generate-can-be-recovered.md`. This is that
path's operational half; `CheckRunViewSet.generate_report` is the user-facing one,
for a single run.

Idempotent the same way `ReportGenerationService.generate` is: re-running this after a
partial pass, or after generation later fails for one run and is fixed, costs nothing
extra for a run that already has a file. `CheckRunQuerySet.missing_report` never
re-selects a run whose generation permanently failed (`report_generation_error` set), so
this cannot loop forever restating the same rejection -- an operator who wants to retry
one of those anyway calls `ReportGenerationService.generate` on it directly.

**One run's exception does not abort the sweep (T-0057).** `generate` can raise -- a
storage outage from `MediaService.store`, a `NotFoundError` for a row deleted since the
cursor snapshot, the `ValueError` branch -- and until this task, any of those killed the
whole loop: the command crashed with a traceback, never printed its `done:` summary, and
left every run after the one that raised unprocessed, including runs with nothing wrong
with them. `generate`'s own transaction boundary (unchanged, out of scope here -- see
`report_generation.py`'s module docstring) already makes each run's outcome independent
of every other run's, so nothing about database coherence required the loop itself to be
all-or-nothing; only this command's own lack of a per-run `try` did. Each eligible run is
now attempted regardless of what happened to the run before it, the summary counts a
raise as a failure alongside a `TOO_LARGE`-style non-exceptional failure -- the old
`failed` counter could only ever count the latter, which made it structurally unable to
report the exact failure mode this task is about -- and the command exits non-zero if any
run failed either way, so a script invoking this does not have to parse `done:`'s prose to
know whether to retry or alert.

**`--include-failed` (T-0059).** `missing_report` permanently excludes a run whose
`report_generation_error` is set -- correctly, for the default sweep above: retrying an
unchanged cause (the size cap) would just restate the same `TOO_LARGE` rejection forever.
But `ReportGenerationService._attach` already anticipates a later attempt succeeding once
the cause changes -- an operator raising `MAX_BYTES[MediaKind.REPORT]`, or a code change
that shrinks the render -- and clears the error on success. Until this flag existed, there
was no supported way to actually make that later attempt: an operator had to call
`ReportGenerationService.generate` by hand, one uuid at a time, via `manage.py shell`, with
no listing of which runs were even stranded. This command now always prints how many runs
are in that state before doing anything -- visible on every invocation, not gated behind a
separate listing mode, so an operator sees the number and decides whether `--include-failed`
is warranted without having to opt in just to look. Passing the flag adds
`CheckRunQuerySet.generation_failed()` to the sweep, alongside `missing_report()`,
unchanged. Both querysets already exclude any run with a `report_file`, and `generate`
itself is a no-op for one, so the opt-in path is exactly as idempotent as the default
sweep -- no separate check was added here to duplicate what `generate` already
guarantees.
"""

from __future__ import annotations

from typing import Any

from django.core.management.base import BaseCommand, CommandError

from cadgpt.apps.review.models import CheckRun
from cadgpt.apps.review.services.report_generation import ReportGenerationService


class Command(BaseCommand):
    help = "Generate the report file for every succeeded check run that has none."

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument(
            "--include-failed",
            action="store_true",
            help=(
                "Also retry runs whose report generation failed terminally "
                "(report_generation_error is set, e.g. too_large) -- opt-in, "
                "for after the cause has changed (MAX_BYTES[MediaKind.REPORT] "
                "raised, or a fix shipped that shrinks the render). Not part of "
                "the default sweep: retrying an unchanged cause would only "
                "restate the same rejection."
            ),
        )

    def handle(self, *args: Any, **options: Any) -> None:  # noqa: ARG002
        service = ReportGenerationService()
        generated = 0
        failed = 0
        considered = 0
        include_failed = bool(options["include_failed"])

        stranded = CheckRun.objects.generation_failed().count()
        if include_failed:
            self.stdout.write(f"{stranded} previously-failed run(s) included in this sweep")
        else:
            self.stdout.write(
                f"{stranded} previously-failed run(s) not swept -- "
                "rerun with --include-failed once the cause has changed"
            )

        queryset = CheckRun.objects.missing_report()
        if include_failed:
            queryset = queryset | CheckRun.objects.generation_failed()

        for run in queryset.order_by("created_at").iterator():
            considered += 1
            try:
                result = service.generate(run.uuid)
            except Exception as exc:  # noqa: BLE001 -- one run's failure must not end the sweep
                failed += 1
                self.stdout.write(
                    self.style.ERROR(
                        f"could not generate: run {run.uuid} "
                        f"(raised {exc.__class__.__name__}: {exc})"
                    )
                )
                continue

            if result.report_file_id is not None:
                generated += 1
                self.stdout.write(f"generated: run {result.uuid}")
            else:
                failed += 1
                self.stdout.write(
                    self.style.WARNING(
                        f"could not generate: run {result.uuid} "
                        f"({result.report_generation_error})"
                    )
                )

        self.stdout.write(
            f"done: {generated} generated, {failed} could not be generated, "
            f"{considered} runs considered"
        )

        if failed:
            # Non-zero exit, distinct from a clean sweep, so a script invoking this
            # command can tell "swept, some runs failed" apart from "swept cleanly"
            # without parsing the prose above. `CommandError` is Django's own signal for
            # this: `manage.py` catches it and exits 1 after printing the message below;
            # `call_command` (tests, any in-process caller) lets it propagate as a normal
            # Python exception instead of killing the interpreter, unlike `sys.exit`.
            raise CommandError(
                f"{failed} of {considered} run(s) could not be generated; see output "
                "above. Safe to re-run: each run's own generation is independent and "
                "idempotent."
            )
