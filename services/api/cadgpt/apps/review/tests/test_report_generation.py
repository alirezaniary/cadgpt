"""The Markdown report file: generated after a real check, over the real HTTP stack.

No mocks. A real IFC, a real IDS, the real engine, the real generation task, dispatched the
same way `execute_check_run` is -- on commit, chained from the check's own success.
"""

from __future__ import annotations

from typing import Any

import pytest
from rest_framework.test import APIClient

from cadgpt.apps.media.models import Media
from cadgpt.apps.review.choices import CheckRunStatus
from cadgpt.apps.review.models import CheckRun, Review
from cadgpt.apps.review.services.report_generation import ReportGenerationService
from cadgpt.apps.tenancy.models import Tenant

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


def test_a_successful_check_generates_the_report_file_with_a_url_on_the_run(
    api: APIClient, review: Review, commit: Any
) -> None:
    with commit():
        queued = api.post(f"/api/v1/reviews/{review.uuid}/check/")
    assert queued.status_code == 202, queued.data
    run_uuid = queued.data["uuid"]

    detail = api.get(f"/api/v1/reviews/{review.uuid}/runs/{run_uuid}/")
    assert detail.status_code == 200
    assert detail.data["status"] == "succeeded"
    url = detail.data["report_file_url"]
    assert url, "a succeeded run must carry the generated report's URL"
    assert url.startswith(f"/api/v1/reviews/{review.uuid}/runs/{run_uuid}/report-file/")

    run = CheckRun.objects.get(uuid=run_uuid)
    assert run.report_file_id is not None
    assert run.report_file.kind == "report"
    assert run.report_file.tenant_id == review.tenant_id, (
        "the generated file must belong to the run's own tenant, exactly like an upload"
    )


def test_the_downloaded_file_is_the_real_generated_markdown(
    api: APIClient, review: Review, commit: Any
) -> None:
    with commit():
        queued = api.post(f"/api/v1/reviews/{review.uuid}/check/")
    run_uuid = queued.data["uuid"]

    response = api.get(f"/api/v1/reviews/{review.uuid}/runs/{run_uuid}/report-file/")
    assert response.status_code == 200
    # A real `FileResponse` streams -- `.content` raises on purpose, so a real client
    # (and this test) reads it the way one is meant to be read.
    body = b"".join(response.streaming_content).decode("utf-8")  # type: ignore[attr-defined]
    assert body.startswith("# Accessible door width")
    assert "What this report checked" in body
    assert "## Coverage" in body
    assert "## Specifications" in body
    assert body.index("## Coverage") < body.index("## Specifications")


def test_a_second_tenant_cannot_reach_the_first_tenants_report_file(
    api: APIClient, rival_api: APIClient, review: Review, commit: Any
) -> None:
    with commit():
        queued = api.post(f"/api/v1/reviews/{review.uuid}/check/")
    run_uuid = queued.data["uuid"]

    theirs = rival_api.get(f"/api/v1/reviews/{review.uuid}/runs/{run_uuid}/report-file/")
    assert theirs.status_code == 404


def test_running_generation_twice_produces_one_file_not_two(
    tenant: Tenant, review: Review, owner: Any, commit: Any
) -> None:
    """`acks_late` means a message survives a dead worker and is delivered again. The
    second delivery must find `report_file` already set and change nothing -- not a
    second `Media` row, not a re-render."""
    from cadgpt.apps.review.services import ReviewService

    with commit():
        run = ReviewService(tenant=tenant).request_check(review=review, requested_by=owner)
    run.refresh_from_db()
    assert run.report_file_id is not None
    first_media_id = run.report_file_id
    files_after_first = Media.objects.for_tenant(tenant).filter(kind="report").count()
    assert files_after_first == 1

    replayed = ReportGenerationService().generate(run.uuid)

    assert replayed.report_file_id == first_media_id
    files_after_second = Media.objects.for_tenant(tenant).filter(kind="report").count()
    assert files_after_second == 1, "a redelivered generation must not create a second file"


def test_dispatch_is_registered_on_commit_not_inside_the_transaction(
    tenant: Tenant, review: Review, owner: Any, django_capture_on_commit_callbacks: Any
) -> None:
    """`execution.py:226` must register the dispatch through `transaction.on_commit`,
    not call `generate_report_file.delay(...)` inline. This is the test T-0032's review
    (A1) found hollow: `django_capture_on_commit_callbacks(execute=False)` alone drains
    nothing, so it cannot tell the two apart -- with `execute=False`, `_succeed` is never
    even reached, and the old assertions passed on `ReviewService.request_check`'s
    pre-existing dispatch alone, regardless of what `execution.py` does.

    The distinguishing move: capture (without running) *only* the check's own dispatch,
    then invoke that one captured callback *by hand*, outside any capture context but
    still inside this test's real wrapping transaction. That runs `execute_check_run`
    (`CELERY_TASK_ALWAYS_EAGER`) through to `CheckRunExecutor._succeed`. If `_succeed`
    dispatches report generation via `transaction.on_commit`, that registration just joins
    the connection's pending on-commit queue -- nothing drains it here, so
    `report_file_id` is still `None` immediately afterward. If `_succeed` instead called
    `generate_report_file.delay(...)` inline, it would already have run by this point
    (eager mode), and `report_file_id` would already be set.

    Proof this fails on the regression it targets: replacing `execution.py`'s
    `transaction.on_commit(lambda: generate_report_file.delay(str(run.uuid)))` with a bare
    `generate_report_file.delay(str(run.uuid))` makes this assertion fail -- pasted as
    evidence item 6 in the task file, reverted after.
    """
    from cadgpt.apps.review.services import ReviewService

    with django_capture_on_commit_callbacks(execute=False) as callbacks:
        run = ReviewService(tenant=tenant).request_check(review=review, requested_by=owner)
    assert len(callbacks) == 1, "expected exactly the check's own dispatch to be captured"

    callbacks[0]()  # runs execute_check_run -> CheckRunExecutor._succeed, synchronously

    run.refresh_from_db()
    assert run.status == CheckRunStatus.SUCCEEDED
    assert run.report_file_id is None, (
        "report generation must still be queued on-commit, not already run inline"
    )


def test_a_run_with_no_report_cannot_be_generated_from(
    tenant: Tenant, review: Review, owner: Any
) -> None:
    """Generation only ever follows a real success; calling it on a run with nothing to
    render is a programming error, not a silent no-op that produces an empty file."""
    run = CheckRun.objects.create_run(review=review, requested_by=owner)

    with pytest.raises(ValueError, match="has no report to render yet"):
        ReportGenerationService().generate(run.uuid)
