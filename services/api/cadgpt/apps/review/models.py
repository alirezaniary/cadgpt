"""A review holds the inputs; a check run holds one evaluation of them.

They are separate because the workflow is check, fix, re-check. A review that carried its
own result would lose every earlier one, and the second run would be worth less than the
first -- punishing exactly the loop the product exists to accelerate.

The report is stored as one JSON document rather than as a row per finding. A real rule
set against a real model produced 3,623 non-passing entities in a single specification;
that is a document to read, not a table to join. Findings become rows when they need
identity across runs -- when dispositions arrive -- and not before.
"""

from __future__ import annotations

from typing import Any, ClassVar

from django.db import models
from django.utils.translation import gettext_lazy as _

from cadgpt.apps.base.models import SoftDeleteModelMixin, UuidBaseModel
from cadgpt.apps.review.choices import (
    CheckRunFailure,
    CheckRunStatus,
    OutcomeStatus,
    ReportGenerationFailure,
)
from cadgpt.apps.review.repositories.custom_managers import CheckRunManager, ReviewManager
from cadgpt.apps.tenancy.models import TenantOwnedModel


class Review(TenantOwnedModel, SoftDeleteModelMixin, UuidBaseModel):
    """One model checked against a rule source, over as many runs as it takes.

    That source is either an uploaded `RuleSet` -- carried here, unchanged since before
    T-0031 -- or the shipped catalogue, selected per run rather than fixed on the review.
    `rule_set` is therefore nullable: a review with no `rule_set` names no rule source of
    its own, and each `CheckRun` beneath it must be given a catalogue selection when it is
    requested (`ReviewService.request_check`, `CheckRun.rule_pack_selection`). A review
    with a `rule_set` keeps working exactly as it always has -- that path is unchanged.
    """

    tenant_related_name = "reviews"

    name = models.CharField(_("name"), max_length=255)
    model_file = models.ForeignKey(
        "media.Media",
        on_delete=models.PROTECT,
        related_name="reviews",
        verbose_name=_("model file"),
    )
    rule_set = models.ForeignKey(
        "rulepack.RuleSet",
        on_delete=models.PROTECT,
        related_name="reviews",
        verbose_name=_("rule set"),
        null=True,
        blank=True,
    )
    created_by = models.ForeignKey(
        "account.User",
        on_delete=models.SET_NULL,
        null=True,
        related_name="created_reviews",
        verbose_name=_("created by"),
    )

    objects: ClassVar[ReviewManager] = ReviewManager()

    class Meta:
        verbose_name = _("review")
        verbose_name_plural = _("reviews")
        ordering = ("-created_at",)
        indexes = (models.Index(fields=("tenant", "-created_at")),)

    def __str__(self) -> str:
        return self.name


