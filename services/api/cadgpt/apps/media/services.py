"""Storing an upload, and handing it back to code that needs a real file on disk."""

from __future__ import annotations

import contextlib
import hashlib
import shutil
import tempfile
from collections.abc import Iterator
from pathlib import Path, PurePosixPath
from typing import Any

from django.conf import settings
from django.core.files.uploadedfile import UploadedFile
from django.utils.translation import gettext_lazy as _

from cadgpt.apps.account.models import User
from cadgpt.apps.base.exceptions import ValidationError
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

        The checking engine works on paths, because `ifcopenshell` parses from a file. On
        a local filesystem backend this hands over the real path and copies nothing; on
        object storage it streams to a temporary file and deletes it afterwards. Callers
        get one contract either way, so the worker does not have to know where files live.

        The shortcut requires a file that is actually readable, not a backend that merely
        offers a `path` attribute. Django's in-memory storage offers one and writes
        nothing behind it, and an S3 backend can be configured with a location too -- so
        trusting the attribute yields a path to a file that is not there, and the caller
        gets a parse error about the user's upload instead of about our storage.
        """
        storage_path = self._readable_path(media)
        if storage_path is not None:
            yield storage_path
            return

        suffix = PurePosixPath(media.original_name).suffix.lower()[:16]
        handle = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)  # noqa: SIM115
        try:
            with handle:
                media.file.open("rb")
                try:
                    shutil.copyfileobj(media.file, handle, CHECKSUM_CHUNK_BYTES)
                finally:
                    media.file.close()
            yield Path(handle.name)
        finally:
            Path(handle.name).unlink(missing_ok=True)

    @staticmethod
    def _readable_path(media: Media) -> Path | None:
        """The backing file's own path, but only if it exists and can be opened."""
        try:
            candidate = Path(media.file.path)
        except (NotImplementedError, ValueError, AttributeError):
            return None
        return candidate if candidate.is_file() else None

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
            raise ValidationError(
                _("This file is larger than the %(limit)d byte limit.") % {"limit": limit},
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
