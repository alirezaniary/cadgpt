"""Running one check. The only module a Celery worker enters.

Idempotency is the contract. `acks_late` means a message survives a worker that dies
mid-task and is delivered again, so `execute` must reach the same end state whether it
runs once or five times:

- a run that is already terminal is returned untouched, because its result is final;
- a run that is PENDING or RUNNING is claimed under a row lock and executed.

Claiming a RUNNING run is deliberate, not an oversight. The only way a redelivery sees
RUNNING is that the worker holding it died -- Celery does not deliver a message to two
live workers at once, and the row lock serializes any overlap. Refusing to claim it would
leave the run stuck in RUNNING forever, which is exactly the state `reap_stalled_runs`
exists to clean up and which should not be created in the first place.

The evaluation itself happens outside the transaction. It takes seconds to minutes on a
real model, and holding a row lock and a database connection open for that would exhaust
the pool long before the queue.
"""

from __future__ import annotations

import uuid as uuid_lib
from pathlib import Path
from typing import cast

from cadgpt_engine import InvalidIdsError, InvalidIfcError, Report, run_check
from django.conf import settings
from django.db import transaction
from django.utils import timezone

from cadgpt.apps.base.exceptions import NotFoundError
from cadgpt.apps.base.services import BaseService
from cadgpt.apps.media.services import MediaService
from cadgpt.apps.review.choices import CheckRunFailure, CheckRunStatus
from cadgpt.apps.review.models import CheckRun


class CheckRunExecutor(BaseService):
    """Executes a check run to a terminal state. Safe to call twice with the same id."""

    def execute(self, run_uuid: uuid_lib.UUID | str) -> CheckRun:
        run = self._claim(run_uuid)
        if run.is_terminal:
            self.log.info(
                "check_run_already_terminal", run_id=str(run.uuid), status=run.status
            )
            return run

        log = self.log.bind(run_id=str(run.uuid), tenant_id=str(run.tenant.uuid))
        media = MediaService(tenant=run.tenant)

        try:
            with (
                media.local_path(run.review.model_file) as ifc_path,
                media.local_path(run.review.rule_set.source_file) as ids_path,
            ):
                report = self._evaluate(
                    ifc_path, ids_path, run.review.model_file.original_name
                )
        except InvalidIfcError as exc:
            return self._fail(run, CheckRunFailure.INVALID_MODEL, str(exc), log)
        except InvalidIdsError as exc:
            return self._fail(run, CheckRunFailure.INVALID_RULE_SET, str(exc), log)
        except Exception as exc:
            self._fail(run, CheckRunFailure.INTERNAL_ERROR, str(exc), log)
            # The user sees an honest failure; the worker still reports it as a failure so
            # it reaches the error tracker rather than being silently absorbed.
            raise

        return self._succeed(run, report, log)

    def _evaluate(self, ifc_path: Path, ids_path: Path, ifc_name: str) -> Report:
        return run_check(
            ifc_path,
            ids_path,
            entity_limit=settings.CHECK_ENTITY_LIMIT,
            ifc_name=ifc_name,
        )

    def _claim(self, run_uuid: uuid_lib.UUID | str) -> CheckRun:
        with transaction.atomic():
            run = (
                CheckRun.objects.select_for_update()
                .select_related(
                    "tenant", "review", "review__model_file", "review__rule_set"
                )
                .filter(uuid=run_uuid)
                .first()
            )
            if run is None:
                raise NotFoundError(f"No check run with uuid {run_uuid}.")
            if run.is_terminal:
                return cast("CheckRun", run)

            run.status = CheckRunStatus.RUNNING
            run.started_at = timezone.now()
            run.save(update_fields=["status", "started_at", "updated_at"])
        return cast("CheckRun", run)

    def _succeed(self, run: CheckRun, report: Report, log: object) -> CheckRun:
        run.status = CheckRunStatus.SUCCEEDED
        run.finished_at = timezone.now()
        run.report = report.to_dict()
        run.engine_version = report.engine_version
        run.outcome = report.status.value
        run.specifications_passed = report.specifications_passed
        run.specifications_failed = report.specifications_failed
        run.specifications_indeterminate = report.specifications_indeterminate
        run.passed = report.passed
        run.failed = report.failed
        run.indeterminate = report.indeterminate
        run.failure_reason = ""
        run.failure_detail = ""
        run.save()

        log.info(  # type: ignore[attr-defined]
            "check_run_succeeded",
            outcome=run.outcome,
            passed=run.passed,
            failed=run.failed,
            indeterminate=run.indeterminate,
            duration_seconds=run.duration_seconds,
        )
        return run

    def _fail(self, run: CheckRun, reason: str, detail: str, log: object) -> CheckRun:
        run.status = CheckRunStatus.FAILED
        run.finished_at = timezone.now()
        run.failure_reason = reason
        # Bounded: an ifcopenshell parse error can carry a very long fragment of the file.
        run.failure_detail = detail[:4000]
        run.save(
            update_fields=[
                "status",
                "finished_at",
                "failure_reason",
                "failure_detail",
                "updated_at",
            ]
        )
        log.warning("check_run_failed", reason=reason, detail=run.failure_detail[:200])  # type: ignore[attr-defined]
        return run

    def reap_stalled(self) -> int:
        """Fail runs whose worker died, so nothing sits in RUNNING forever.

        A stalled run left alone is worse than a failed one: it reads as work still in
        progress, and the review it belongs to refuses a new check because one is already
        in flight. That is a user permanently unable to re-check their model.
        """
        stalled = CheckRun.objects.stalled(settings.CHECK_RUN_STALL_SECONDS)
        count: int = stalled.update(
            status=CheckRunStatus.FAILED,
            finished_at=timezone.now(),
            failure_reason=CheckRunFailure.STALLED,
            failure_detail="The worker running this check stopped responding.",
            updated_at=timezone.now(),
        )
        if count:
            self.log.warning("stalled_check_runs_reaped", count=count)
        return count
