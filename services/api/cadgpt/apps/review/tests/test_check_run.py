"""The real path, end to end: upload, register, review, check, read the report.

No mocks. A real IFC, a real IDS, the real engine, the real task function, over the real
HTTP stack. The counts asserted here are the product's entire claim -- that "violates the
rule" and "lacks the data the rule needs" are different answers.
"""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest
from conftest import ENGINE_FIXTURES, IDS_FIXTURE, IFC_FIXTURE, _upload
from django.utils import timezone
from rest_framework.test import APIClient

from cadgpt.apps.account.models import User
from cadgpt.apps.base.exceptions import ConflictError
from cadgpt.apps.media.choices import MediaKind
from cadgpt.apps.media.models import Media
from cadgpt.apps.media.services import MediaService
from cadgpt.apps.project.models import Project
from cadgpt.apps.review.choices import CheckRunFailure, CheckRunStatus
from cadgpt.apps.review.models import CheckRun, Review
from cadgpt.apps.review.services import ReviewService
from cadgpt.apps.review.services.execution import CheckRunExecutor
from cadgpt.apps.review.tasks import (
    execute_check_run,
    reap_lost_dispatch_runs,
    reap_stalled_runs,
)
from cadgpt.apps.rulepack.models import RuleSet
from cadgpt.apps.rulepack.services import RuleSetService
from cadgpt.apps.tenancy.models import Tenant

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


def _review_over(
    ids_path: Path, *, tenant: Tenant, owner: User, project: Project
) -> Review:
    """A review over `three_doors.ifc` and whatever IDS `ids_path` names.

    Built the same way the `review` fixture in `conftest.py` is, just with a different
    rule set -- for T-0038, which needs an IDS with zero requirement facets that the
    shared `review` fixture (`door_width.ids`) does not exercise.
    """
    media = MediaService(tenant=tenant)
    ifc_media = media.store(
        upload=_upload(IFC_FIXTURE, "application/octet-stream"),
        kind=MediaKind.IFC_MODEL,
        uploaded_by=owner,
    )
    ids_media: Media = media.store(
        upload=_upload(ids_path, "application/xml"),
        kind=MediaKind.IDS_RULESET,
        uploaded_by=owner,
    )
    rule_set: RuleSet = RuleSetService(tenant=tenant).create(
        source_file=ids_media, name=ids_path.stem, created_by=owner
    )
    return ReviewService(tenant=tenant).create(
        name=ids_path.stem,
        model_file=ifc_media,
        project=project,
        rule_set=rule_set,
        created_by=owner,
    )


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
    # T-0083: this API request carries no `Accept-Language`, exactly like every real
    # request `services/web` ever sends (T-0072) -- the disclosure is genuinely rendered
    # in the product's one language, Persian, not the English source string.
    assert "مجموعه نقشه" in report["disclosure_text"], (
        "'drawing set', translated -- see cadgpt/locale/fa/LC_MESSAGES/django.po"
    )
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
    assert review.rule_set is not None
    assert run.model_checksum == review.model_file.checksum_sha256
    assert run.rule_set_checksum == review.rule_set.source_file.checksum_sha256


