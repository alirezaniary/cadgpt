"""Creating a review and asking for it to be checked."""

from __future__ import annotations

from django.db import transaction
from django.utils.translation import gettext_lazy as _

from cadgpt.apps.account.models import User
from cadgpt.apps.base.exceptions import ConflictError, ValidationError
from cadgpt.apps.base.services import BaseTenantAwareService
from cadgpt.apps.media.choices import MediaKind
from cadgpt.apps.media.models import Media
from cadgpt.apps.review.models import CheckRun, Review
from cadgpt.apps.rulepack.models import RuleSet


class ReviewService(BaseTenantAwareService):
    """The tenant-facing operations on a review."""

    #: One review may not have several checks in flight at once. A second would consume a
    #: worker to produce a result identical to the first, and the two would race to write
    #: the same review's newest result.
    MAX_IN_FLIGHT_RUNS = 1

    def create(
        self,
        *,
        name: str,
        model_file: Media,
        rule_set: RuleSet,
        created_by: User | None = None,
    ) -> Review:
        if model_file.kind != MediaKind.IFC_MODEL:
            raise ValidationError(_("That file was not uploaded as a model."))
        if model_file.tenant_id != self.tenant.pk or rule_set.tenant_id != self.tenant.pk:
            # Unreachable through the API, which resolves both through tenant-scoped
            # querysets. Asserted here because this service is also called from a
            # management command and a task, where nothing else checks.
            raise ValidationError(
                _("The model and the rule set must belong to this workspace.")
            )

        review = Review.objects.create_review(
            tenant=self.tenant,
            name=name,
            model_file=model_file,
            rule_set=rule_set,
            created_by=created_by,
        )
        self.log.info("review_created", review_id=str(review.uuid))
        return review

    def request_check(
        self, *, review: Review, requested_by: User | None = None
    ) -> CheckRun:
        """Create a run and hand it to a worker after the transaction commits.

        `on_commit` is load-bearing. Enqueuing inside the transaction lets a worker pick
        the message up before the row it names is visible to any other connection, and the
        task then fails to find a run that certainly exists. This is the classic
        dual-write race, and the ordering here is the whole fix.
        """
        from cadgpt.apps.review.tasks import execute_check_run

        in_flight = (
            CheckRun.objects.for_tenant(self.tenant).for_review(review.pk).in_flight()
        )
        if in_flight.count() >= self.MAX_IN_FLIGHT_RUNS:
            raise ConflictError(_("A check is already running for this review."))

        with transaction.atomic():
            run = CheckRun.objects.create_run(review=review, requested_by=requested_by)
            transaction.on_commit(lambda: self._dispatch(run, execute_check_run))

        self.log.info("check_requested", run_id=str(run.uuid), review_id=str(review.uuid))
        return run

    def _dispatch(self, run: CheckRun, task: object) -> None:
        from django.utils import timezone

        async_result = task.delay(str(run.uuid))  # type: ignore[attr-defined]
        CheckRun.objects.filter(pk=run.pk).update(
            task_id=async_result.id, queued_at=timezone.now()
        )
