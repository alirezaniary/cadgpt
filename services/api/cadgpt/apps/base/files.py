"""Materializing a stored file as a real path on disk.

`ifcopenshell` and `ifctester` read from a filesystem path, because that is what the
checking engine's CLI takes. On local storage this hands back the file's own path and
copies nothing; on object storage it streams to a temporary file and removes it
afterwards. Both `media.Media` and `rulepack.RulePack` store their file through a plain
Django `FileField`, so this is the one place that logic lives -- `MediaService.local_path`
and `RulePackService.local_path` both delegate here rather than each keeping their own
copy of the same fallback.
"""

from __future__ import annotations

import contextlib
import shutil
import tempfile
from collections.abc import Iterator
from pathlib import Path, PurePosixPath
from typing import Any

#: Read size when copying to a temporary file. Large enough to be fast, small enough that
#: a large model never sits in memory -- matches `media.constants.CHECKSUM_CHUNK_BYTES`.
COPY_CHUNK_BYTES = 1024 * 1024


@contextlib.contextmanager
def local_path(file_field: Any, display_name: str) -> Iterator[Path]:
    """Yield a filesystem path for `file_field`, downloading it only if it is remote.

    The shortcut requires a file that is actually readable, not a backend that merely
    offers a `path` attribute. Django's in-memory storage offers one and writes nothing
    behind it, and an S3 backend can be configured with a location too -- so trusting the
    attribute yields a path to a file that is not there, and the caller gets a parse error
    about the user's upload instead of about our storage.
    """
    storage_path = _readable_path(file_field)
    if storage_path is not None:
        yield storage_path
        return

    suffix = PurePosixPath(display_name).suffix.lower()[:16]
    handle = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)  # noqa: SIM115
    try:
        with handle:
            file_field.open("rb")
            try:
                shutil.copyfileobj(file_field, handle, COPY_CHUNK_BYTES)
            finally:
                file_field.close()
        yield Path(handle.name)
    finally:
        Path(handle.name).unlink(missing_ok=True)


def _readable_path(file_field: Any) -> Path | None:
    """The backing file's own path, but only if it exists and can be opened."""
    try:
        candidate = Path(file_field.path)
    except (NotImplementedError, ValueError, AttributeError):
        return None
    return candidate if candidate.is_file() else None
