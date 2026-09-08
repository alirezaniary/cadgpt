"""Creating a review and asking for it to be checked."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from cadgpt.apps.account.models import User
from cadgpt.apps.base.exceptions import ConflictError, ValidationError
from cadgpt.apps.base.services import BaseTenantAwareService
from cadgpt.apps.media.choices import MediaKind
from cadgpt.apps.media.models import Media
from cadgpt.apps.project.models import Project
from cadgpt.apps.review.choices import CheckRunFailure, CheckRunStatus
from cadgpt.apps.review.models import CheckRun, Review
from cadgpt.apps.review.repositories.querysets import CheckRunQuerySet
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
        project: Project,
        rule_set: RuleSet | None = None,
        created_by: User | None = None,
    ) -> Review:
        if model_file.kind != MediaKind.IFC_MODEL:
            raise ValidationError(_("That file was not uploaded as a model."))
        if (
            model_file.tenant_id != self.tenant.pk
            or project.tenant_id != self.tenant.pk
            or (rule_set is not None and rule_set.tenant_id != self.tenant.pk)
        ):
            # Unreachable through the API, which resolves all three through tenant-scoped
            # querysets. Asserted here because this service is also called from a
            # management command and a task, where nothing else checks.
            raise ValidationError(
                _("The model, the project and the rule set must belong to this workspace.")
            )

        review = Review.objects.create_review(
            tenant=self.tenant,
            name=name,
            model_file=model_file,
            project=project,
            rule_set=rule_set,
            created_by=created_by,
        )
        self.log.info(
            "review_created", review_id=str(review.uuid), project_id=str(project.uuid)
        )
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

        The same race has a worse failure mode one step earlier: if the process dies
        between `COMMIT` and the `on_commit` callback firing -- or the callback fires and
        `.delay()` itself raises because the broker is unreachable -- `_dispatch` never
        runs at all, and the run it would have queued sits `PENDING` forever with no
        `task_id`. Because `MAX_IN_FLIGHT_RUNS` counts that row, it then blocks every
        future call here too. `_reap_lost_dispatch` is the reactive half of the self-heal:
        it runs when this method is about to refuse, looks for exactly that shape of row,
        and fails it so the request below can proceed -- the user's way out is asking
        again, not a separate recovery action. `CheckRunExecutor.reap_lost_dispatch`
        (T-0085) is the proactive half, run from Celery beat, so the row is usually already
        gone before anyone retries. See `docs/tasks/
        T-0056-a-lost-check-dispatch-kills-the-review.md` and `docs/tasks/
        T-0085-the-lost-dispatch-recovery-is-blind-until-someone-asks.md`.
        """
        from cadgpt.apps.review.tasks import execute_check_run

        review_runs: CheckRunQuerySet = CheckRun.objects.for_tenant(self.tenant).for_review(
            review.pk
        )
        if review_runs.in_flight().count() >= self.MAX_IN_FLIGHT_RUNS:
            self._reap_lost_dispatch(review_runs)
            if review_runs.in_flight().count() >= self.MAX_IN_FLIGHT_RUNS:
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

    def _reap_lost_dispatch(self, runs: CheckRunQuerySet) -> int:
        """Fail a `PENDING` run in `runs` whose dispatch was lost, so it stops blocking.

        Called only from `request_check`, only at the moment it is about to refuse a new
        check -- this method itself is never a periodic sweep. `CheckRunExecutor.
        reap_lost_dispatch` (T-0085) is a second, independent caller of the same
        `CheckRunQuerySet.dispatch_lost` UPDATE, run from Celery beat on the same cadence
        as the RUNNING-side sweep -- so a lost dispatch no longer depends on this method
        ever running at all. What actually keeps *this* method safe is not being the only
        caller; it is that `CheckRunQuerySet.dispatch_lost` already limits its match to a
        run old enough that a live dispatch would certainly have set `task_id` by now
        (`settings.CHECK_RUN_STALL_SECONDS`), so nothing here -- called reactively or from
        beat -- fails a run that is merely waiting behind a busy queue.

        Re-dispatching instead of failing was considered and rejected. `CheckRunExecutor.
        execute` is documented idempotent for a *redelivered* Celery message, but that
        relies on Celery's own guarantee that a message is never live on two workers at
        once (`execution.py`'s docstring on `_claim`). A *second, independently issued*
        `task.delay()` call for the same run carries no such guarantee: if the original
        dispatch actually reached the broker and only the follow-up write of `task_id` was
        lost -- a narrower race than the one this method exists for, but a real one --
        `_claim`'s row lock would serialize the two attempts rather than reject the second,
        and both would go on to evaluate the same model concurrently. Failing the row
        instead costs the one result that attempt would have produced; the caller asks
        again, at the price of one more request, rather than this method risking a model
        checked twice at once.

        A single filtered `UPDATE`, not select-then-save: `runs.dispatch_lost(...)` is
        re-evaluated by Postgres against the current row at the moment of the write, the
        same pattern `reap_stalled` already uses (`execution.py`). A `SELECT` into Python
        objects followed by per-row `.save()` would reopen exactly the race this method
        exists to close -- a worker claiming the row (`_claim` flips it to `RUNNING`)
        between the read and the write would have its `RUNNING` row overwritten back to
        `FAILED` out from under it, and the caller below would then dispatch a second,
        genuinely concurrent evaluation of the same review.
        """
        count = runs.dispatch_lost(settings.CHECK_RUN_STALL_SECONDS).update(
            status=CheckRunStatus.FAILED,
            finished_at=timezone.now(),
            failure_reason=CheckRunFailure.DISPATCH_LOST,
            failure_detail=str(
                _(
                    "This check was requested but its dispatch never reached a worker, "
                    "so it was ended. Request the check again."
                )
            ),
            updated_at=timezone.now(),
        )
        if count:
            self.log.warning("check_run_dispatch_lost_reaped", count=count)
        return count

    def _dispatch(self, run: CheckRun, task: object) -> None:
        async_result = task.delay(str(run.uuid))  # type: ignore[attr-defined]
        CheckRun.objects.filter(pk=run.pk).update(
            task_id=async_result.id, queued_at=timezone.now()
        )
