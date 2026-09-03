"""Deterministic checks for externally produced semantic candidates."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from cadgpt_regulations.errors import RegulationsError
from cadgpt_regulations.jsonio import JsonObject, load_object
from cadgpt_regulations.storage import read_regular_snapshot, safe_path

_PAGE_ID = re.compile(r":page:(?P<page>[0-9]{6}):")
_SPAN_COLLECTIONS = ("chars", "lines", "words")


class SemanticCheckError(RegulationsError):
    """Raised when model output is not bound to its declared source evidence."""


@dataclass(frozen=True)
class SemanticCheckResult:
    candidates: int
    source_span_references: int
    qualifier_span_references: int
    unique_span_references: int
    allowed_span_ids: int
    files_checked: int


def check_semantic_artifact(
    job_path: Path, artifact_path: Path, *, root: Path | None = None
) -> SemanticCheckResult:
    """Verify source IDs and immutable inputs without trusting model-written counts."""
    job_bytes = _read_bytes(job_path, description="semantic job")
    artifact_bytes = _read_bytes(artifact_path, description="semantic artifact")
    job = load_object(job_path, description="semantic job")
    artifact = load_object(artifact_path, description="semantic artifact")

    allowed_spans, pages, files_checked = _job_evidence(job, root=root)
    _validate_input_identity(artifact, hashlib.sha256(job_bytes).hexdigest())
    _validate_artifact_pages(artifact, pages)

    candidates = _candidate_records(artifact)
    candidate_ids: set[str] = set()
    source_refs: list[str] = []
    qualifier_refs: list[str] = []
    for index, candidate in enumerate(candidates):
        candidate_id = candidate.get("candidate_id")
        if not isinstance(candidate_id, str) or not candidate_id:
            raise SemanticCheckError(f"candidate {index} has no candidate_id")
        if candidate_id in candidate_ids:
            raise SemanticCheckError(f"duplicate candidate_id: {candidate_id}")
        candidate_ids.add(candidate_id)

        sources = _span_list(candidate, "source_span_ids", candidate_id=candidate_id)
        if not sources:
            raise SemanticCheckError(f"candidate {candidate_id} has no source spans")
        qualifiers = _span_list(candidate, "qualifier_span_ids", candidate_id=candidate_id)
        source_refs.extend(sources)
        qualifier_refs.extend(qualifiers)

    all_refs = source_refs + qualifier_refs
    unknown = sorted(set(all_refs) - allowed_spans)
    if unknown:
        raise SemanticCheckError(
            f"semantic artifact cites {len(unknown)} unknown span IDs; first={unknown[0]}"
        )
    for span_id in all_refs:
        match = _PAGE_ID.search(span_id)
        if match is None:
            raise SemanticCheckError(f"span ID has no PDF page identity: {span_id}")
        page = int(match.group("page"))
        if page not in pages:
            raise SemanticCheckError(f"span ID belongs to page outside the job: {span_id}")

    if not artifact_bytes:
        raise SemanticCheckError("semantic artifact is empty")
    return SemanticCheckResult(
        candidates=len(candidates),
        source_span_references=len(source_refs),
        qualifier_span_references=len(qualifier_refs),
        unique_span_references=len(set(all_refs)),
        allowed_span_ids=len(allowed_spans),
        files_checked=files_checked,
    )


def _job_evidence(job: JsonObject, *, root: Path | None) -> tuple[set[str], set[int], int]:
    raw_pages = job.get("pages")
    if not isinstance(raw_pages, list) or not raw_pages:
        raise SemanticCheckError("semantic job has no pages")
    pages = [cast(JsonObject, value) for value in raw_pages]
    if all("files" in page for page in pages):
        return _manifest_job_evidence(pages, root=root)
    if all("span_ids" in page for page in pages):
        return _bundle_job_evidence(job, pages, root=root)
    raise SemanticCheckError("semantic job page format is unsupported or mixed")


def _manifest_job_evidence(
    pages: list[JsonObject], *, root: Path | None
) -> tuple[set[str], set[int], int]:
    allowed: set[str] = set()
    page_numbers: set[int] = set()
    files_checked = 0
    for page in pages:
        page_number = _page_number(page)
        if page_number in page_numbers:
            raise SemanticCheckError(f"semantic job repeats PDF page {page_number}")
        page_numbers.add(page_number)
        files = page.get("files")
        if not isinstance(files, dict) or not files:
            raise SemanticCheckError(f"semantic job page {page_number} has no files")
        native_path: Path | None = None
        for role, raw_reference in files.items():
            if not isinstance(role, str) or not isinstance(raw_reference, dict):
                raise SemanticCheckError(f"invalid file entry on page {page_number}")
            reference = cast(JsonObject, raw_reference)
            path = _resolve_input_path(reference.get("path"), root=root)
            expected_sha256 = reference.get("sha256")
            expected_bytes = reference.get("bytes")
            if not isinstance(expected_sha256, str) or not isinstance(expected_bytes, int):
                raise SemanticCheckError(
                    f"file {role} on page {page_number} lacks hash or byte count"
                )
            snapshot = read_regular_snapshot(path)
            if snapshot.sha256 != expected_sha256 or snapshot.bytes != expected_bytes:
                raise SemanticCheckError(
                    f"file {role} on page {page_number} differs from its job record"
                )
            files_checked += 1
            if role == "native":
                native_path = path
        if native_path is None:
            raise SemanticCheckError(f"semantic job page {page_number} has no native file")
        native = load_object(native_path, description=f"native page {page_number}")
        allowed.update(_native_span_ids(native, page_number=page_number))
    return allowed, page_numbers, files_checked


def _bundle_job_evidence(
    job: JsonObject, pages: list[JsonObject], *, root: Path | None
) -> tuple[set[str], set[int], int]:
    allowed: set[str] = set()
    page_numbers: set[int] = set()
    files_checked = 0
    total_input_bytes = 0
    for page in pages:
        page_number = _page_number(page)
        if page_number in page_numbers:
            raise SemanticCheckError(f"semantic bundle repeats PDF page {page_number}")
        page_numbers.add(page_number)
        span_ids = page.get("span_ids")
        if not isinstance(span_ids, list) or not all(
            isinstance(span_id, str) for span_id in span_ids
        ):
            raise SemanticCheckError(f"bundle page {page_number} has invalid span_ids")
        allowed.update(cast(list[str], span_ids))

        page_input_bytes = 0
        for field in (
            "normalized_text_path",
            "raw_native_text_path",
            "model_render_path",
        ):
            value = page.get(field)
            if root is None:
                if not isinstance(value, str) or not value:
                    raise SemanticCheckError(
                        f"bundle page {page_number} has invalid {field}"
                    )
                continue
            path = _resolve_input_path(value, root=root)
            snapshot = read_regular_snapshot(path)
            if field != "raw_native_text_path":
                page_input_bytes += snapshot.bytes
            files_checked += 1
        expected_page_bytes = page.get("input_bytes")
        if root is not None and page_input_bytes != expected_page_bytes:
            raise SemanticCheckError(f"bundle page {page_number} input byte count is false")
        total_input_bytes += cast(int, expected_page_bytes)
    if total_input_bytes != job.get("input_bytes"):
        raise SemanticCheckError("bundle input byte total is false")
    return allowed, page_numbers, files_checked


def _native_span_ids(native: JsonObject, *, page_number: int) -> set[str]:
    result: set[str] = set()
    for collection_name in _SPAN_COLLECTIONS:
        collection = native.get(collection_name)
        if not isinstance(collection, list):
            raise SemanticCheckError(
                f"native page {page_number} has invalid {collection_name}"
            )
        for record in collection:
            if not isinstance(record, dict) or not isinstance(record.get("span_id"), str):
                raise SemanticCheckError(
                    f"native page {page_number} has an invalid span record"
                )
            span_id = cast(str, record["span_id"])
            if span_id in result:
                raise SemanticCheckError(
                    f"native page {page_number} repeats span ID {span_id}"
                )
            result.add(span_id)
    return result


def _candidate_records(artifact: JsonObject) -> list[JsonObject]:
    for field in ("candidates", "accepted_candidates"):
        value = artifact.get(field)
        if isinstance(value, list):
            if not all(isinstance(record, dict) for record in value):
                raise SemanticCheckError(f"semantic artifact {field} is invalid")
            return [cast(JsonObject, record) for record in value]
    raise SemanticCheckError("semantic artifact has no candidate collection")


def _span_list(candidate: JsonObject, field: str, *, candidate_id: str) -> list[str]:
    value = candidate.get(field, [])
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise SemanticCheckError(f"candidate {candidate_id} has invalid {field}")
    return cast(list[str], value)


def _page_number(page: JsonObject) -> int:
    value = page.get("pdf_page")
    if not isinstance(value, int) or value < 1:
        raise SemanticCheckError("semantic job has an invalid PDF page number")
    return value


def _validate_input_identity(artifact: JsonObject, actual_sha256: str) -> None:
    identities = [
        artifact[field]
        for field in ("input_job_sha256", "input_bundle_sha256")
        if field in artifact
    ]
    if len(identities) != 1 or not isinstance(identities[0], str):
        raise SemanticCheckError("semantic artifact has no unambiguous input hash")
    if identities[0] != actual_sha256:
        raise SemanticCheckError("semantic artifact input hash does not match its job")


def _validate_artifact_pages(artifact: JsonObject, expected: set[int]) -> None:
    value = artifact.get("pages")
    if value is None:
        return
    if not isinstance(value, list):
        raise SemanticCheckError("semantic artifact pages field is invalid")
    actual: set[int] = set()
    for record in value:
        if isinstance(record, int):
            actual.add(record)
        elif isinstance(record, dict) and isinstance(record.get("pdf_page"), int):
            actual.add(cast(int, record["pdf_page"]))
        else:
            raise SemanticCheckError("semantic artifact pages field is invalid")
    if actual != expected or len(value) != len(expected):
        raise SemanticCheckError("semantic artifact page coverage differs from its job")


def _resolve_input_path(value: Any, *, root: Path | None) -> Path:
    if not isinstance(value, str) or not value:
        raise SemanticCheckError("semantic job contains an invalid file path")
    path = Path(value)
    if path.is_absolute():
        if root is not None:
            try:
                path.relative_to(root)
            except ValueError as exc:
                raise SemanticCheckError(
                    f"input path escapes the artifact root: {path}"
                ) from exc
        return path
    if root is None:
        raise SemanticCheckError("relative job paths require an artifact root")
    return safe_path(root, value)


def _read_bytes(path: Path, *, description: str) -> bytes:
    try:
        return path.read_bytes()
    except OSError as exc:
        raise SemanticCheckError(f"cannot read {description} {path}: {exc}") from exc
