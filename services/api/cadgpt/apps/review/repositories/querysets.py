from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING, Self

from django.utils import timezone

from cadgpt.apps.base.querysets import TenantScopedQuerySet
from cadgpt.apps.review.choices import TERMINAL_STATUSES, CheckRunStatus

if TYPE_CHECKING:
    # Imported for the quoted type parameter on the queryset below, which ruff
    # does not read as a use. Importing at runtime would be a cycle: the model
    # module imports the manager, which imports this one.
    from cadgpt.apps.review.models import CheckRun, Review  # noqa: F401


class ReviewQuerySet(TenantScopedQuerySet["Review"]):
    def alive(self) -> Self:
        return self.filter(deleted_at__isnull=True)

    def with_inputs(self) -> Self:
        return self.select_related(
            "model_file", "rule_set", "rule_set__source_file", "created_by"
        )

    def with_latest_run(self) -> Self:
        return self.prefetch_related("runs")

    def for_rule_set(self, rule_set_id: int) -> Self:
        return self.filter(rule_set_id=rule_set_id)


class CheckRunQuerySet(TenantScopedQuerySet["CheckRun"]):
    def pending(self) -> Self:
        return self.filter(status=CheckRunStatus.PENDING)

    def running(self) -> Self:
        return self.filter(status=CheckRunStatus.RUNNING)

    def terminal(self) -> Self:
        return self.filter(status__in=TERMINAL_STATUSES)

    def in_flight(self) -> Self:
        return self.exclude(status__in=TERMINAL_STATUSES)

    def for_review(self, review_id: int) -> Self:
        return self.filter(review_id=review_id)

    def with_inputs(self) -> Self:
        return self.select_related(
            "review",
            "review__model_file",
            "review__rule_set",
            "review__rule_set__source_file",
        )

    def without_report(self) -> Self:
        """List views never need the report document, which can be megabytes."""
        return self.defer("report")

    def missing_report(self) -> Self:
        """Succeeded, but no report file was ever produced -- eligible for recovery.

        Never includes a run whose generation permanently failed
        (`CheckRun.report_generation_error` set): that raises the same terminal outcome
        on every retry (`ReportGenerationFailure`), so a blind sweep over this set would
        just restate the same rejection forever. This is the set that is actually
        silently stuck -- pre-T-0032 runs, and any run whose `on_commit` dispatch or
        `.delay()` was lost. See `docs/tasks/
        T-0051-a-report-that-failed-to-generate-can-be-recovered.md`.
        """
        return self.filter(
            status=CheckRunStatus.SUCCEEDED,
            report_file_id__isnull=True,
            report_generation_error="",
        )

    def stalled(self, older_than_seconds: int) -> Self:
        """Started, never finished, and past the point where a live worker would have.

        Not merely old: a run that is still PENDING is waiting for a worker, which is a
        queue depth problem rather than a dead one.
        """
        cutoff = timezone.now() - timedelta(seconds=older_than_seconds)
        return self.filter(status=CheckRunStatus.RUNNING, started_at__lt=cutoff)
