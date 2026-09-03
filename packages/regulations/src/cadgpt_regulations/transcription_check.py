"""Fail-closed accounting and re-attestation for transcription output."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from cadgpt_regulations.acquisition import validate_acquisition_receipt
from cadgpt_regulations.catalog import load_catalog
from cadgpt_regulations.errors import ManifestError, RegulationsError, TranscriptionError
from cadgpt_regulations.jsonio import (
    JsonObject,
    canonical_bytes,
    loads_object,
    sha256_json,
    validate_schema,
)
from cadgpt_regulations.page_probe import validate_page_probe
from cadgpt_regulations.resources import load_packaged_json
from cadgpt_regulations.storage import (
    InstallStatus,
    StorageError,
    ensure_private_tree,
    install_immutable_bytes,
    read_attested_bytes,
    safe_path,
    validate_output_root,
)
from cadgpt_regulations.store_index import validate_output_inventory
from cadgpt_regulations.transcription import validate_transcription


@dataclass(frozen=True)
class CheckRun:
    report: JsonObject
    report_path: Path
    report_created: bool


def check_transcription(
    manifest: JsonObject,
    *,
    root: Path,
    acquisition_root: Path,
    catalog: JsonObject | None = None,
) -> CheckRun:
    """Return and persist every available blocker without publishing uncertain pages."""
    curated = load_catalog() if catalog is None else catalog
    blockers: list[JsonObject] = []
    acquisition: JsonObject | None = None
    probe: JsonObject | None = None
    try:
        validate_output_root(root)
    except StorageError as exc:
        blockers.append(_blocker("output", "OUTPUT_ROOT_UNSAFE", exc))
    try:
        acquisition_payload, _ = read_attested_bytes(
            safe_path(acquisition_root, "acquisition.json")
        )
        acquisition = loads_object(
            acquisition_payload.decode("utf-8"), description="acquisition receipt"
        )
        validate_acquisition_receipt(acquisition, catalog=curated, root=acquisition_root)
    except (RegulationsError, StorageError, UnicodeError) as exc:
        blockers.append(_blocker("acquisition", "ACQUISITION_INVALID", exc))
    try:
        probe_sha256 = cast(str, cast(JsonObject, manifest["probe"])["sha256"])
        probe_path = safe_path(root, f"manifests/page-probe/{probe_sha256}.json")
        probe_payload, _ = read_attested_bytes(probe_path, expected_sha256=probe_sha256)
        probe = loads_object(probe_payload.decode("utf-8"), description="page probe")
        validate_page_probe(probe, root=root, acquisition=acquisition)
    except (KeyError, TypeError, RegulationsError, StorageError, UnicodeError) as exc:
        blockers.append(_blocker("page-probe", "PAGE_PROBE_INVALID", exc))
    try:
        validate_transcription(manifest, root=root, probe=probe)
    except (RegulationsError, StorageError) as exc:
        blockers.append(_blocker("transcription", "TRANSCRIPTION_INVALID", exc))
    try:
        validate_output_inventory(root)
    except (RegulationsError, StorageError) as exc:
        blockers.append(_blocker("output", "OUTPUT_INVENTORY_INVALID", exc))

    documents = manifest.get("documents", [])
    pages = (
        [
            page
            for document in documents
            if isinstance(document, dict)
            for page in document.get("pages", [])
            if isinstance(page, dict)
        ]
        if isinstance(documents, list)
        else []
    )
    report: JsonObject = {
        "schema_version": "1.0.0",
        "transcription_sha256": sha256_json(manifest),
        "valid": not blockers,
        "summary": {
            "documents_observed": len(documents) if isinstance(documents, list) else 0,
            "pages_observed": len(pages),
            "pages_ready": sum(page.get("state") == "ready" for page in pages),
            "pages_needs_review": sum(
                page.get("state") == "needs_review" for page in pages
            ),
            "pages_failed": sum(page.get("state") == "failed" for page in pages),
            "blockers": len(blockers),
        },
        "blockers": blockers,
    }
    try:
        validate_schema(
            report,
            load_packaged_json(
                "cadgpt_regulations.schemas", "transcription-check.schema.json"
            ),
            description="transcription check",
        )
    except ManifestError as exc:
        raise TranscriptionError(str(exc)) from exc
    report_path, created = _install_report(root, report)
    return CheckRun(report=report, report_path=report_path, report_created=created)


def _blocker(subject: str, code: str, exc: BaseException) -> JsonObject:
    return {
        "subject": subject,
        "code": code,
        "diagnostic": f"{type(exc).__name__}: {exc}"[:1000],
    }


def _install_report(root: Path, report: JsonObject) -> tuple[Path, bool]:
    payload = canonical_bytes(report)
    digest = hashlib.sha256(payload).hexdigest()
    relative = Path("checks") / "transcription" / f"{digest}.json"
    index_relative = Path("indexes") / "transcription-check" / f"{digest}.json"
    index: JsonObject = {
        "schema_version": "1.0.0",
        "kind": "transcription_check",
        "report_path": relative.as_posix(),
        "report_sha256": digest,
        "transcription_sha256": report["transcription_sha256"],
    }
    try:
        ensure_private_tree(root, relative.parent.as_posix())
        ensure_private_tree(root, index_relative.parent.as_posix())
        result = install_immutable_bytes(safe_path(root, relative.as_posix()), payload)
        install_immutable_bytes(
            safe_path(root, index_relative.as_posix()), canonical_bytes(index)
        )
    except StorageError as exc:
        raise TranscriptionError(str(exc)) from exc
    return safe_path(root, relative.as_posix()), result.status is InstallStatus.INSTALLED
