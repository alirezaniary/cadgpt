"""The real path, end to end: upload, register, review, check, read the report.

No mocks. A real IFC, a real IDS, the real engine, the real task function, over the real
HTTP stack. The counts asserted here are the product's entire claim -- that "violates the
rule" and "lacks the data the rule needs" are different answers.
"""

from __future__ import annotations

from typing import Any

import pytest
from rest_framework.test import APIClient

from cadgpt.apps.review.choices import CheckRunFailure, CheckRunStatus
from cadgpt.apps.review.models import CheckRun, Review
from cadgpt.apps.review.services import ReviewService
from cadgpt.apps.review.services.execution import CheckRunExecutor
from cadgpt.apps.tenancy.models import Tenant

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


def test_a_check_separates_a_violation_from_missing_data(
    api: APIClient, review: Review, commit: Any
) -> None:
    """Three doors: one passes, one is too narrow, one records no width at all.

    A two-valued checker calls this two failures. Reporting it that way would tell an
    architect they have two violations when they have one violation and one unknown.
    """
    with commit():
        queued = api.post(f"/api/v1/reviews/{review.uuid}/check/")
    assert queued.status_code == 202, queued.data

    run_uuid = queued.data["uuid"]
    detail = api.get(f"/api/v1/reviews/{review.uuid}/runs/{run_uuid}/")
    assert detail.status_code == 200

    body = detail.data
    assert body["status"] == CheckRunStatus.SUCCEEDED
    assert body["outcome"] == "FAIL"
    assert (body["passed"], body["failed"], body["indeterminate"]) == (1, 1, 1)
    assert body["engine_version"]

    report = body["report"]
    assert report["ids_title"] == "Accessible door width"
    assert report["ifc_filename"] == "three_doors.ifc", (
        "the report must name the file the architect uploaded, not the storage key"
    )
    assert report["disclosure_title"]
    assert "three_doors.ifc" in report["disclosure_text"], (
        "the I7 disclosure must name the model that was actually checked, from the "
        "payload, not a hardcoded example filename"
    )
    assert "drawing set" in report["disclosure_text"]
    entities = [
        entity
        for spec in report["specifications"]
        for requirement in spec["requirements"]
        for entity in requirement["entities"]
    ]
    by_status = {entity["status"] for entity in entities}
    assert by_status == {"FAIL", "INDETERMINATE"}

    # Every non-passing element carries a machine code and the sentence for it.
    for entity in entities:
        assert entity["reason_code"]
        assert entity["reason_label"]
        assert entity["reason_label"] != entity["reason_code"], (
            "a reason code with no translation would surface to a user as an identifier"
        )


def test_indeterminate_is_never_counted_as_a_pass(
    api: APIClient, review: Review, commit: Any
) -> None:
    """The invariant, asserted at the API boundary rather than only in the engine."""
    with commit():
        api.post(f"/api/v1/reviews/{review.uuid}/check/")
    run = CheckRun.objects.for_tenant(review.tenant).first()

    assert run is not None
    assert run.indeterminate == 1
    assert run.passed == 1, (
        "the indeterminate element must not have been folded into passed"
    )
    assert run.outcome == "FAIL"


def test_the_run_records_the_exact_inputs_it_checked(
    api: APIClient, review: Review, commit: Any
) -> None:
    """An old run stays explainable only if it names the bytes it read."""
    with commit():
        api.post(f"/api/v1/reviews/{review.uuid}/check/")
    run = CheckRun.objects.for_tenant(review.tenant).first()

    assert run is not None
    assert run.model_checksum == review.model_file.checksum_sha256
    assert run.rule_set_checksum == review.rule_set.source_file.checksum_sha256


def test_running_the_same_task_twice_changes_nothing(
    tenant: Tenant, review: Review, owner: Any, commit: Any
) -> None:
    """`acks_late` means a message survives a dead worker and is delivered again.

    The second delivery must find the run terminal and leave it exactly as it was, or a
    redelivery would overwrite a finished result with a fresh evaluation.
    """
    with commit():
        run = ReviewService(tenant=tenant).request_check(review=review, requested_by=owner)
    run.refresh_from_db()

    assert run.status == CheckRunStatus.SUCCEEDED
    first_finished_at = run.finished_at
    first_report = run.report

    replayed = CheckRunExecutor().execute(run.uuid)

    assert replayed.status == CheckRunStatus.SUCCEEDED
    assert replayed.finished_at == first_finished_at
    assert replayed.report == first_report


def test_a_second_check_while_one_is_in_flight_is_refused(
    api: APIClient, review: Review, tenant: Tenant, commit: Any
) -> None:
    """Two runs of the same review would burn a worker to produce the same answer."""
    with commit():
        api.post(f"/api/v1/reviews/{review.uuid}/check/")
    CheckRun.objects.for_tenant(tenant).update(status=CheckRunStatus.RUNNING)

    second = api.post(f"/api/v1/reviews/{review.uuid}/check/")
    assert second.status_code == 409
    assert second.json()["code"] == "conflict"


def test_an_unreadable_model_fails_the_run_with_a_stated_reason(
    api: APIClient, tenant: Tenant, owner: Any, rule_set: Any, commit: Any
) -> None:
    """A rejected input and a crashed worker are different events, reported differently."""
    from django.core.files.uploadedfile import SimpleUploadedFile

    from cadgpt.apps.media.choices import MediaKind
    from cadgpt.apps.media.services import MediaService

    broken = MediaService(tenant=tenant).store(
        upload=SimpleUploadedFile("broken.ifc", b"this is not an IFC file"),
        kind=MediaKind.IFC_MODEL,
        uploaded_by=owner,
    )
    review = ReviewService(tenant=tenant).create(
        name="Broken", model_file=broken, rule_set=rule_set, created_by=owner
    )

    with commit():
        response = api.post(f"/api/v1/reviews/{review.uuid}/check/")
    assert response.status_code == 202

    run = CheckRun.objects.for_tenant(tenant).for_review(review.pk).first()
    assert run is not None
    assert run.status == CheckRunStatus.FAILED
    assert run.failure_reason == CheckRunFailure.INVALID_MODEL
    assert run.failure_detail


def test_a_stalled_run_is_failed_rather_than_left_looking_busy(
    tenant: Tenant, review: Review, owner: Any, settings: Any
) -> None:
    """A run stuck in RUNNING blocks its review from ever being re-checked."""
    from datetime import timedelta

    from django.utils import timezone

    settings.CHECK_RUN_STALL_SECONDS = 60
    run = CheckRun.objects.create_run(review=review, requested_by=owner)
    CheckRun.objects.filter(pk=run.pk).update(
        status=CheckRunStatus.RUNNING,
        started_at=timezone.now() - timedelta(hours=2),
    )

    assert CheckRunExecutor().reap_stalled() == 1

    run.refresh_from_db()
    assert run.status == CheckRunStatus.FAILED
    assert run.failure_reason == CheckRunFailure.STALLED


def test_a_list_of_runs_does_not_load_the_report_documents(
    api: APIClient, review: Review, commit: Any
) -> None:
    """A report can be megabytes. A list of six numbers must not fetch them."""
    with commit():
        api.post(f"/api/v1/reviews/{review.uuid}/check/")

    response = api.get(f"/api/v1/reviews/{review.uuid}/runs/")
    assert response.status_code == 200
    assert response.data["count"] == 1
    assert "report" not in response.data["results"][0]
