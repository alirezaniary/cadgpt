"""Storing an upload, and handing it back to code that needs a real file on disk."""

from __future__ import annotations

import contextlib
import hashlib
from collections.abc import Iterator
from pathlib import Path, PurePosixPath
from typing import Any

from django.conf import settings
from django.core.files.uploadedfile import UploadedFile
from django.template.defaultfilters import filesizeformat
from django.utils.translation import gettext_lazy as _

from cadgpt.apps.account.models import User
from cadgpt.apps.base.exceptions import ValidationError
from cadgpt.apps.base.files import local_path as _local_path
from cadgpt.apps.base.services import BaseTenantAwareService
from cadgpt.apps.media.constants import ALLOWED_EXTENSIONS, CHECKSUM_CHUNK_BYTES, MAX_BYTES
from cadgpt.apps.media.models import Media


class MediaService(BaseTenantAwareService):
    """The only way a file enters the system."""

    def store(
        self, *, upload: UploadedFile[Any], kind: str, uploaded_by: User | None = None
    ) -> Media:
        self._validate(upload, kind)
        checksum, size = self._digest(upload)

        media = Media.objects.store(
            tenant=self.tenant,
            file=upload,
            kind=kind,
            original_name=upload.name or "unnamed",
            content_type=upload.content_type or "",
            size_bytes=size,
            checksum_sha256=checksum,
            uploaded_by=uploaded_by,
        )
        self.log.info(
            "media_stored",
            media_id=str(media.uuid),
            kind=kind,
            size_bytes=size,
            checksum=checksum,
        )
        return media

    @contextlib.contextmanager
    def local_path(self, media: Media) -> Iterator[Path]:
        """Yield a filesystem path for `media`, downloading it only if it is remote.

        The checking engine works on paths, because `ifcopenshell` parses from a file.
        Callers get one contract either way, so the worker does not have to know where
        files live. The actual fallback -- stream to a temporary file only when the
        storage backend offers no real path -- lives in `cadgpt.apps.base.files`, shared
        with `rulepack.services.RulePackService.local_path` for the same reason.
        """
        with _local_path(media.file, media.original_name) as path:
            yield path

    def _validate(self, upload: UploadedFile[Any], kind: str) -> None:
        if kind not in ALLOWED_EXTENSIONS:
            raise ValidationError(_("That kind of file is not accepted."))

        suffix = PurePosixPath(upload.name or "").suffix.lower()
        if suffix not in ALLOWED_EXTENSIONS[kind]:
            allowed = ", ".join(sorted(ALLOWED_EXTENSIONS[kind]))
            raise ValidationError(
                _("This file type is not accepted here. Expected one of: %(allowed)s.")
                % {"allowed": allowed},
                details={"file": [f"unexpected extension {suffix!r}"]},
            )

        limit = MAX_BYTES.get(kind, settings.MAX_UPLOAD_BYTES)
        if upload.size is None or upload.size > limit:
            # In human units: "larger than the 536870912 byte limit" is a number no
            # architect can act on (T-0033). `filesizeformat` is itself translated, so
            # "MB"/"GB" read correctly in either locale without a second lookup table.
            raise ValidationError(
                _("This file is larger than the %(limit)s limit.")
                % {"limit": filesizeformat(limit)},
                details={"file": ["too large"]},
            )
        if upload.size == 0:
            raise ValidationError(_("The uploaded file is empty."))

    def _digest(self, upload: UploadedFile[Any]) -> tuple[str, int]:
        """SHA-256 and byte count, read in chunks so a large model never sits in memory."""
        digest = hashlib.sha256()
        size = 0
        upload.seek(0)
        for chunk in upload.chunks(CHECKSUM_CHUNK_BYTES):
            digest.update(chunk)
            size += len(chunk)
        upload.seek(0)
        return digest.hexdigest(), size