class CheckRun(TenantOwnedModel, UuidBaseModel):
    """One evaluation. Immutable once terminal.

    The tenant is carried here as well as on the review. It is denormalized on purpose:
    every tenant-scoped queryset filters on a `tenant` column of the table it reads, and a
    run that could only be scoped by joining its review is a run that will eventually be
    read without the join.
    """

    tenant_related_name = "check_runs"

    review = models.ForeignKey(
        Review, on_delete=models.CASCADE, related_name="runs", verbose_name=_("review")
    )
    status = models.CharField(
        _("status"),
        max_length=16,
        choices=CheckRunStatus.choices,
        default=CheckRunStatus.PENDING,
        db_index=True,
    )
    requested_by = models.ForeignKey(
        "account.User",
        on_delete=models.SET_NULL,
        null=True,
        related_name="requested_check_runs",
        verbose_name=_("requested by"),
    )

    task_id = models.CharField(_("task id"), max_length=255, blank=True, db_index=True)
    queued_at = models.DateTimeField(_("queued at"), null=True, blank=True)
    started_at = models.DateTimeField(_("started at"), null=True, blank=True)
    finished_at = models.DateTimeField(_("finished at"), null=True, blank=True)

    #: How many times `CheckRunExecutor._claim` has claimed this run -- incremented in the
    #: same row-locked write that flips the run to `RUNNING`, so it counts every attempt
    #: that actually started, including one a worker died on before it could finish. Once
    #: this reaches `settings.CHECK_RUN_MAX_CLAIMS`, `_claim` ends the run as
    #: `CheckRunFailure.RESOURCE_EXHAUSTED` instead of claiming it again (T-0033) --
    #: without this, `acks_late` redelivering a run whose worker was OOM-killed cycles it
    #: through the shared `checks` queue forever.
    claim_count = models.PositiveIntegerField(_("claim count"), default=0)

    # What produced this result. An old run stays explainable only if it says so itself.
    engine_version = models.CharField(_("engine version"), max_length=64, blank=True)
    model_checksum = models.CharField(_("model SHA-256"), max_length=64, blank=True)
    rule_set_checksum = models.CharField(_("rule set SHA-256"), max_length=64, blank=True)

    #: The catalogue selection this run was dispatched with, captured at that moment as
    #: plain data -- never a foreign key a later catalogue edit could redefine underneath
    #: an already-dispatched run. Empty for a run against `review.rule_set` (the existing
    #: single-upload path); one entry per selected pack otherwise, each carrying the
    #: pack's uuid, name, jurisdiction, region, version and a content hash. See
    #: `rulepack.services.RulePackService.snapshot` and `docs/decisions.md`.
    rule_pack_selection = models.JSONField(
        _("rule pack selection"), default=list, blank=True
    )

    outcome = models.CharField(
        _("outcome"),
        max_length=16,
        choices=OutcomeStatus.choices,
        blank=True,
        db_index=True,
    )

    # Denormalized so a list of runs needs no JSON parsing. These are the three counts
    # every summary states, and INDETERMINATE is never folded into passed.
    specifications_passed = models.PositiveIntegerField(
        _("specifications passed"), default=0
    )
    specifications_failed = models.PositiveIntegerField(
        _("specifications failed"), default=0
    )
    specifications_indeterminate = models.PositiveIntegerField(
        _("specifications indeterminate"), default=0
    )
    passed = models.PositiveIntegerField(_("elements passed"), default=0)
    failed = models.PositiveIntegerField(_("elements failed"), default=0)
    indeterminate = models.PositiveIntegerField(_("elements indeterminate"), default=0)

    report = models.JSONField(_("report"), null=True, blank=True)

    #: The generated Markdown report (T-0032), stored through `media.Media` under this
    #: run's tenant like any other file here. `SET_NULL` rather than `PROTECT`: unlike
    #: `Review.model_file`, this is a derived artifact the run can regenerate, not an
    #: input whose loss would make the run unexplainable. `None` until generation
    #: completes, which is also how `ReportGenerationService.generate` recognises a run
    #: it has not yet produced a file for -- see its idempotence contract.
    report_file = models.ForeignKey(
        "media.Media",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="generated_for_runs",
        verbose_name=_("report file"),
    )

    #: Set only when generation was attempted and failed for a reason a retry will not
    #: change -- today, only `MediaService`'s size cap rejecting the rendered file
    #: (`ReportGenerationFailure.TOO_LARGE`). Blank is what distinguishes "not generated
    #: yet, ask again" from "asked, and it cannot be produced" -- both `CheckRunQuerySet.
    #: missing_report` and the frontend (`docs/tasks/
    #: T-0051-a-report-that-failed-to-generate-can-be-recovered.md`) read this rather
    #: than inferring it from `report_file` being `None` alone, which both states share.
    #: The run itself is never retro-failed for this: see `docs/decisions.md`.
    report_generation_error = models.CharField(
        _("report generation error"),
        max_length=32,
        choices=ReportGenerationFailure.choices,
        blank=True,
    )
    #: The raw exception text behind `report_generation_error`, for an operator reading
    #: logs or the admin -- not translated, not sent to a client, exactly like
    #: `failure_detail` below.
    report_generation_detail = models.TextField(_("report generation detail"), blank=True)

    failure_reason = models.CharField(
        _("failure reason"), max_length=32, choices=CheckRunFailure.choices, blank=True
    )
    failure_detail = models.TextField(_("failure detail"), blank=True)

    objects: ClassVar[CheckRunManager] = CheckRunManager()

    class Meta:
        verbose_name = _("check run")
        verbose_name_plural = _("check runs")
        ordering = ("-created_at",)
        indexes = (
            models.Index(fields=("tenant", "status", "-created_at")),
            models.Index(fields=("review", "-created_at")),
        )
        constraints = (
            # A terminal run must say what it found or why it could not. A row that is
            # 'succeeded' with no report would read as a clean check of nothing.
            models.CheckConstraint(
                condition=(
                    ~models.Q(status=CheckRunStatus.SUCCEEDED)
                    | models.Q(report__isnull=False)
                ),
                name="succeeded_run_has_a_report",
            ),
            models.CheckConstraint(
                condition=(
                    ~models.Q(status=CheckRunStatus.FAILED) | ~models.Q(failure_reason="")
                ),
                name="failed_run_states_a_reason",
            ),
        )

    def __str__(self) -> str:
        return f"{self.review.name} - {self.status}"

    @property
    def is_terminal(self) -> bool:
        from cadgpt.apps.review.choices import TERMINAL_STATUSES

        return self.status in TERMINAL_STATUSES

    @property
    def duration_seconds(self) -> float | None:
        if self.started_at is None or self.finished_at is None:
            return None
        return (self.finished_at - self.started_at).total_seconds()

    def summary(self) -> dict[str, Any]:
        """The counts a summary states, with all three always present."""
        return {
            "passed": self.passed,
            "failed": self.failed,
            "indeterminate": self.indeterminate,
            "specifications_passed": self.specifications_passed,
            "specifications_failed": self.specifications_failed,
            "specifications_indeterminate": self.specifications_indeterminate,
        }