def test_an_optional_specification_with_no_requirements_is_indeterminate_end_to_end(
    api: APIClient, tenant: Tenant, owner: User, project: Project, commit: Any
) -> None:
    """T-0038, through the real stack: upload, review, check, read the stored run.

    `door_optional_no_requirements.ids` matches all three real doors and states zero
    requirement facets -- optional cardinality, so it checked nothing and established
    nothing. A stored `CheckRun` must say INDETERMINATE, not PASS, and must carry the
    engine version that changed this verdict (T-0038's `docs/decisions.md` entry: a
    verdict-changing release bumps the engine version).
    """
    review = _review_over(
        ENGINE_FIXTURES / "door_optional_no_requirements.ids",
        tenant=tenant,
        owner=owner,
        project=project,
    )
    with commit():
        queued = api.post(f"/api/v1/reviews/{review.uuid}/check/")
    assert queued.status_code == 202, queued.data

    run = CheckRun.objects.for_tenant(tenant).get(uuid=queued.data["uuid"])
    assert run.status == CheckRunStatus.SUCCEEDED
    assert run.outcome == "INDETERMINATE"
    assert (run.passed, run.failed, run.indeterminate) == (0, 0, 0)
    assert run.engine_version, "an old run stays explainable only if it says so itself"

    detail = api.get(f"/api/v1/reviews/{review.uuid}/runs/{run.uuid}/")
    assert detail.status_code == 200
    spec = detail.data["report"]["specifications"][0]
    assert spec["applicability"] == "APPLIES"
    assert spec["matched"] == 3
    assert spec["requirements"] == []
    assert spec["status"] == "INDETERMINATE"
    assert spec["reason_code"] == "NO_REQUIREMENTS_NOTHING_ASSERTED"
    assert spec["reason_label"], "a reason code with no translation is a bare identifier"


def test_a_required_specification_with_no_requirements_still_passes_end_to_end(
    api: APIClient, tenant: Tenant, owner: User, project: Project, commit: Any
) -> None:
    """T-0038's control case, through the real stack: `required` with zero requirement
    facets is a legitimate existence check over real matched subjects and must stay PASS.
    """
    review = _review_over(
        ENGINE_FIXTURES / "door_required_no_requirements.ids",
        tenant=tenant,
        owner=owner,
        project=project,
    )
    with commit():
        queued = api.post(f"/api/v1/reviews/{review.uuid}/check/")
    assert queued.status_code == 202, queued.data

    run = CheckRun.objects.for_tenant(tenant).get(uuid=queued.data["uuid"])
    assert run.status == CheckRunStatus.SUCCEEDED
    assert run.outcome == "PASS"
    assert run.engine_version


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


def test_a_run_whose_dispatch_was_lost_can_be_recovered(
    tenant: Tenant, review: Review, owner: Any, settings: Any
) -> None:
    """T-0056: a `PENDING` run whose `on_commit` callback never fired stops blocking.

    Calling `request_check` outside the `commit()` fixture -- exactly like
    `test_a_second_check_while_one_is_in_flight_is_refused` above -- leaves the
    transaction's `on_commit` callback registered but never run, which is precisely what a
    worker dying between `COMMIT` and that callback firing looks like: a `PENDING` row with
    no `task_id`. Backdating it past `CHECK_RUN_STALL_SECONDS` is what a live dispatch
    could never produce (`_dispatch` writes `task_id` synchronously, long before that).
    """
    settings.CHECK_RUN_STALL_SECONDS = 60
    stuck = ReviewService(tenant=tenant).request_check(review=review, requested_by=owner)
    assert stuck.task_id == "", "the on_commit dispatch must not have run in this test"
    CheckRun.objects.filter(pk=stuck.pk).update(
        created_at=timezone.now() - timedelta(seconds=120)
    )

    # The hole, reproduced: the existing RUNNING-only sweep does not see it, and it is
    # still exactly the row it was.
    assert CheckRunExecutor().reap_stalled() == 0
    stuck.refresh_from_db()
    assert stuck.status == CheckRunStatus.PENDING

    # The recovery: asking for a new check reaps the stuck one first and succeeds.
    recovered = ReviewService(tenant=tenant).request_check(
        review=review, requested_by=owner
    )

    stuck.refresh_from_db()
    assert stuck.status == CheckRunStatus.FAILED
    assert stuck.failure_reason == CheckRunFailure.DISPATCH_LOST
    assert stuck.failure_detail
    assert recovered.uuid != stuck.uuid
    assert recovered.status == CheckRunStatus.PENDING


