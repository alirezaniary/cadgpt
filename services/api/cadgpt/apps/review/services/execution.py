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
from collections.abc import Sequence
from pathlib import Path
from typing import Any, cast

from cadgpt_engine import InvalidIdsError, InvalidIfcError, Report, Status, run_check
from django.conf import settings
from django.db import transaction
from django.utils import timezone

from cadgpt.apps.base.exceptions import NotFoundError
from cadgpt.apps.base.services import BaseService
from cadgpt.apps.media.services import MediaService
from cadgpt.apps.review.choices import CheckRunFailure, CheckRunStatus
from cadgpt.apps.review.models import CheckRun
from cadgpt.apps.rulepack.models import RulePack
from cadgpt.apps.rulepack.services import RulePackService


class RulePackCitationMismatchError(Exception):
    """A cited pack's bytes no longer match the checksum this run recorded at dispatch.

    T-0031's review (F1): the citation `CheckRun.rule_pack_selection` stores existed
    without anything ever comparing it against what actually got evaluated -- the column
    recorded a fact nothing enforced. This is that enforcement's failure mode, raised
    from `CheckRunExecutor._evaluate_selection` and mapped to
    `CheckRunFailure.RULE_PACK_MODIFIED` in `CheckRunExecutor.execute`, never silently
    absorbed into evaluating whatever bytes are behind the uuid right now.
    """


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
        ifc_name = run.review.model_file.original_name

        try:
            with media.local_path(run.review.model_file) as ifc_path:
                rule_set = run.review.rule_set
                if rule_set is not None:
                    with media.local_path(rule_set.source_file) as ids_path:
                        report = self._evaluate(ifc_path, ids_path, ifc_name)
                else:
                    report = self._evaluate_selection(
                        ifc_path, run.rule_pack_selection, ifc_name, log
                    )
        except InvalidIfcError as exc:
            return self._fail(run, CheckRunFailure.INVALID_MODEL, str(exc), log)
        except InvalidIdsError as exc:
            return self._fail(run, CheckRunFailure.INVALID_RULE_SET, str(exc), log)
        except RulePackCitationMismatchError as exc:
            return self._fail(run, CheckRunFailure.RULE_PACK_MODIFIED, str(exc), log)
        except Exception as exc:
            self._fail(run, CheckRunFailure.INTERNAL_ERROR, str(exc), log)
            # The user sees an honest failure; the worker still reports it as a failure so
            # it reaches the error tracker rather than being silently absorbed.
            raise

        return self._succeed(run, report, log)

    def _evaluate_selection(
        self,
        ifc_path: Path,
        selection: Sequence[dict[str, Any]],
        ifc_name: str,
        log: Any,
    ) -> Report:
        """One model against every pack in the selection, combined into one report.

        Each pack is a separate `run_check` call -- the engine takes one IDS file per
        call and stays exactly as it is; see `docs/tasks/
        T-0031-rule-selection-on-the-run.md`, "the engine ... must not learn what a
        RulePack is". `_combine_reports` is where the several results become one, so the
        run's coverage sentence counts across the whole selection rather than resetting
        per pack.

        Packs are re-fetched by uuid rather than trusted from `selection` alone: the
        selection is this run's *citation*, captured once at dispatch time, but the bytes
        to actually check against still have to be read from the catalogue as it exists
        right now. **The citation is then verified, not merely trusted**: T-0031's review
        (F1) found that a run stored a checksum nothing ever compared against anything,
        so bytes swapped in behind a cited uuid between dispatch and execution would be
        evaluated and reported on as if they were what was cited. No in-repo path can do
        that today -- every seeded pack is immutable (T-0030) -- but the guarantee this
        task exists to make now holds by construction rather than by nothing happening to
        exploit it.
        """
        packs = {
            str(pack.uuid): pack
            for pack in RulePack.objects.selected(entry["uuid"] for entry in selection)
        }
        pack_service = RulePackService()

        reports: list[Report] = []
        for entry in selection:
            pack = packs.get(entry["uuid"])
            if pack is None:
                raise InvalidIdsError(
                    f"Rule pack {entry['uuid']} ({entry['name']}) cited by this run is "
                    "no longer in the catalogue."
                )
            actual_checksum = pack_service.checksum_of(pack)
            if actual_checksum != entry["checksum_sha256"]:
                raise RulePackCitationMismatchError(
                    f"Rule pack {entry['uuid']} ({entry['name']}) was cited with "
                    f"checksum {entry['checksum_sha256']} at dispatch, but its file now "
                    f"hashes to {actual_checksum}. Refusing to evaluate a rule this run "
                    "did not actually cite."
                )
            with pack_service.local_path(pack) as ids_path:
                report = self._evaluate(ifc_path, ids_path, ifc_name)
            reports.append(report)
            # F2 (T-0031's review): logged beside the citation is what the produced
            # report actually calls itself -- its own `ids_title` and the names of the
            # specifications it evaluated -- built from `report`, never from `entry`.
            # A line built only from the citation can only ever agree with the
            # citation; this one can disagree with it, which is the only thing that
            # makes it evidence the check ran against the cited rules rather than a
            # restatement of what was asked for.
            log.info(
                "check_run_pack_evaluated",
                rule_pack_id=entry["uuid"],
                cited_name=entry["name"],
                cited_jurisdiction=entry["jurisdiction"],
                cited_version=entry["version"],
                cited_checksum=entry["checksum_sha256"],
                evaluated_ids_title=report.ids_title,
                evaluated_specification_names=[s.name for s in report.specifications],
                specifications_passed=report.specifications_passed,
                specifications_failed=report.specifications_failed,
                specifications_indeterminate=report.specifications_indeterminate,
            )

        return _combine_reports(reports)

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
                # `of=("self",)` restricts the row lock to `check_run` itself. Postgres
                # refuses a plain `FOR UPDATE` across `review__rule_set`, now nullable
                # (T-0031): that join is a LEFT OUTER JOIN, and "FOR UPDATE cannot be
                # applied to the nullable side of an outer join" is a real error, not a
                # theoretical one -- sqlite (the test settings' backend) never enforces
                # it, so only the real path caught this.
                CheckRun.objects.select_for_update(of=("self",))
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
        # T-0032: the Markdown report file is generated from this exact result, so its
        # dispatch is wrapped in the same transaction the save commits with. `on_commit`
        # is load-bearing here for the reason `ReviewService.request_check` documents for
        # `execute_check_run`'s own dispatch -- enqueuing before this row is visible to
        # another connection would let a worker pick the message up and find a run that
        # is not SUCCEEDED yet.
        from cadgpt.apps.review.tasks import generate_report_file

        with transaction.atomic():
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
            transaction.on_commit(lambda: generate_report_file.delay(str(run.uuid)))

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


