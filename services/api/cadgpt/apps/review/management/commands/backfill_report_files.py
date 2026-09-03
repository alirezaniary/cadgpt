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
"""

from __future__ import annotations

from typing import Any

from django.core.management.base import BaseCommand

from cadgpt.apps.review.models import CheckRun
from cadgpt.apps.review.services.report_generation import ReportGenerationService


class Command(BaseCommand):
    help = "Generate the report file for every succeeded check run that has none."

    def handle(self, *args: Any, **options: Any) -> None:  # noqa: ARG002
        service = ReportGenerationService()
        generated = 0
        failed = 0
        considered = 0

        for run in CheckRun.objects.missing_report().order_by("created_at").iterator():
            considered += 1
            result = service.generate(run.uuid)
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
