from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from django.db.models import Manager

from cadgpt.apps.review.repositories.querysets import CheckRunQuerySet, ReviewQuerySet

if TYPE_CHECKING:
    from cadgpt.apps.review.models import CheckRun, Review


class ReviewManager(Manager.from_queryset(ReviewQuerySet)):  # type: ignore[misc]
    def get_queryset(self) -> ReviewQuerySet:
        """Soft-deleted reviews are hidden by default; the safe view is the default one."""
        return cast(ReviewQuerySet, super().get_queryset()).alive()

    def create_review(
        self,
        *,
        tenant: Any,
        name: str,
        model_file: Any,
        rule_set: Any | None,
        created_by: Any | None,
    ) -> Review:
        review = self.model(
            tenant=tenant,
            name=name.strip(),
            model_file=model_file,
            rule_set=rule_set,
            created_by=created_by,
        )
        review.full_clean(exclude=["tenant", "model_file", "rule_set", "created_by"])
        review.save(using=self._db)
        return cast("Review", review)


class CheckRunManager(Manager.from_queryset(CheckRunQuerySet)):  # type: ignore[misc]
    def create_run(
        self,
        *,
        review: Any,
        requested_by: Any | None,
        rule_pack_selection: list[dict[str, Any]] | None = None,
    ) -> CheckRun:
        """A run starts PENDING, carrying a record of the exact rules it will read.

        Recording it at creation rather than at execution is what lets a completed run
        state which bytes it checked, even after the review is pointed at a new upload or
        the catalogue gains a newer version of a selected pack. `rule_set_checksum` is set
        only for the uploaded-rule-set path; a catalogue run's citation lives entirely in
        `rule_pack_selection`, already resolved by the caller (`ReviewService.
        request_check`) before this is called.
        """
        run = self.model(
            tenant=review.tenant,
            review=review,
            requested_by=requested_by,
            model_checksum=review.model_file.checksum_sha256,
            rule_set_checksum=(
                review.rule_set.source_file.checksum_sha256
                if review.rule_set_id is not None
                else ""
            ),
            rule_pack_selection=rule_pack_selection or [],
        )
        run.save(using=self._db)
        return cast("CheckRun", run)
