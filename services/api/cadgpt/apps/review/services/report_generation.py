"""Generating the Markdown report file for a succeeded check run, and storing it.

Idempotency is the contract, the same way it is for `CheckRunExecutor`: `acks_late` means a
message survives a worker that dies mid-task and is delivered again, so `generate` must
reach the same end state whether it runs once or five times. Unlike checking a model,
rendering an already-stored report and writing a small text file is fast, so the row lock is
held for the whole operation rather than released before it -- there is no minutes-long
external call here to hold a connection open against, and doing it this way means two
redeliveries racing each other can never both pass the "not generated yet" check and each
store a file: the loser blocks on the lock, sees `report_file_id` already set when it
acquires it, and returns without writing anything. One file, never two, never half-written.

**The language decision.** A generated file has no request to negotiate a language from --
Markdown carries no `Accept-Language`, and the file is written once, for whoever downloads
it. `Tenant.language` (`cadgpt.apps.tenancy.models.Tenant`) already exists for exactly this
purpose -- its own docstring: "Reports and notifications are written in this language
unless a member overrides it." A member's live override (T-0029-era per-request language
resolution) applies to the API's `localize_report`, rendered fresh on every request; it
cannot apply to a file that is written once and then just sits in storage. So this
generator activates the tenant's language, not the requesting member's, and renders once.
If the tenant's `language` changes after generation, the already-stored file does not
change with it -- it is bytes in storage, exactly like an uploaded model, and nothing
re-renders it after the fact. A later regeneration (there is none in this task's scope;
`report_file_id` being set makes `generate` a no-op) would be the only way to produce a
file in the new language.
"""

from __future__ import annotations

import uuid as uuid_lib
from typing import cast

from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import transaction
from django.utils import translation

from cadgpt.apps.base.exceptions import NotFoundError
from cadgpt.apps.base.services import BaseService
from cadgpt.apps.media.choices import MediaKind
from cadgpt.apps.media.services import MediaService
from cadgpt.apps.review.choices import CheckRunStatus
from cadgpt.apps.review.models import CheckRun
from cadgpt.apps.review.services.presentation import localize_report
from cadgpt.apps.review.services.report_markdown import render_markdown_report


class ReportGenerationService(BaseService):
    """Renders a succeeded run's stored report to Markdown. Safe to call twice."""

    def generate(self, run_uuid: uuid_lib.UUID | str) -> CheckRun:
        with transaction.atomic():
            found = (
                # `of=("self",)` for the same reason `CheckRunExecutor._claim` uses it:
                # `review` is a non-nullable join here, but restricting the lock to this
                # table only is the safe default regardless of what a future select_related
                # joins across.
                CheckRun.objects.select_for_update(of=("self",))
                .select_related("tenant", "review")
                .filter(uuid=run_uuid)
                .first()
            )
            if found is None:
                raise NotFoundError(f"No check run with uuid {run_uuid}.")
            run = cast("CheckRun", found)

            if run.report_file_id is not None:
                self.log.info(
                    "report_file_already_generated",
                    run_id=str(run.uuid),
                    media_id=str(run.report_file_id),
                )
                return run

            if run.status != CheckRunStatus.SUCCEEDED or run.report is None:
                # The dispatcher (`CheckRunExecutor._succeed`) only ever enqueues this
                # after a run has succeeded and been saved with its report -- reaching
                # this branch means a redelivery is racing ahead of that save somehow, or
                # this was called directly against a run that never succeeded. Either way
                # there is nothing to render yet; raising (rather than silently no-op'ing)
                # surfaces it instead of a report file that never appears with no trace of
                # why.
                raise ValueError(f"Check run {run.uuid} has no report to render yet.")

            with translation.override(run.tenant.language):
                localized = localize_report(run.report)
                assert localized is not None  # report is not None, checked above
                markdown = render_markdown_report(localized, run.rule_pack_selection)

            upload = SimpleUploadedFile(
                f"report-{run.uuid}.md",
                markdown.encode("utf-8"),
                content_type="text/markdown",
            )
            media = MediaService(tenant=run.tenant).store(
                upload=upload, kind=MediaKind.REPORT
            )

            run.report_file = media
            run.save(update_fields=["report_file", "updated_at"])

        self.log.info(
            "report_file_generated",
            run_id=str(run.uuid),
            media_id=str(media.uuid),
            language=run.tenant.language,
        )
        return run
