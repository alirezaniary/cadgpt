"""Selecting rule packs from the catalogue at check-request time (T-0031).

No mocks: real fixture IDS files, the real engine, the real HTTP stack. The three fixture
packs below are the same ones `manage.py seed_rule_packs` ships, seeded here directly
through `RulePackService` so each test controls exactly which packs exist.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from cadgpt_engine import run_check
from django.core.files.base import ContentFile
from rest_framework.test import APIClient

from cadgpt.apps.review.choices import CheckRunFailure, CheckRunStatus
from cadgpt.apps.review.models import CheckRun, Review
from cadgpt.apps.review.services import ReviewService
from cadgpt.apps.review.services.execution import CheckRunExecutor
from cadgpt.apps.rulepack.models import RulePack
from cadgpt.apps.rulepack.services import RulePackService
from cadgpt.apps.tenancy.models import Tenant

pytestmark = [pytest.mark.django_db, pytest.mark.integration]

ENGINE_FIXTURES = (
    Path(__file__).resolve().parents[6] / "packages" / "engine" / "tests" / "fixtures"
)
DOOR_WIDTH_IDS = ENGINE_FIXTURES / "door_width.ids"
DOOR_NAME_IDS = ENGINE_FIXTURES / "door_name_recorded.ids"
DOOR_PROHIBITED_IDS = ENGINE_FIXTURES / "door_prohibited.ids"
THREE_DOORS_IFC = ENGINE_FIXTURES / "three_doors.ifc"


def _seed(ids_path: Path, *, version: str = "0.1") -> RulePack:
    pack, _ = RulePackService().seed(
        ids_path=ids_path,
        jurisdiction="sample",
        region="",
        version=version,
        source_citation="test fixture, seeded for the test suite; not a real regulation.",
    )
    return pack


@pytest.fixture
def door_width_pack(db: Any) -> RulePack:
    return _seed(DOOR_WIDTH_IDS)


@pytest.fixture
def door_name_pack(db: Any) -> RulePack:
    return _seed(DOOR_NAME_IDS)


@pytest.fixture
def door_prohibited_pack(db: Any) -> RulePack:
    return _seed(DOOR_PROHIBITED_IDS)


def test_a_run_created_with_a_catalogue_selection_records_which_packs_it_cites(
    api: APIClient,
    catalogue_review: Review,
    door_width_pack: RulePack,
    door_name_pack: RulePack,
    commit: Any,
) -> None:
    """Item 1: the run record names exactly the packs and versions it was asked for."""
    with commit():
        queued = api.post(
            f"/api/v1/reviews/{catalogue_review.uuid}/check/",
            {"rule_packs": [str(door_width_pack.uuid), str(door_name_pack.uuid)]},
            format="json",
        )
    assert queued.status_code == 202, queued.data

    run_uuid = queued.data["uuid"]
    detail = api.get(f"/api/v1/reviews/{catalogue_review.uuid}/runs/{run_uuid}/")
    assert detail.status_code == 200

    selection = detail.data["rule_pack_selection"]
    assert {entry["uuid"] for entry in selection} == {
        str(door_width_pack.uuid),
        str(door_name_pack.uuid),
    }
    by_uuid = {entry["uuid"]: entry for entry in selection}
    assert by_uuid[str(door_width_pack.uuid)]["version"] == "0.1"
    assert by_uuid[str(door_width_pack.uuid)]["jurisdiction"] == "sample"
    assert by_uuid[str(door_width_pack.uuid)]["name"] == "Accessible door width"
    assert by_uuid[str(door_width_pack.uuid)]["checksum_sha256"]


def test_the_check_actually_executes_against_every_selected_pack(
    catalogue_review: Review,
    door_width_pack: RulePack,
    door_name_pack: RulePack,
    door_prohibited_pack: RulePack,
    owner: Any,
    tenant: Tenant,
    commit: Any,
) -> None:
    """Item 2: the run's counts are the real engine's, summed across the whole selection.

    Each pack is run through the same engine entry point independently for the expected
    numbers, then compared against what the executor produced for the combined run --
    the same real IFC, the same real IDS files, no mock anywhere in the comparison.
    """
    expected = [
        run_check(THREE_DOORS_IFC, DOOR_WIDTH_IDS),
        run_check(THREE_DOORS_IFC, DOOR_NAME_IDS),
        run_check(THREE_DOORS_IFC, DOOR_PROHIBITED_IDS),
    ]

    with commit():
        run = ReviewService(tenant=tenant).request_check(
            review=catalogue_review,
            requested_by=owner,
            rule_pack_uuids=[
                str(door_width_pack.uuid),
                str(door_name_pack.uuid),
                str(door_prohibited_pack.uuid),
            ],
        )
    run.refresh_from_db()

    assert run.status == CheckRunStatus.SUCCEEDED
    assert run.specifications_passed == sum(r.specifications_passed for r in expected)
    assert run.specifications_failed == sum(r.specifications_failed for r in expected)
    assert run.specifications_indeterminate == sum(
        r.specifications_indeterminate for r in expected
    )
    assert run.passed == sum(r.passed for r in expected)
    assert run.failed == sum(r.failed for r in expected)
    assert run.indeterminate == sum(r.indeterminate for r in expected)

    # F1: "N of M specifications evaluated" must count across the whole selection -- the
    # combined report carries every pack's specification, not just the last pack's.
    assert run.report is not None
    assert len(run.report["specifications"]) == sum(len(r.specifications) for r in expected)
    names = {spec["name"] for spec in run.report["specifications"]}
    assert names == {
        "Minimum clear door width 900 mm",
        "Door name recorded",
        "No doors permitted",
    }


def test_an_unknown_pack_is_refused_not_silently_dropped(
    api: APIClient, catalogue_review: Review, door_width_pack: RulePack, commit: Any
) -> None:
    """Item 3: a selection naming a pack that does not exist fails the whole request."""
    bogus = "00000000-0000-0000-0000-000000000000"
    with commit():
        response = api.post(
            f"/api/v1/reviews/{catalogue_review.uuid}/check/",
            {"rule_packs": [str(door_width_pack.uuid), bogus]},
            format="json",
        )
    assert response.status_code == 400
    assert response.data["code"] == "validation_error"
    assert bogus in str(response.data["detail"])

    # Refused, not silently narrowed to the one pack that did exist.
    assert not CheckRun.objects.for_tenant(catalogue_review.tenant).exists()


def test_the_same_pack_selected_twice_is_refused_as_ambiguous(
    api: APIClient, catalogue_review: Review, door_width_pack: RulePack, commit: Any
) -> None:
    """Item 3, the other refusal named in the task: ambiguous, not just unknown."""
    with commit():
        response = api.post(
            f"/api/v1/reviews/{catalogue_review.uuid}/check/",
            {"rule_packs": [str(door_width_pack.uuid), str(door_width_pack.uuid)]},
            format="json",
        )
    assert response.status_code == 400
    assert "ambiguous" in str(response.data["detail"])
    assert not CheckRun.objects.for_tenant(catalogue_review.tenant).exists()


def test_a_catalogue_review_refuses_a_check_with_no_selection(
    api: APIClient, catalogue_review: Review, commit: Any
) -> None:
    with commit():
        response = api.post(f"/api/v1/reviews/{catalogue_review.uuid}/check/")
    assert response.status_code == 400
    assert not CheckRun.objects.for_tenant(catalogue_review.tenant).exists()


def test_a_review_with_an_uploaded_rule_set_refuses_a_catalogue_selection(
    api: APIClient, review: Review, door_width_pack: RulePack, commit: Any
) -> None:
    """The existing single-`RuleSet` path and a catalogue selection are mutually
    exclusive on one review: naming both is refused rather than picking one silently."""
    with commit():
        response = api.post(
            f"/api/v1/reviews/{review.uuid}/check/",
            {"rule_packs": [str(door_width_pack.uuid)]},
            format="json",
        )
    assert response.status_code == 400
    assert not CheckRun.objects.for_tenant(review.tenant).filter(review=review).exists()


def test_a_completed_run_still_reports_what_it_checked_after_the_catalogue_changes(
    catalogue_review: Review,
    door_width_pack: RulePack,
    owner: Any,
    tenant: Tenant,
    commit: Any,
) -> None:
    """Item 4: reproducibility, the additive half.

    The catalogue gains a newer version of the same pack (T-0030's seeder never
    overwrites -- a version bump is a new row); the already-completed run's own
    citation must be unaffected. T-0031's review (F3) is explicit that this alone does
    not distinguish a JSON snapshot from a plain `ForeignKey(RulePack)`: a new row would
    leave an FK-based citation just as untouched. The test that actually distinguishes
    them -- same uuid, different bytes -- is
    `test_a_cited_packs_bytes_changing_behind_its_uuid_is_refused` below.
    """
    with commit():
        run = ReviewService(tenant=tenant).request_check(
            review=catalogue_review,
            requested_by=owner,
            rule_pack_uuids=[str(door_width_pack.uuid)],
        )
    run.refresh_from_db()
    assert run.status == CheckRunStatus.SUCCEEDED
    original_selection = run.rule_pack_selection

    # Mutate the catalogue: a newer version of the same pack is added.
    newer = _seed(DOOR_WIDTH_IDS, version="0.2")
    assert newer.pk != door_width_pack.pk

    run.refresh_from_db()
    assert run.rule_pack_selection == original_selection
    assert len(run.rule_pack_selection) == 1
    assert run.rule_pack_selection[0]["uuid"] == str(door_width_pack.uuid)
    assert run.rule_pack_selection[0]["version"] == "0.1"


def test_a_cited_packs_bytes_changing_behind_its_uuid_is_refused(
    catalogue_review: Review,
    door_width_pack: RulePack,
    owner: Any,
) -> None:
    """Item 4, the differentiating half (T-0031's review, F1 and F3).

    A new pack row (the test above) proves nothing an FK-based citation would not also
    prove. The one edit a hash-based citation catches and an FK cannot is this one: the
    *same* uuid, with different bytes behind it. No in-repo path can cause this today --
    every seeded pack is immutable -- so the bytes are swapped directly in storage here,
    simulating exactly the edit F1's review found nothing would notice.
    """
    pack_service = RulePackService()
    citation = pack_service.snapshot(door_width_pack)
    cited_checksum = citation["checksum_sha256"]

    # A run dispatched and cited against `door_width_pack` as it is right now -- created
    # directly, the same way `test_a_stalled_run_is_failed_rather_than_left_looking_busy`
    # does in test_check_run.py, so the citation is fixed before the swap below happens.
    run = CheckRun.objects.create_run(
        review=catalogue_review, requested_by=owner, rule_pack_selection=[citation]
    )
    assert run.rule_pack_selection[0]["checksum_sha256"] == cited_checksum

    # Swap the bytes behind the same uuid, same storage key -- a different pack's IDS
    # content, saved over the one `door_width_pack.uuid` still points to.
    storage = door_width_pack.source_file.storage
    name = door_width_pack.source_file.name
    assert name is not None
    storage.delete(name)
    storage.save(name, ContentFile(DOOR_NAME_IDS.read_bytes()))

    executed = CheckRunExecutor().execute(run.uuid)

    assert executed.status == CheckRunStatus.FAILED
    assert executed.failure_reason == CheckRunFailure.RULE_PACK_MODIFIED
    assert executed.report is None
    assert cited_checksum in executed.failure_detail
    assert str(door_width_pack.uuid) in executed.failure_detail


def test_a_runs_selection_is_visible_to_its_own_tenant_and_not_to_another(
    api: APIClient,
    rival_api: APIClient,
    catalogue_review: Review,
    door_width_pack: RulePack,
    commit: Any,
) -> None:
    """Item 5: tenancy. The catalogue itself is global (T-0030); the run that cites it is
    not."""
    with commit():
        queued = api.post(
            f"/api/v1/reviews/{catalogue_review.uuid}/check/",
            {"rule_packs": [str(door_width_pack.uuid)]},
            format="json",
        )
    run_uuid = queued.data["uuid"]

    owner_view = api.get(f"/api/v1/reviews/{catalogue_review.uuid}/runs/{run_uuid}/")
    assert owner_view.status_code == 200
    assert owner_view.data["rule_pack_selection"]

    rival_view = rival_api.get(f"/api/v1/reviews/{catalogue_review.uuid}/runs/{run_uuid}/")
    assert rival_view.status_code == 404
