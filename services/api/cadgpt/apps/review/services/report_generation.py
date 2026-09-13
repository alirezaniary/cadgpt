"""Generating the Markdown report file for a succeeded check run, and storing it.

Idempotency is the contract, the same way it is for `CheckRunExecutor`: `acks_late` means a
message survives a worker that dies mid-task and is delivered again, so `generate` must
reach the same end state whether it runs once or five times. A sequential redelivery -- the
overwhelmingly common case, since it follows the same worker recovering or a user asking
again after the first attempt already finished -- is caught up front: the row is locked,
`report_file_id` is checked, and a run that already has one returns immediately without
rendering or storing anything. A redelivery that arrives *while an earlier attempt is still
rendering and storing* (see "No transaction spans the storage write" below for why that
window exists at all) is caught later instead, by `_attach` re-checking under a fresh lock
before it writes. Either way: one file ends up referenced, never two, never half-written.

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

**No transaction spans the storage write (T-0054).** `MediaService.store` writes bytes to
storage as part of `Media.save()`, ahead of the row's own `INSERT` -- a write no
`atomic()` block can rewind, because the storage backend keeps no transaction of its own.
Wrapping that write in the same `atomic()` block that also claims the run and later
updates it meant a crash between the write and that block's own commit rolled back the
`Media` row while the bytes it named stayed on disk: orphaned, invisible to any query, and
a redelivery would write a second one beside it. `generate` therefore renders and claims
the run in one short transaction, calls `MediaService.store` with no transaction open at
all, and attaches the result in a second short transaction -- by the time `store` returns,
either both the file and its `Media` row exist, or neither does, because there is no outer
transaction left for a later exception to roll back through. The row lock is dropped
across that gap, so `_attach` re-checks `report_file_id` under a fresh lock before writing
it: a concurrent redelivery that renders and stores in the same window is not a duplicate
kept forever, it is a redundant `Media` this call deletes outright rather than leaving
unreferenced.

That still leaves one gap of its own: a worker dying between `store` returning and
`_attach` committing leaves a `Media` row that is real, valid and committed, but not yet
referenced by any run -- a fundamentally smaller problem than the original bug (this one
is a normal row a query can find) but still not nothing. `_find_reusable_media` closes it
using the checksum `MediaService.store` already computes for every file: rendering is
deterministic for a given run and language, so a redelivery's markdown is byte-identical
to the attempt that stored it, and `generate` looks for an unattached `Media` with that
exact checksum before storing a new one. Recovery from that narrow crash window is
therefore a reuse, not a second file.
"""

from __future__ import annotations

import hashlib
import uuid as uuid_lib
from typing import cast

from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import transaction
from django.utils import translation

