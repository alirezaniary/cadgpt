"""Creating a review and asking for it to be checked."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from django.db import transaction
from django.utils.translation import gettext_lazy as _

from cadgpt.apps.account.models import User
from cadgpt.apps.base.exceptions import ConflictError, ValidationError
from cadgpt.apps.base.services import BaseTenantAwareService
from cadgpt.apps.media.choices import MediaKind
from cadgpt.apps.media.models import Media
from cadgpt.apps.review.models import CheckRun, Review
from cadgpt.apps.rulepack.models import RulePack, RuleSet
from cadgpt.apps.rulepack.services import RulePackService


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
        rule_set: RuleSet | None = None,
        created_by: User | None = None,
    ) -> Review:
        if model_file.kind != MediaKind.IFC_MODEL:
            raise ValidationError(_("That file was not uploaded as a model."))
        if model_file.tenant_id != self.tenant.pk or (
            rule_set is not None and rule_set.tenant_id != self.tenant.pk
        ):
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
        self,
        *,
        review: Review,
        requested_by: User | None = None,
        rule_pack_uuids: Sequence[str] = (),
    ) -> CheckRun:
        """Create a run and hand it to a worker after the transaction commits.

        `rule_pack_uuids` is the catalogue selection for this run, meaningful only when
        `review.rule_set` is unset -- see `_resolve_selection`, which is where an unknown
        or ambiguous pack is refused before anything is created.

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

        selection = self._resolve_selection(review=review, rule_pack_uuids=rule_pack_uuids)

        with transaction.atomic():
            run = CheckRun.objects.create_run(
                review=review, requested_by=requested_by, rule_pack_selection=selection
            )
            transaction.on_commit(lambda: self._dispatch(run, execute_check_run))

        self.log.info(
            "check_requested",
            run_id=str(run.uuid),
            review_id=str(review.uuid),
            rule_packs=[entry["uuid"] for entry in selection],
        )
        return run

    def _resolve_selection(
        self, *, review: Review, rule_pack_uuids: Sequence[str]
    ) -> list[dict[str, Any]]:
        """Turn the requested pack uuids into the self-contained citation the run stores.

        Refuses rather than silently narrowing: a pack that does not exist in the
        catalogue, or the same pack named twice (ambiguous -- which one was meant, and
        would it be run once or double-counted?), fails the whole request instead of
        running against whatever subset did resolve. That refusal is the coverage
        guarantee this task exists for; see
        `docs/tasks/T-0031-rule-selection-on-the-run.md`.
        """
        if review.rule_set_id is not None:
            if rule_pack_uuids:
                raise ValidationError(
                    _(
                        "This review already checks against an uploaded rule set; it "
                        "cannot also select packs from the catalogue."
                    )
                )
            return []

        if not rule_pack_uuids:
            raise ValidationError(
                _(
                    "This review has no uploaded rule set. Select at least one rule "
                    "pack from the catalogue to check against."
                )
            )

        requested = [str(uuid) for uuid in rule_pack_uuids]
        seen: set[str] = set()
        duplicates: set[str] = set()
        for uuid in requested:
            if uuid in seen:
                duplicates.add(uuid)
            seen.add(uuid)
        if duplicates:
            raise ValidationError(
                _(
                    "The same rule pack was selected more than once, which is "
                    "ambiguous: %(uuids)s."
                )
                % {"uuids": ", ".join(sorted(duplicates))}
            )

        packs = {str(pack.uuid): pack for pack in RulePack.objects.selected(seen)}
        missing = seen - packs.keys()
        if missing:
            raise ValidationError(
                _("Unknown rule pack: %(uuids)s.") % {"uuids": ", ".join(sorted(missing))}
            )

        pack_service = RulePackService()
        return [pack_service.snapshot(packs[uuid]) for uuid in requested]

    def _dispatch(self, run: CheckRun, task: object) -> None:
        from django.utils import timezone

        async_result = task.delay(str(run.uuid))  # type: ignore[attr-defined]
        CheckRun.objects.filter(pk=run.pk).update(
            task_id=async_result.id, queued_at=timezone.now()
        )