def _status_from_counts(passed: int, failed: int, indeterminate: int) -> Status:
    """A known violation decides FAIL; otherwise an unknown prevents PASS.

    Mirrors `cadgpt_engine.check._aggregate` exactly -- that function is private to the
    engine and this combinator lives here, not there, because it operates across several
    already-produced `Report`s and the engine must not learn what a `RulePack` selection
    is. The rule itself does not belong to `RulePack` at all, though: it is the same
    three-valued aggregation `run_check` already applies to its own specification counts,
    so keeping the two in sync is a matter of not changing one without the other, not a
    new decision made here.
    """
    if failed:
        return Status.FAIL
    if indeterminate:
        return Status.INDETERMINATE
    if passed:
        return Status.PASS
    return Status.INDETERMINATE


def _combine_reports(reports: Sequence[Report]) -> Report:
    """Several packs' reports, against the same model, as one.

    Concatenating every selected pack's specifications into one list -- rather than
    keeping one report per pack -- is the deliberate choice `docs/tasks/
    T-0031-rule-selection-on-the-run.md` calls out: a selection of several packs is one
    run with several rule sources, not several runs. `report.specifications` is what the
    coverage sentence ("N of M specifications evaluated") is computed from downstream
    (`services/web/src/components/ReportView.tsx`), so this is also what makes that count
    span the whole selection instead of resetting per pack. See `docs/decisions.md`.
    """
    specifications = tuple(spec for report in reports for spec in report.specifications)
    specifications_passed = sum(r.specifications_passed for r in reports)
    specifications_failed = sum(r.specifications_failed for r in reports)
    specifications_indeterminate = sum(r.specifications_indeterminate for r in reports)
    passed = sum(r.passed for r in reports)
    failed = sum(r.failed for r in reports)
    indeterminate = sum(r.indeterminate for r in reports)

    first = reports[0]
    # Each pack's own `<ids:title>`; several packs, no single title, so the selection is
    # named by all of them rather than inventing a collective one. `dict.fromkeys` keeps
    # first-seen order while dropping repeats and blanks.
    ids_title = "; ".join(dict.fromkeys(r.ids_title for r in reports if r.ids_title))

    return Report(
        ifc_filename=first.ifc_filename,
        ifc_schema=first.ifc_schema,
        ids_title=ids_title,
        engine_version=first.engine_version,
        status=_status_from_counts(
            specifications_passed, specifications_failed, specifications_indeterminate
        ),
        specifications_passed=specifications_passed,
        specifications_failed=specifications_failed,
        specifications_indeterminate=specifications_indeterminate,
        passed=passed,
        failed=failed,
        indeterminate=indeterminate,
        specifications=specifications,
    )
