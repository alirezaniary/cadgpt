"""Build deterministic, complete inventories over local regulation artifacts."""

from __future__ import annotations

import hashlib
import os
import stat
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from cadgpt_regulations.catalog import load_catalog, validate_catalog
from cadgpt_regulations.errors import InventoryError
from cadgpt_regulations.jsonio import JsonObject, canonical_bytes, sha256_json
from cadgpt_regulations.pdf import detect_media_type, inspect_pdf

MANIFEST_SCHEMA_VERSION = "1.0.0"
_READ_CHUNK_SIZE = 1024 * 1024
_PROBE_SIZE = 4096


@dataclass(frozen=True)
class _FileSnapshot:
    digest: str
    byte_size: int
    prefix: bytes
    device: int
    inode: int
    modified_ns: int


def build_inventory(
    source_directory: Path, *, catalog: JsonObject | None = None
) -> JsonObject:
    """Account for every expected artifact and every file present in one directory."""
    curated = load_catalog() if catalog is None else catalog
    validate_catalog(curated)
    if not source_directory.is_dir():
        raise InventoryError(f"source directory does not exist: {source_directory}")

    try:
        discovered = sorted(
            (
                path
                for path in source_directory.rglob("*")
                if path.is_file() or path.is_symlink()
            ),
            key=lambda path: path.relative_to(source_directory).as_posix(),
        )
    except OSError as exc:
        raise InventoryError(
            f"cannot enumerate source directory {source_directory}: {exc}"
        ) from exc

    by_filename = {
        path.relative_to(source_directory).as_posix(): path for path in discovered
    }
    catalog_artifacts = cast(list[JsonObject], curated["artifacts"])
    expected_filenames = {
        cast(str, artifact["original_filename"]) for artifact in catalog_artifacts
    }

    records: list[JsonObject] = []
    for catalog_artifact in sorted(
        catalog_artifacts, key=lambda artifact: cast(int, artifact["catalog_order"])
    ):
        filename = cast(str, catalog_artifact["original_filename"])
        path = by_filename.get(filename)
        if path is None:
            records.append(_missing_record(catalog_artifact))
        else:
            records.append(_inspect_expected(path, catalog_artifact))

    next_order = max(
        (cast(int, artifact["catalog_order"]) for artifact in catalog_artifacts),
        default=0,
    )
    for offset, path in enumerate(
        (
            path
            for path in discovered
            if path.relative_to(source_directory).as_posix() not in expected_filenames
        ),
        start=1,
    ):
        records.append(
            _inspect_unaccounted(
                path,
                path.relative_to(source_directory).as_posix(),
                next_order + offset,
            )
        )

    summary = _summarize(records, expected_count=len(catalog_artifacts))
    return {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "catalog": {
            "catalog_id": curated["catalog_id"],
            "schema_version": curated["schema_version"],
            "sha256": sha256_json(curated),
            "provenance": curated["provenance"],
        },
        "summary": summary,
        "artifacts": records,
    }


def write_inventory(manifest: JsonObject, output: Path) -> None:
    """Write canonical JSON atomically without introducing a generation timestamp."""
    parent = output.parent
    try:
        parent_mode = parent.lstat().st_mode
    except OSError as exc:
        raise InventoryError(f"cannot inspect output directory {parent}: {exc}") from exc
    if not stat.S_ISDIR(parent_mode) or stat.S_ISLNK(parent_mode):
        raise InventoryError(f"output directory does not exist: {parent}")
    _reject_unsafe_output(output)

    temporary: Path | None = None
    descriptor: int | None = None
    try:
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{output.name}.", suffix=".tmp", dir=parent
        )
        temporary = Path(temporary_name)
        with os.fdopen(descriptor, "wb") as destination:
            descriptor = None
            destination.write(canonical_bytes(manifest))
            destination.flush()
            os.fsync(destination.fileno())
        _reject_unsafe_output(output)
        temporary.replace(output)
        temporary = None
    except InventoryError:
        raise
    except OSError as exc:
        raise InventoryError(f"cannot write inventory {output}: {exc}") from exc
    finally:
        if descriptor is not None:
            os.close(descriptor)
        if temporary is not None:
            try:
                temporary.unlink(missing_ok=True)
            except OSError as exc:
                raise InventoryError(
                    f"cannot remove incomplete inventory {temporary}: {exc}"
                ) from exc


def ensure_output_outside_source(source_directory: Path, output: Path) -> None:
    """Never let a generated manifest replace or join the source artifact set."""
    try:
        source = source_directory.resolve(strict=True)
        destination = output.resolve(strict=False)
    except OSError as exc:
        raise InventoryError(f"cannot resolve inventory paths: {exc}") from exc
    if destination.is_relative_to(source):
        raise InventoryError(
            "output must be outside the source directory and cannot overwrite "
            f"input: {output}"
        )