def test_a_genuinely_queued_run_is_not_swept_as_lost(
    tenant: Tenant, review: Review, owner: Any, settings: Any
) -> None:
    """The false-positive direction: age alone must never be the signal.

    This run carries a `task_id` -- it really was dispatched and is only old because the
    queue is busy. Sweeping it just for its age would silently throw away a review's only
    working check underneath it.
    """
    settings.CHECK_RUN_STALL_SECONDS = 60
    run = CheckRun.objects.create_run(review=review, requested_by=owner)
    CheckRun.objects.filter(pk=run.pk).update(
        task_id="celery-task-id-still-queued",
        queued_at=timezone.now() - timedelta(seconds=120),
        created_at=timezone.now() - timedelta(seconds=120),
    )

    with pytest.raises(ConflictError):
        ReviewService(tenant=tenant).request_check(review=review, requested_by=owner)

    run.refresh_from_db()
    assert run.status == CheckRunStatus.PENDING, (
        "a run that was actually dispatched must never be reaped just for being old"
    )


def test_a_young_pending_run_with_no_task_id_is_not_swept_either(
    tenant: Tenant, review: Review, owner: Any, settings: Any
) -> None:
    """The age threshold is load-bearing, not decorative.

    A `PENDING` run with no `task_id` and no age past `CHECK_RUN_STALL_SECONDS` is the
    normal window between `COMMIT` and `_dispatch`'s synchronous `task_id` write in an
    ordinary, healthy request -- not evidence of a lost dispatch. Reaping it here would
    make every busy moment look like a failure.
    """
    settings.CHECK_RUN_STALL_SECONDS = 120
    young = ReviewService(tenant=tenant).request_check(review=review, requested_by=owner)
    assert young.task_id == "", "the on_commit dispatch must not have run in this test"

    with pytest.raises(ConflictError):
        ReviewService(tenant=tenant).request_check(review=review, requested_by=owner)

    young.refresh_from_db()
    assert young.status == CheckRunStatus.PENDING, (
        "a run well within the stall window must never be reaped just for lacking a "
        "task_id yet -- that is every healthy run's normal first moment"
    )


