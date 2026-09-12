"""T-0048's fix-now round (F4): tests for the three failure-classification fixes that
shipped with no coverage of their own.

No mocks except where the fix's whole point is distinguishing one exception type from
another (F2's second case, where the real S3 exception is not worth reproducing here) --
everything else is a real seeded pack, a real deleted file, a real `CheckRunExecutor`.
"""

from __future__ import annotations

from typing import Any

import pytest
import structlog.testing

from cadgpt.apps.review.choices import CheckRunFailure, CheckRunStatus
from cadgpt.apps.review.models import CheckRun, Review
from cadgpt.apps.review.services.execution import CheckRunExecutor
from cadgpt.apps.rulepack.models import RulePack
from cadgpt.apps.rulepack.services import RulePackService
from cadgpt.apps.tenancy.models import Tenant

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


def test_a_run_with_no_rule_set_and_no_selection_fails_named_not_crashed(
    catalogue_review: Review, owner: Any
) -> None:
    """The empty-selection guard in `_evaluate_selection`.

    Reachable only from `CheckRun.objects.create_run` directly -- `_resolve_selection`
    already refuses this at request time and is unchanged -- but a run built this way
    must still end named, not with `_combine_reports([])`'s `IndexError` leaking
    "list index out of range" to the tenant as `internal_error`.

    Mutation-proof: commenting out the `if not selection: raise InvalidIdsError(...)`
    guard in `execution.py` and re-running this test reproduces exactly that -- an
    unhandled `IndexError: list index out of range` from `_combine_reports`, not this
    assertion failing gracefully. Confirmed by hand before this test was left in place;
    see the task's Evidence section for the transcript.
    """
    run = CheckRun.objects.create_run(
        review=catalogue_review, requested_by=owner, rule_pack_selection=[]
    )

    executed = CheckRunExecutor().execute(run.uuid)

    assert executed.status == CheckRunStatus.FAILED
    assert executed.failure_reason == CheckRunFailure.INVALID_RULE_SET
    assert executed.report is None
    assert "index" not in executed.failure_detail.lower()


def test_a_missing_pack_file_is_classified_honestly_without_the_storage_path(
    catalogue_review: Review, rule_pack: RulePack, owner: Any, tenant: Tenant
) -> None:
    """F2: a pack row present, its bytes gone from storage -- classified `invalid_rule_set`,
    naming the pack, never the storage key, and the original exception is logged with its
    traceback before being mapped to that sentence.
    """
    pack_service = RulePackService()
    citation = pack_service.snapshot(rule_pack)
    run = CheckRun.objects.create_run(
        review=catalogue_review, requested_by=owner, rule_pack_selection=[citation]
    )

    storage = rule_pack.source_file.storage
    name = rule_pack.source_file.name
    assert name is not None
    storage.delete(name)

    with structlog.testing.capture_logs() as captured:
        executed = CheckRunExecutor().execute(run.uuid)

    assert executed.status == CheckRunStatus.FAILED
    assert executed.failure_reason == CheckRunFailure.INVALID_RULE_SET
    assert executed.report is None
    assert rule_pack.name in executed.failure_detail
    # Neither the storage key nor its directory prefix ever reaches the tenant.
    assert name not in executed.failure_detail
    assert "rule-packs" not in executed.failure_detail
    assert ".ids" not in executed.failure_detail

    # The operator-side signal F2 requires: the original exception, logged before it was
    # mapped to the tenant's sentence, with its traceback attached.
    unreadable_events = [e for e in captured if e["event"] == "check_run_pack_unreadable"]
    assert unreadable_events, captured
    assert unreadable_events[0]["rule_pack_id"] == str(rule_pack.uuid)
    assert unreadable_events[0].get("exc_info"), unreadable_events[0]


def test_a_transient_storage_error_is_not_swallowed_as_invalid_rule_set(
    catalogue_review: Review,
    rule_pack: RulePack,
    owner: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """F2's other half: a genuine operator-side fault -- simulated here as a
    `ConnectionError`, one of the two classes `execute_check_run`'s `autoretry_for` exists
    to retry -- must not be relabeled `invalid_rule_set`. It must reach `execute`'s
    `except Exception` branch instead: classified `internal_error` and re-raised, so
    Celery's retry policy still sees it.

    Mutation-proof: widening the guard in `execution.py` back to a bare `except OSError`
    (an ancestor of `ConnectionError`) makes this test fail -- the run would be classified
    `invalid_rule_set` and `execute` would return normally instead of raising. Confirmed
    by hand before this test was left in place; see the task's Evidence section.
    """
    pack_service = RulePackService()
    citation = pack_service.snapshot(rule_pack)
    run = CheckRun.objects.create_run(
        review=catalogue_review, requested_by=owner, rule_pack_selection=[citation]
    )

    def _transient_failure(self: RulePackService, pack: RulePack) -> str:
        raise ConnectionError("simulated transient storage blip")

    monkeypatch.setattr(RulePackService, "checksum_of", _transient_failure)

    with pytest.raises(ConnectionError):
        CheckRunExecutor().execute(run.uuid)

    run.refresh_from_db()
    assert run.status == CheckRunStatus.FAILED
    assert run.failure_reason == CheckRunFailure.INTERNAL_ERROR