def _inspect_expected(path: Path, catalog_artifact: JsonObject) -> JsonObject:
    runtime = _inspect_file(
        path,
        cast(str, catalog_artifact["expected_media_type"]),
        cast(str, catalog_artifact["expected_sha256"]),
    )
    return _catalog_record(catalog_artifact) | runtime


def _inspect_unaccounted(path: Path, relative_name: str, catalog_order: int) -> JsonObject:
    runtime = _inspect_file(path, None)
    previous_error = cast(JsonObject | None, runtime["error"])
    diagnostic = "file is not represented in the curated catalog"
    if previous_error is not None:
        diagnostic = (
            f"{diagnostic}; {previous_error['code']}: {previous_error['diagnostic']}"
        )
    runtime["artifact_state"] = "quarantined"
    runtime["error"] = {
        "code": "UNACCOUNTED_ARTIFACT",
        "diagnostic": diagnostic,
    }
    return {
        "catalog_key": None,
        "catalog_order": catalog_order,
        "original_filename": relative_name,
        "document_kind": "unclassified",
        "volume": None,
        "title_fa": None,
        "title_en": None,
        "translation_provenance": None,
        "edition": _empty_edition(),
        "legal_status": "unknown",
        "relationships": [],
        "source_urls": [],
        "evidence": [],
        "review_status": "needs_review",
        "review_flags": ["UNACCOUNTED_ARTIFACT"],
        "expected_media_type": None,
        "expected_sha256": None,
    } | runtime


def _inspect_file(
    path: Path, expected_media_type: str | None, expected_sha256: str | None = None
) -> JsonObject:
    if path.is_symlink():
        return {
            "present": True,
            "sha256": None,
            "bytes": None,
            "detected_media_type": None,
            "artifact_state": "quarantined",
            "pdf_page_count": None,
            "error": {
                "code": "UNSUPPORTED_FILE_TYPE",
                "diagnostic": "symbolic links are not read as corpus artifacts",
            },
        }
    try:
        snapshot = _read_snapshot(path)
    except OSError as exc:
        return {
            "present": True,
            "sha256": None,
            "bytes": None,
            "detected_media_type": "application/octet-stream",
            "artifact_state": "quarantined",
            "pdf_page_count": None,
            "error": {
                "code": "FILE_READ_FAILED",
                "diagnostic": f"{type(exc).__name__}: {exc.strerror or 'read failed'}",
            },
        }

    if snapshot is None:
        return {
            "present": True,
            "sha256": None,
            "bytes": None,
            "detected_media_type": None,
            "artifact_state": "quarantined",
            "pdf_page_count": None,
            "error": {
                "code": "FILE_CHANGED_DURING_READ",
                "diagnostic": "file metadata or size changed while it was being hashed",
            },
        }

    media_type = detect_media_type(snapshot.prefix)
    base: JsonObject = {
        "present": True,
        "sha256": snapshot.digest,
        "bytes": snapshot.byte_size,
        "detected_media_type": media_type,
        "artifact_state": "ready",
        "pdf_page_count": None,
        "error": None,
    }
    if not _snapshot_is_current(path, snapshot):
        return _changed_file_record(
            "file changed immediately after hashing and content inspection"
        )
    if expected_sha256 is not None and snapshot.digest != expected_sha256:
        base["artifact_state"] = "quarantined"
        base["error"] = {
            "code": "SOURCE_HASH_MISMATCH",
            "diagnostic": (
                f"expected SHA-256 {expected_sha256}, calculated {snapshot.digest}"
            ),
        }
        return base
    if expected_media_type is not None and media_type != expected_media_type:
        base["artifact_state"] = "quarantined"
        base["error"] = {
            "code": "MEDIA_TYPE_MISMATCH",
            "diagnostic": f"expected {expected_media_type}, detected {media_type}",
        }
        return base
    if media_type != "application/pdf":
        base["artifact_state"] = "quarantined"
        base["error"] = {
            "code": "UNSUPPORTED_MEDIA_TYPE",
            "diagnostic": f"unsupported detected media type: {media_type}",
        }
        return base

    probe = inspect_pdf(path)
    if not _snapshot_is_current(path, snapshot):
        return _changed_file_record(
            "file changed between hashing and PDF metadata inspection"
        )
    base["pdf_page_count"] = probe.page_count
    if probe.error_code is not None:
        base["artifact_state"] = "quarantined"
        base["error"] = {
            "code": probe.error_code,
            "diagnostic": probe.diagnostic,
        }
    return base


def _missing_record(catalog_artifact: JsonObject) -> JsonObject:
    return _catalog_record(catalog_artifact) | {
        "present": False,
        "sha256": None,
        "bytes": None,
        "detected_media_type": None,
        "artifact_state": "quarantined",
        "pdf_page_count": None,
        "error": {
            "code": "EXPECTED_ARTIFACT_MISSING",
            "diagnostic": "expected catalog artifact is absent from the source directory",
        },
    }