def test_an_unreadable_model_fails_the_run_with_a_stated_reason(
    api: APIClient, tenant: Tenant, owner: Any, project: Any, rule_set: Any, commit: Any
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
        name="Broken",
        model_file=broken,
        project=project,
        rule_set=rule_set,
        created_by=owner,
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


def test_a_run_below_the_claim_limit_is_reclaimed_and_the_count_survives_a_dead_worker(
    tenant: Tenant, review: Review, owner: Any, settings: Any
) -> None:
    """Redelivery after a dead worker re-claims the run and counts the attempt.

    Simulates exactly the state `acks_late` redelivery finds: the previous worker's
    `_claim` committed -- the run is RUNNING and `claim_count` reflects that one claim --
    but it never reached a terminal state, because it died doing the expensive work in
    between. `_claim` must still be willing to reclaim it (T-0033 explicitly keeps that
    behaviour) and must count this as a second attempt.
    """
    settings.CHECK_RUN_MAX_CLAIMS = 3
    run = CheckRun.objects.create_run(review=review, requested_by=owner)
    CheckRun.objects.filter(pk=run.pk).update(status=CheckRunStatus.RUNNING, claim_count=1)

    claimed = CheckRunExecutor()._claim(run.uuid)

    assert claimed.status == CheckRunStatus.RUNNING
    assert claimed.claim_count == 2


def test_a_run_claimed_too_many_times_is_ended_rather_than_claimed_again(
    tenant: Tenant, review: Review, owner: Any, settings: Any
) -> None:
    """The poison-message bound: a run that keeps dying stops, instead of cycling.

    `claim_count` already at the limit is exactly what redelivery number
    `CHECK_RUN_MAX_CLAIMS + 1` finds: every prior claim committed and none of them
    finished. The run is failed with a reason distinct from `STALLED` -- this one was
    ended on purpose, not left to time out -- and the limit is a ceiling, not a counter
    that keeps climbing once tripped.
    """
    settings.CHECK_RUN_MAX_CLAIMS = 3
    run = CheckRun.objects.create_run(review=review, requested_by=owner)
    CheckRun.objects.filter(pk=run.pk).update(status=CheckRunStatus.RUNNING, claim_count=3)

    claimed = CheckRunExecutor()._claim(run.uuid)

    assert claimed.status == CheckRunStatus.FAILED
    assert claimed.failure_reason == CheckRunFailure.RESOURCE_EXHAUSTED
    assert claimed.failure_detail
    assert claimed.claim_count == 3


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


def test_the_periodic_sweep_recovers_a_lost_dispatch_run_with_nobody_retrying(
    tenant: Tenant, review: Review, owner: Any, settings: Any
) -> None:
    """T-0085: the recovery no longer needs a second request to happen at all.

    Same reproduction as `test_a_run_whose_dispatch_was_lost_can_be_recovered` -- a
    `PENDING` run whose `on_commit` callback never fired, backdated past
    `CHECK_RUN_STALL_SECONDS` -- but this time nothing calls `request_check` again.
    `CheckRunExecutor().reap_lost_dispatch()` is the periodic tick beat now runs
    (`review.tasks.reap_lost_dispatch_runs`); it must find and fail the row on its own.
    """
    settings.CHECK_RUN_STALL_SECONDS = 60
    stuck = ReviewService(tenant=tenant).request_check(review=review, requested_by=owner)
    assert stuck.task_id == "", "the on_commit dispatch must not have run in this test"
    CheckRun.objects.filter(pk=stuck.pk).update(
        created_at=timezone.now() - timedelta(seconds=120)
    )

    reaped = CheckRunExecutor().reap_lost_dispatch()

    assert reaped == 1
    stuck.refresh_from_db()
    assert stuck.status == CheckRunStatus.FAILED
    assert stuck.failure_reason == CheckRunFailure.DISPATCH_LOST
    assert stuck.failure_detail

    # And the review is checkable again, still without any manual sweep or retry loop --
    # `MAX_IN_FLIGHT_RUNS` no longer sees a phantom in-flight run.
    recovered = ReviewService(tenant=tenant).request_check(
        review=review, requested_by=owner
    )
    assert recovered.status == CheckRunStatus.PENDING


def test_the_periodic_sweep_does_not_touch_a_genuinely_queued_run(
    tenant: Tenant, review: Review, owner: Any, settings: Any
) -> None:
    """The false-positive direction for the periodic sweep, mirroring the reactive test."""
    settings.CHECK_RUN_STALL_SECONDS = 60
    run = CheckRun.objects.create_run(review=review, requested_by=owner)
    CheckRun.objects.filter(pk=run.pk).update(
        task_id="celery-task-id-still-queued",
        queued_at=timezone.now() - timedelta(seconds=120),
        created_at=timezone.now() - timedelta(seconds=120),
    )

    assert CheckRunExecutor().reap_lost_dispatch() == 0

    run.refresh_from_db()
    assert run.status == CheckRunStatus.PENDING, (
        "a run that was actually dispatched must never be reaped just for being old"
    )


def test_the_periodic_sweep_reaps_lost_dispatches_across_every_tenant(
    tenant: Tenant,
    review: Review,
    owner: Any,
    other_tenant: Tenant,
    other_owner: Any,
    settings: Any,
) -> None:
    """Cross-tenant by construction: one tick must recover both tenants' stuck runs.

    `reap_lost_dispatch` reads `CheckRun.objects.dispatch_lost(...)` directly rather than
    a `for_tenant(...)`-scoped queryset -- exactly `reap_stalled`'s existing pattern
    (`execution.py`) for the RUNNING side. This is that property, exercised: a second
    tenant's own lost-dispatch run, created independently, is reaped in the same call as
    the first tenant's, with no tenant argument anywhere on the call.
    """
    from django.core.files.uploadedfile import SimpleUploadedFile

    from cadgpt.apps.media.choices import MediaKind
    from cadgpt.apps.media.services import MediaService
    from cadgpt.apps.project.models import Project
    from cadgpt.apps.rulepack.services import RuleSetService

    settings.CHECK_RUN_STALL_SECONDS = 60

    first = ReviewService(tenant=tenant).request_check(review=review, requested_by=owner)
    CheckRun.objects.filter(pk=first.pk).update(
        created_at=timezone.now() - timedelta(seconds=120)
    )

    other_ids_media = MediaService(tenant=other_tenant).store(
        upload=SimpleUploadedFile(
            IDS_FIXTURE.name, IDS_FIXTURE.read_bytes(), content_type="application/xml"
        ),
        kind=MediaKind.IDS_RULESET,
        uploaded_by=other_owner,
    )
    other_ifc_media = MediaService(tenant=other_tenant).store(
        upload=SimpleUploadedFile(
            IFC_FIXTURE.name,
            IFC_FIXTURE.read_bytes(),
            content_type="application/octet-stream",
        ),
        kind=MediaKind.IFC_MODEL,
        uploaded_by=other_owner,
    )
    other_rule_set = RuleSetService(tenant=other_tenant).create(
        source_file=other_ids_media, name="Rival's doors", created_by=other_owner
    )
    other_project = Project.objects.create_project(
        tenant=other_tenant, name="Rival's project", created_by=other_owner
    )
    other_review = ReviewService(tenant=other_tenant).create(
        name="Rival's review",
        model_file=other_ifc_media,
        project=other_project,
        rule_set=other_rule_set,
        created_by=other_owner,
    )
    second = ReviewService(tenant=other_tenant).request_check(
        review=other_review, requested_by=other_owner
    )
    CheckRun.objects.filter(pk=second.pk).update(
        created_at=timezone.now() - timedelta(seconds=120)
    )

    reaped = CheckRunExecutor().reap_lost_dispatch()

    assert reaped == 2
    first.refresh_from_db()
    second.refresh_from_db()
    assert first.status == CheckRunStatus.FAILED
    assert first.failure_reason == CheckRunFailure.DISPATCH_LOST
    assert second.status == CheckRunStatus.FAILED
    assert second.failure_reason == CheckRunFailure.DISPATCH_LOST


def _persian(msgid: str) -> str:
    """What `msgid` actually translates to in the `fa` catalogue, computed with an
    explicit, local `translation.override` -- used only to build the *expected* side of
    an assertion below, never anywhere near the code under test. Building this from the
    real compiled catalogue (rather than retyping the Persian by hand) is what makes the
    assertion resilient to the wording changing in `cadgpt/locale/fa/LC_MESSAGES/django.po`
    without silently starting to compare two different strings.
    """
    from django.utils import translation
    from django.utils.translation import gettext

    with translation.override("fa"):
        return str(gettext(msgid))


def _is_persian(text: str) -> bool:
    """True only if `text` actually contains Persian/Arabic-block script.

    `_persian(msgid)` alone is not enough of a check: if the catalogue were never
    compiled, `gettext` would silently fall back to returning `msgid` unchanged (plain
    English), and comparing the worker's stored value against that same fallback would
    pass without proving anything about the language actually used. This closes that gap
    by refusing to accept a value that is not, in fact, written in Persian script.
    """
    return any("؀" <= character <= "ۿ" for character in text)


def test_the_real_lost_dispatch_task_stores_persian_with_no_accept_language_anywhere(
    tenant: Tenant, review: Review, owner: Any, settings: Any
) -> None:
    """T-0083: the exact shape of every real worker invocation -- no HTTP request, no
    `Accept-Language` header, nothing for `LocaleMiddleware` to ever see or act on, because
    `LocaleMiddleware` never runs for a Celery task at all. This calls
    `review.tasks.reap_lost_dispatch_runs` itself -- the real, registered task Beat's
    periodic tick dispatches (`CELERY_BEAT_SCHEDULE` in `cadgpt/config/settings/base.py`)
    -- rather than the service method directly, and nothing in this test calls
    `translation.activate` or `override` before it runs: whatever language the stored
    `failure_detail` ends up in is entirely down to what the task itself, and the settings
    it runs under, decide on their own.
    """
    settings.CHECK_RUN_STALL_SECONDS = 60
    stuck = ReviewService(tenant=tenant).request_check(review=review, requested_by=owner)
    assert stuck.task_id == "", "the on_commit dispatch must not have run in this test"
    CheckRun.objects.filter(pk=stuck.pk).update(
        created_at=timezone.now() - timedelta(seconds=120)
    )
    assert tenant.language == "en", (
        "this tenant never chose 'fa' -- the Persian result below must come from the "
        "worker's own language activation, not from a tenant-language override"
    )

    reap_lost_dispatch_runs.delay()

    stuck.refresh_from_db()
    assert stuck.status == CheckRunStatus.FAILED
    assert stuck.failure_reason == CheckRunFailure.DISPATCH_LOST
    expected = _persian(
        "This check was requested but its dispatch never reached a worker, so it "
        "was ended. Request the check again."
    )
    assert _is_persian(expected), (
        "the catalogue must actually be compiled for this to mean anything"
    )
    assert stuck.failure_detail == expected


def test_the_real_stalled_sweep_task_stores_persian_with_no_accept_language_anywhere(
    tenant: Tenant, review: Review, owner: Any, settings: Any
) -> None:
    """The RUNNING-side sibling of the test above, over `review.tasks.reap_stalled_runs`.

    `reap_stalled`'s `failure_detail` was, until T-0083, a bare Python string literal --
    never passed through `gettext` at all, so no language activation anywhere could ever
    have made it Persian. This asserts the fixed version: the stored value is not just
    non-English, it is the real compiled Persian translation of the now-wrapped string.
    """
    settings.CHECK_RUN_STALL_SECONDS = 60
    run = CheckRun.objects.create_run(review=review, requested_by=owner)
    CheckRun.objects.filter(pk=run.pk).update(
        status=CheckRunStatus.RUNNING,
        started_at=timezone.now() - timedelta(hours=2),
    )

    reap_stalled_runs.delay()

    run.refresh_from_db()
    assert run.status == CheckRunStatus.FAILED
    assert run.failure_reason == CheckRunFailure.STALLED
    expected = _persian("The worker running this check stopped responding.")
    assert _is_persian(expected), (
        "the catalogue must actually be compiled for this to mean anything"
    )
    assert run.failure_detail == expected


def test_the_real_execute_check_run_task_stores_persian_for_a_claim_limit_failure(
    tenant: Tenant, review: Review, owner: Any, settings: Any
) -> None:
    """`execute_check_run` itself, the task every real dispatch actually queues, driven
    into its `RESOURCE_EXHAUSTED` failure branch (`CheckRunExecutor._claim`) -- the
    synchronous counterpart to the two periodic sweeps above, going through
    `BaseTask.__call__`'s language activation exactly the way a real redelivered,
    already-poisoned message would.
    """
    settings.CHECK_RUN_MAX_CLAIMS = 3
    run = CheckRun.objects.create_run(review=review, requested_by=owner)
    CheckRun.objects.filter(pk=run.pk).update(status=CheckRunStatus.RUNNING, claim_count=3)

    execute_check_run.delay(str(run.uuid))

    run.refresh_from_db()
    assert run.status == CheckRunStatus.FAILED
    assert run.failure_reason == CheckRunFailure.RESOURCE_EXHAUSTED
    expected = _persian(
        "This run was claimed %(count)s times without finishing and has "
        "been stopped rather than tried again."
    ) % {"count": 3}
    assert _is_persian(expected), (
        "the catalogue must actually be compiled for this to mean anything"
    )
    assert run.failure_detail == expected
