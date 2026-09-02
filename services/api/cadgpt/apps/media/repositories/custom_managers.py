from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from django.db.models import Manager

from cadgpt.apps.media.repositories.querysets import MediaQuerySet

if TYPE_CHECKING:
    from cadgpt.apps.media.models import Media


class MediaManager(Manager.from_queryset(MediaQuerySet)):  # type: ignore[misc]
    """Thin write wrapper. Whether a file may be stored was decided by the service."""

    def store(
        self,
        *,
        tenant: Any,
        file: Any,
        kind: str,
        original_name: str,
        content_type: str,
        size_bytes: int,
        checksum_sha256: str,
        uploaded_by: Any | None,
    ) -> Media:
        media = self.model(
            tenant=tenant,
            kind=kind,
            original_name=original_name[:255],
            content_type=content_type[:128],
            size_bytes=size_bytes,
            checksum_sha256=checksum_sha256,
            uploaded_by=uploaded_by,
        )
        media.file = file
        media.save(using=self._db)
        return cast("Media", media)