def _catalog_record(catalog_artifact: JsonObject) -> JsonObject:
    return {
        "catalog_key": catalog_artifact["catalog_key"],
        "catalog_order": catalog_artifact["catalog_order"],
        "original_filename": catalog_artifact["original_filename"],
        "document_kind": catalog_artifact["document_kind"],
        "volume": catalog_artifact["volume"],
        "title_fa": catalog_artifact["title_fa"],
        "title_en": catalog_artifact["title_en"],
        "translation_provenance": catalog_artifact["translation_provenance"],
        "edition": catalog_artifact["edition"],
        "legal_status": catalog_artifact["legal_status"],
        "relationships": catalog_artifact["relationships"],
        "source_urls": catalog_artifact["source_urls"],
        "evidence": catalog_artifact["evidence"],
        "review_status": catalog_artifact["review_status"],
        "review_flags": catalog_artifact["review_flags"],
        "expected_media_type": catalog_artifact["expected_media_type"],
        "expected_sha256": catalog_artifact["expected_sha256"],
    }


def _empty_edition() -> JsonObject:
    return {
        "label_fa": None,
        "label_en": None,
        "edition_number": None,
        "publication_year_shamsi": None,
        "publication_date_shamsi": None,
    }


def _summarize(records: list[JsonObject], *, expected_count: int) -> JsonObject:
    actual_records = [record for record in records if record["present"]]
    matched_records = [
        record
        for record in actual_records
        if record["catalog_key"] is not None
        and _error_code(record) != "EXPECTED_ARTIFACT_MISSING"
    ]
    ready_pdfs = [
        record
        for record in records
        if record["artifact_state"] == "ready"
        and record["detected_media_type"] == "application/pdf"
    ]
    return {
        "expected_artifacts": expected_count,
        "files_discovered": len(actual_records),
        "artifacts_accounted": len(matched_records),
        "valid_pdfs": len(ready_pdfs),
        "quarantined": sum(record["artifact_state"] == "quarantined" for record in records),
        "missing": sum(
            _error_code(record) == "EXPECTED_ARTIFACT_MISSING" for record in records
        ),
        "unaccounted": sum(
            _error_code(record) == "UNACCOUNTED_ARTIFACT" for record in records
        ),
        "needs_review": sum(
            record["review_status"] == "needs_review" for record in records
        ),
        "pdf_pages": sum(cast(int, record["pdf_page_count"]) for record in ready_pdfs),
    }


def _error_code(record: JsonObject) -> str | None:
    error = cast(JsonObject | None, record["error"])
    return None if error is None else cast(str, error["code"])


def _read_snapshot(path: Path) -> _FileSnapshot | None:
    digest = hashlib.sha256()
    prefix = b""
    bytes_read = 0
    with path.open("rb") as source:
        before = os.fstat(source.fileno())
        while block := source.read(_READ_CHUNK_SIZE):
            if len(prefix) < _PROBE_SIZE:
                prefix += block[: _PROBE_SIZE - len(prefix)]
            bytes_read += len(block)
            digest.update(block)
        after = os.fstat(source.fileno())
    identity_before = (
        before.st_dev,
        before.st_ino,
        before.st_size,
        before.st_mtime_ns,
    )
    identity_after = (
        after.st_dev,
        after.st_ino,
        after.st_size,
        after.st_mtime_ns,
    )
    if identity_before != identity_after or bytes_read != after.st_size:
        return None
    return _FileSnapshot(
        digest=digest.hexdigest(),
        byte_size=bytes_read,
        prefix=prefix,
        device=after.st_dev,
        inode=after.st_ino,
        modified_ns=after.st_mtime_ns,
    )


def _snapshot_is_current(path: Path, snapshot: _FileSnapshot) -> bool:
    try:
        current = path.stat()
    except OSError:
        return False
    return (
        current.st_dev,
        current.st_ino,
        current.st_size,
        current.st_mtime_ns,
    ) == (
        snapshot.device,
        snapshot.inode,
        snapshot.byte_size,
        snapshot.modified_ns,
    )


def _changed_file_record(diagnostic: str) -> JsonObject:
    return {
        "present": True,
        "sha256": None,
        "bytes": None,
        "detected_media_type": None,
        "artifact_state": "quarantined",
        "pdf_page_count": None,
        "error": {
            "code": "FILE_CHANGED_DURING_READ",
            "diagnostic": diagnostic,
        },
    }


def _reject_unsafe_output(output: Path) -> None:
    try:
        mode = output.lstat().st_mode
    except FileNotFoundError:
        return
    except OSError as exc:
        raise InventoryError(f"cannot inspect inventory output {output}: {exc}") from exc
    if stat.S_ISLNK(mode) or not stat.S_ISREG(mode):
        raise InventoryError(f"inventory output is not a regular file: {output}")