from cadgpt.apps.base.exceptions import NotFoundError, ValidationError
from cadgpt.apps.base.services import BaseService
from cadgpt.apps.media.choices import MediaKind
from cadgpt.apps.media.models import Media
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
                .select_related("tenant", "review", "report_file")
                .filter(uuid=run_uuid)
                .first()
            )
            if found is None:
                raise NotFoundError(f"No check run with uuid {run_uuid}.")
            run = cast("CheckRun", found)

            if run.report_file_id is not None:
                assert run.report_file is not None  # report_file_id set, checked above
                # `media_id` names the `Media` **uuid** everywhere in this module, never
                # the primary key (T-0054) -- the same identifier `MediaService.store`
                # logs, the one embedded in the storage path, and the one
                # `generate_report_file` returns.
                self.log.info(
                    "report_file_already_generated",
                    run_id=str(run.uuid),
                    media_id=str(run.report_file.uuid),
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
                # T-0055: the file identifies its own run and judgement time in its body.
                # `run.finished_at` is set in the same transaction as `run.status =
                # SUCCEEDED` (`CheckRunExecutor._succeed`), so a run reaching this branch
                # (status already checked as SUCCEEDED, above) always has one.
                assert run.finished_at is not None  # set with SUCCEEDED, in the same commit
                markdown = render_markdown_report(
                    localized,
                    run.rule_pack_selection,
                    run_uuid=run.uuid,
                    checked_at=run.finished_at,
                )
        # The transaction above has committed and the row lock is released by the time
        # this line runs -- see the module docstring's "No transaction spans the storage
        # write" for why that is deliberate, not an oversight.

        encoded = markdown.encode("utf-8")
        checksum = hashlib.sha256(encoded).hexdigest()
        media = self._find_reusable_media(run, checksum)
        if media is None:
            upload = SimpleUploadedFile(
                f"report-{run.uuid}.md", encoded, content_type="text/markdown"
            )
            # Still under the tenant's language (T-0051): the exception text this can
            # raise is persisted (`report_generation_detail`) as part of this run's
            # terminal state, and that state is written once, exactly like the file
            # would have been -- the same "language decision" the module docstring
            # names, extended to the failure case it did not have to consider before.
            with translation.override(run.tenant.language):
                try:
                    media = MediaService(tenant=run.tenant).store(
                        upload=upload, kind=MediaKind.REPORT
                    )
                except ValidationError as exc:
                    return self._record_failure(run, exc)

        return self._attach(run, media)

    def _find_reusable_media(self, run: CheckRun, checksum: str) -> Media | None:
        """An unattached `Media` row already carrying this exact rendered content.

        See the module docstring's closing paragraph: this exists for the narrow window
        between an earlier attempt's `MediaService.store` returning and its `_attach`
        committing, where a worker died in between. Reusing the row it already wrote
        turns a redelivery's recovery into a no-op retry instead of a second file next
        to an orphan.
        """
        attached_ids = CheckRun.objects.exclude(report_file=None).values("report_file_id")
        return cast(
            "Media | None",
            Media.objects.for_tenant(run.tenant)
            .of_kind(MediaKind.REPORT)
            .with_checksum(checksum)
            .exclude(pk__in=attached_ids)
            .first(),
        )

    def _record_failure(self, run: CheckRun, exc: ValidationError) -> CheckRun:
        """A check that genuinely found what it found is not retro-failed because its
        rendering did not fit in storage -- the run stays SUCCEEDED. This is the
        terminal, not-retryable state that tells a user (and
        `CheckRunQuerySet.missing_report`) so, instead of leaving the run looking merely
        "not generated yet" forever.
        """
        with transaction.atomic():
            locked = cast(
                "CheckRun",
                CheckRun.objects.select_for_update(of=("self",))
                .select_related("report_file")
                .get(pk=run.pk),
            )
            if locked.report_file_id is not None:
                # Another delivery succeeded while this one was rendering and hitting
                # the size cap -- the run already has a file; this delivery's failure is
                # moot, not news.
                return locked
            locked.report_generation_error = ReportGenerationFailure.TOO_LARGE
            locked.report_generation_detail = str(exc.message)[:4000]
            locked.save(
                update_fields=[
                    "report_generation_error",
                    "report_generation_detail",
                    "updated_at",
                ]
            )
        self.log.warning(
            "report_generation_failed",
            run_id=str(locked.uuid),
            reason=locked.report_generation_error,
            detail=locked.report_generation_detail[:200],
        )
        return locked

    def _attach(self, run: CheckRun, media: Media) -> CheckRun:
        """Record `media` as `run`'s report file, under a freshly acquired lock.

        The lock dropped between the claim above and here is exactly the gap a
        concurrent redelivery could have rendered and stored into. Re-checking
        `report_file_id` here is what keeps that race from producing a `Media` row
        nothing will ever reference: the loser deletes the file and row it just wrote
        instead of abandoning them.
        """
        with transaction.atomic():
            locked = cast(
                "CheckRun",
                CheckRun.objects.select_for_update(of=("self",))
                .select_related("tenant", "report_file")
                .get(pk=run.pk),
            )
            if locked.report_file_id is not None:
                assert locked.report_file is not None  # report_file_id set, above
                media.file.delete(save=False)
                media.delete()
                self.log.info(
                    "report_file_already_generated",
                    run_id=str(locked.uuid),
                    media_id=str(locked.report_file.uuid),
                )
                return locked

            locked.report_file = media
            # Cleared, not merely left alone: a retry that succeeds after an earlier
            # permanent-looking failure (a code change lowering the rendered size, or an
            # operator raising the cap) must not leave a stale error sitting beside a
            # file that now exists.
            locked.report_generation_error = ""
            locked.report_generation_detail = ""
            locked.save(
                update_fields=[
                    "report_file",
                    "report_generation_error",
                    "report_generation_detail",
                    "updated_at",
                ]
            )

        self.log.info(
            "report_file_generated",
            run_id=str(locked.uuid),
            media_id=str(media.uuid),
            language=locked.tenant.language,
        )
        return locked
