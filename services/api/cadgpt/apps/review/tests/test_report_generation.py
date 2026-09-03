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


def _lost_dispatch(*_args: object, **_kwargs: object) -> None:
    """Stands in for `generate_report_file.delay` when a message never arrives -- a
    worker dying between commit and the callback, or `.delay()` itself raising because
    the broker blipped. Used by the T-0051 tests below to reproduce that hole for one
    run's dispatch without touching any other test's."""


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


# ---------------------------------------------------------------------------- T-0051


def test_a_lost_report_dispatch_leaves_a_run_stuck_and_the_recovery_route_fixes_it(
    tenant: Tenant,
    review: Review,
    owner: Any,
    api: APIClient,
    django_capture_on_commit_callbacks: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Reproduces the hole this task exists to close, the same way the T-0032 review
    found it (`docs/tasks/T-0051-a-report-that-failed-to-generate-can-be-recovered.md`):
    stub `generate_report_file.delay` to a no-op for one run's dispatch, let the check
    finish, and confirm the end state is exactly `succeeded / report_file_id=None` --
    permanently, because redelivering the check's own task finds a terminal run and
    returns it untouched; `execute()` never re-dispatches report generation.

    Then asks again, for real, over `CheckRunViewSet.generate_report` (the new
    route this task adds), and confirms the file exists afterward, fetched over
    authenticated HTTP exactly like a normally-generated one.
    """
    from cadgpt.apps.review import tasks as review_tasks
    from cadgpt.apps.review.services import ReviewService
    from cadgpt.apps.review.services.execution import CheckRunExecutor

    monkeypatch.setattr(review_tasks.generate_report_file, "delay", _lost_dispatch)
    with django_capture_on_commit_callbacks(execute=True):
        run = ReviewService(tenant=tenant).request_check(review=review, requested_by=owner)
    monkeypatch.undo()  # restore .delay before the recovery route needs the real thing

    run.refresh_from_db()
    assert run.status == CheckRunStatus.SUCCEEDED
    assert run.report_file_id is None
    assert run.report_generation_error == ""
    assert Media.objects.for_tenant(tenant).filter(kind="report").count() == 0

    # The hole, confirmed before any fix is asked for: a redelivery of the check's own
    # task cannot recover this on its own.
    stuck = CheckRunExecutor().execute(run.uuid)
    assert stuck.status == CheckRunStatus.SUCCEEDED
    assert stuck.report_file_id is None

    response = api.post(f"/api/v1/reviews/{review.uuid}/runs/{run.uuid}/report-file/")
    assert response.status_code == 202, response.data

    run.refresh_from_db()
    assert run.report_file_id is not None
    assert run.report_file.kind == "report"
    assert Media.objects.for_tenant(tenant).filter(kind="report").count() == 1

    downloaded = api.get(f"/api/v1/reviews/{review.uuid}/runs/{run.uuid}/report-file/")
    assert downloaded.status_code == 200
    body = b"".join(downloaded.streaming_content).decode("utf-8")
    assert body.startswith("# Accessible door width")


def test_asking_twice_produces_one_file_and_a_run_that_already_has_one_is_untouched(
    tenant: Tenant,
    review: Review,
    owner: Any,
    api: APIClient,
    django_capture_on_commit_callbacks: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The recovery route is `generate` under a new door, not a new idempotence
    contract -- this proves the route itself is safe to call twice, not merely the
    service function it dispatches to (already covered above by
    `test_running_generation_twice_produces_one_file_not_two`)."""
    from cadgpt.apps.review import tasks as review_tasks
    from cadgpt.apps.review.services import ReviewService

    monkeypatch.setattr(review_tasks.generate_report_file, "delay", _lost_dispatch)
    with django_capture_on_commit_callbacks(execute=True):
        run = ReviewService(tenant=tenant).request_check(review=review, requested_by=owner)
    monkeypatch.undo()

    first = api.post(f"/api/v1/reviews/{review.uuid}/runs/{run.uuid}/report-file/")
    assert first.status_code == 202, first.data
    run.refresh_from_db()
    first_media_id = run.report_file_id
    assert first_media_id is not None

    second = api.post(f"/api/v1/reviews/{review.uuid}/runs/{run.uuid}/report-file/")
    assert second.status_code == 202, second.data

    run.refresh_from_db()
    assert run.report_file_id == first_media_id, "a second request must not re-generate"
    assert Media.objects.for_tenant(tenant).filter(kind="report").count() == 1


def test_generation_cannot_be_requested_for_a_run_that_has_not_succeeded(
    tenant: Tenant, review: Review, owner: Any, api: APIClient
) -> None:
    run = CheckRun.objects.create_run(review=review, requested_by=owner)
    assert run.status == CheckRunStatus.PENDING

    response = api.post(f"/api/v1/reviews/{review.uuid}/runs/{run.uuid}/report-file/")

    assert response.status_code == 409, response.data
    run.refresh_from_db()
    assert run.report_file_id is None


def test_a_report_too_large_to_store_leaves_the_run_succeeded_with_no_file(
    tenant: Tenant,
    review: Review,
    owner: Any,
    commit: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The deliberate decision this task names (`docs/tasks/
    T-0051-a-report-that-failed-to-generate-can-be-recovered.md`): a check that
    genuinely found what it found is not retro-failed because its rendering did not fit
    in storage. Rather than fabricating a multi-megabyte fixture to clear the real 8MB
    cap, the real cap is turned down so a small, real render exceeds it -- the check,
    the render and the rejection in `MediaService._validate` are all real; only the
    limit is different, the same technique `test_media_service.py` already uses for the
    same reason.
    """
    from cadgpt.apps.media.choices import MediaKind
    from cadgpt.apps.media.constants import MAX_BYTES
    from cadgpt.apps.review.api.v1.serializers import CheckRunSummarySerializer
    from cadgpt.apps.review.choices import ReportGenerationFailure
    from cadgpt.apps.review.services import ReviewService

    monkeypatch.setitem(MAX_BYTES, MediaKind.REPORT, 10)

    with commit():
        run = ReviewService(tenant=tenant).request_check(review=review, requested_by=owner)

    run.refresh_from_db()
    assert run.status == CheckRunStatus.SUCCEEDED, run.failure_detail
    assert run.report is not None, "the check's own findings are untouched"
    assert run.report_file_id is None
    assert run.report_generation_error == ReportGenerationFailure.TOO_LARGE
    assert run.report_generation_detail, "the real MediaService message, not empty"
    assert Media.objects.for_tenant(tenant).filter(kind="report").count() == 0

    # The API surface a frontend distinguishes on: the run says it cannot be
    # generated, not merely that it has not been yet.
    data = CheckRunSummarySerializer(run).data
    assert data["report_file_url"] is None
    assert data["report_generation_error"] == "too_large"

    # Not eligible for the blind backfill sweep -- retrying would only restate the
    # same rejection.
    assert not CheckRun.objects.missing_report().filter(pk=run.pk).exists()


def test_backfill_generates_reports_for_runs_that_were_never_dispatched(
    tenant: Tenant,
    review: Review,
    owner: Any,
    django_capture_on_commit_callbacks: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Stands in for a run that succeeded before T-0032 deployed the generator: such a
    run is `succeeded`, carries a real `report`, and has never had
    `generate_report_file` dispatched for it -- `CheckRunExecutor._succeed` is the only
    place that ever queues it, so a run whose success predates that queueing line is in
    exactly this shape. Reproduced here the same way as the lost-dispatch case above,
    because the two are identical by construction: nothing distinguishes "never
    dispatched because the code did not exist yet" from "dispatched and lost" once the
    row is written -- which is exactly why `CheckRunQuerySet.missing_report` recovers
    both without needing to know which one a given row is.
    """
    import io

    from django.core.management import call_command

    from cadgpt.apps.review import tasks as review_tasks
    from cadgpt.apps.review.services import ReviewService

    monkeypatch.setattr(review_tasks.generate_report_file, "delay", _lost_dispatch)
    with django_capture_on_commit_callbacks(execute=True):
        run = ReviewService(tenant=tenant).request_check(review=review, requested_by=owner)
    monkeypatch.undo()

    run.refresh_from_db()
    assert run.report_file_id is None

    out = io.StringIO()
    call_command("backfill_report_files", stdout=out)

    run.refresh_from_db()
    assert run.report_file_id is not None
    assert run.report_file.kind == "report"
    output = out.getvalue()
    assert f"generated: run {run.uuid}" in output
    assert "done: 1 generated, 0 could not be generated, 1 runs considered" in output
