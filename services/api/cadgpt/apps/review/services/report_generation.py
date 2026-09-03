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

**Recovery (T-0051).** `generate` was, until now, only ever reachable from the one
`on_commit` dispatch `CheckRunExecutor._succeed` registers -- lose that message (a worker
dying between commit and the callback, `.delay()` raising because the broker blipped) and
a succeeded run's report file never arrives, permanently, with nothing that asks again.
`CheckRunViewSet.generate_report` and `manage.py backfill_report_files` are the two
new callers this method did not have before; both are just `generate`, unchanged, because
its row-locked idempotence was already the right contract for "call this again and it is
safe" -- redelivery, a user's retry, and an operator's backfill are the same shape of
problem. What is new in the method body itself is `MediaService.store` being allowed to
fail: a rendered report can exceed `MediaService`'s size cap (plausible for a run with
thousands of findings), and that is answered by *not* retro-failing the run -- it found
what it found -- but recording `report_generation_error` so the run stops looking merely
"not generated yet" and both a user and `CheckRunQuerySet.missing_report` can tell the
difference.
"""

from __future__ import annotations

import uuid as uuid_lib
from typing import cast

from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import transaction
from django.utils import translation

from cadgpt.apps.base.exceptions import NotFoundError, ValidationError
from cadgpt.apps.base.services import BaseService
from cadgpt.apps.media.choices import MediaKind
from cadgpt.apps.media.services import MediaService
from cadgpt.apps.review.choices import CheckRunStatus, ReportGenerationFailure
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
                # Moved inside the tenant-language override with the render itself
                # (T-0051): the exception text this can raise is now persisted
                # (`report_generation_detail`) as part of this run's terminal state,
                # and that state is written once, exactly like the file would have
                # been -- the same "language decision" above, extended to the failure
                # case it did not have to consider before.
                try:
                    media = MediaService(tenant=run.tenant).store(
                        upload=upload, kind=MediaKind.REPORT
                    )
                except ValidationError as exc:
                    # A check that genuinely found what it found is not retro-failed
                    # because its rendering did not fit in storage -- the run stays
                    # SUCCEEDED. This is the terminal, not-retryable state that tells
                    # a user (and `CheckRunQuerySet.missing_report`) so, instead of
                    # leaving the run looking merely "not generated yet" forever.
                    run.report_generation_error = ReportGenerationFailure.TOO_LARGE
                    run.report_generation_detail = str(exc.message)[:4000]
                    run.save(
                        update_fields=[
                            "report_generation_error",
                            "report_generation_detail",
                            "updated_at",
                        ]
                    )
                    self.log.warning(
                        "report_generation_failed",
                        run_id=str(run.uuid),
                        reason=run.report_generation_error,
                        detail=run.report_generation_detail[:200],
                    )
                    return run

            run.report_file = media
            # Cleared, not merely left alone: a retry that succeeds after an earlier
            # permanent-looking failure (a code change lowering the rendered size, or an
            # operator raising the cap) must not leave a stale error sitting beside a
            # file that now exists.
            run.report_generation_error = ""
            run.report_generation_detail = ""
            run.save(
                update_fields=[
                    "report_file",
                    "report_generation_error",
                    "report_generation_detail",
                    "updated_at",
                ]
            )

        self.log.info(
            "report_file_generated",
            run_id=str(run.uuid),
            media_id=str(media.uuid),
            language=run.tenant.language,
        )
        return run
