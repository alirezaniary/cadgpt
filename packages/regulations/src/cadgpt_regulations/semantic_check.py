"""Deterministic checks for externally produced semantic candidates."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from cadgpt_regulations.errors import ManifestError, RegulationsError
from cadgpt_regulations.jsonio import JsonObject, load_object, validate_schema
from cadgpt_regulations.resources import load_packaged_json
from cadgpt_regulations.storage import (
    StorageError,
    read_attested_bytes,
    read_regular_snapshot,
    safe_path,
)

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
    job_path: Path,
    artifact_path: Path,
    *,
    root: Path | None = None,
    structure_binding: JsonObject | None = None,
    structure_root: Path | None = None,
) -> SemanticCheckResult:
    """Verify source IDs and immutable inputs without trusting model-written counts."""
    job_bytes = _read_bytes(job_path, description="semantic job")
    artifact_bytes = _read_bytes(artifact_path, description="semantic artifact")
    job = load_object(job_path, description="semantic job")
    artifact = load_object(artifact_path, description="semantic artifact")

    allowed_spans, pages, files_checked = _job_evidence(job, root=root)
    _validate_input_identity(
        artifact,
        hashlib.sha256(job_bytes).hexdigest(),
        structural=structure_binding is not None,
    )
    _validate_artifact_pages(artifact, pages)

    candidates = _candidate_records(artifact)
    structure_ids = _job_structure_ids(
        structure_binding if structure_binding is not None else job
    )
    structure_records: dict[str, dict[str, JsonObject]] | None = None
    if structure_binding is not None:
        if structure_root is None:
            raise SemanticCheckError("structured semantic check requires structure_root")
        path = _resolve_input_path(
            structure_binding.get("structural_bundle_path"), root=structure_root
        )
        snapshot = read_regular_snapshot(path)
        if snapshot.sha256 != structure_binding.get("structural_bundle_sha256"):
            raise SemanticCheckError("structural bundle differs from its job binding")
        try:
            payload, _ = read_attested_bytes(
                path,
                expected_sha256=snapshot.sha256,
                expected_bytes=snapshot.bytes,
            )
            structural_bundle = load_object(path, description="structural semantic bundle")
            validate_schema(
                structural_bundle,
                load_packaged_json(
                    "cadgpt_regulations.schemas", "structural-bundle.schema.json"
                ),
                description="structural semantic bundle",
            )
        except (ManifestError, StorageError) as exc:
            raise SemanticCheckError(f"invalid structural semantic bundle: {exc}") from exc
        if hashlib.sha256(payload).hexdigest() != snapshot.sha256:
            raise SemanticCheckError("structural bundle bytes are not stable")
        structure_records = _structural_records(structural_bundle)
        if structure_ids is None:
            raise SemanticCheckError("structured job has no structural IDs")
        for field, ids in structure_ids.items():
            if set(structure_records[field]) != ids:
                raise SemanticCheckError(f"structural job {field} differs from bundle")
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
        if structure_ids is not None:
            source_node_ids = candidate.get("source_node_ids")
            if not isinstance(source_node_ids, list) or not source_node_ids:
                raise SemanticCheckError(
                    f"candidate {candidate_id} must cite source_node_ids"
                )
            for field, allowed_key in (
                ("source_node_ids", "node_ids"),
                ("formula_ids", "formula_ids"),
                ("table_ids", "table_ids"),
                ("unit_ids", "unit_ids"),
                ("abbreviation_ids", "abbreviation_ids"),
            ):
                values = candidate.get(field, [])
                if not isinstance(values, list) or not all(
                    isinstance(item, str) for item in values
                ):
                    raise SemanticCheckError(
                        f"candidate {candidate_id} has invalid {field}"
                    )
                unknown_ids = sorted(set(values) - structure_ids[allowed_key])
                if unknown_ids:
                    raise SemanticCheckError(
                        f"candidate {candidate_id} cites unknown {field}: {unknown_ids[0]}"
                    )
            if candidate.get("kind") in {"formula", "equation"} and not candidate.get(
                "formula_ids"
            ):
                raise SemanticCheckError(f"candidate {candidate_id} must cite formula_ids")
            if candidate.get("kind") in {"table", "table_value"} and not candidate.get(
                "table_ids"
            ):
                raise SemanticCheckError(f"candidate {candidate_id} must cite table_ids")
            if structure_records is not None:
                referenced = [
                    structure_records["node_ids"][item]
                    for item in cast(list[str], source_node_ids)
                ]
                for field in (
                    "formula_ids",
                    "table_ids",
                    "unit_ids",
                    "abbreviation_ids",
                ):
                    referenced.extend(
                        structure_records[field][item]
                        for item in cast(list[str], candidate.get(field, []))
                    )
                referenced_spans = {
                    span
                    for record in referenced
                    for span in cast(list[str], record.get("source_span_ids", []))
                }
                if not referenced_spans.issubset(set(sources + qualifiers)):
                    raise SemanticCheckError(
                        f"candidate {candidate_id} omits a structural source anchor"
                    )
                structural_pages = {cast(int, record["pdf_page"]) for record in referenced}
                cited_pages = {
                    int(match.group("page"))
                    for span in sources + qualifiers
                    if (match := _PAGE_ID.search(span)) is not None
                }
                if not structural_pages.issubset(cited_pages):
                    raise SemanticCheckError(
                        f"candidate {candidate_id} structural pages differ from spans"
                    )
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
    if all("blocks" in page for page in pages):
        return _structural_bundle_evidence(job, pages, root=root)
    if all("files" in page for page in pages):
        return _manifest_job_evidence(pages, root=root)
    if all("span_ids" in page for page in pages):
        return _bundle_job_evidence(job, pages, root=root)
    raise SemanticCheckError("semantic job page format is unsupported or mixed")


def _structural_bundle_evidence(
    job: JsonObject, pages: list[JsonObject], *, root: Path | None
) -> tuple[set[str], set[int], int]:
    allowed: set[str] = set()
    page_numbers: set[int] = set()
    files_checked = 0
    for page in pages:
        page_number = _page_number(page)
        if page_number in page_numbers:
            raise SemanticCheckError(f"structural bundle repeats PDF page {page_number}")
        page_numbers.add(page_number)
        blocks = page.get("blocks")
        if not isinstance(blocks, list):
            raise SemanticCheckError(f"structural page {page_number} has no blocks")
        for block in blocks:
            if not isinstance(block, dict):
                raise SemanticCheckError(
                    f"structural page {page_number} has an invalid block"
                )
            spans = block.get("source_span_ids")
            if not isinstance(spans, list) or not all(
                isinstance(span, str) for span in spans
            ):
                raise SemanticCheckError(
                    f"structural page {page_number} has invalid block spans"
                )
            allowed.update(cast(list[str], spans))
            alternate_spans = block.get("alternate_source_span_ids", [])
            if not isinstance(alternate_spans, list) or not all(
                isinstance(span, str) for span in alternate_spans
            ):
                raise SemanticCheckError(
                    f"structural page {page_number} has invalid alternate spans"
                )
            allowed.update(cast(list[str], alternate_spans))
        artifacts = page.get("source_artifacts", [])
        if not isinstance(artifacts, list):
            raise SemanticCheckError(f"structural page {page_number} has invalid artifacts")
        for artifact in artifacts:
            if not isinstance(artifact, dict):
                raise SemanticCheckError(
                    f"structural page {page_number} has invalid artifact"
                )
            if root is None:
                continue
            path = _resolve_input_path(artifact.get("path"), root=root)
            snapshot = read_regular_snapshot(path)
            if snapshot.sha256 != artifact.get("sha256") or snapshot.bytes != artifact.get(
                "bytes"
            ):
                raise SemanticCheckError(f"structural page {page_number} artifact differs")
            files_checked += 1
    for field in ("formulas", "tables", "units", "abbreviations"):
        for item in cast(list[JsonObject], job.get(field, [])):
            spans = item.get("source_span_ids")
            if isinstance(spans, list):
                allowed.update(cast(list[str], spans))
    return allowed, page_numbers, files_checked


def _job_structure_ids(job: JsonObject) -> dict[str, set[str]] | None:
    raw = job.get("structure")
    if raw is None and all(
        field in job
        for field in ("page_ids", "node_ids", "formula_ids", "table_ids", "unit_ids")
    ):
        raw = job
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise SemanticCheckError("semantic job structure binding is invalid")
    result: dict[str, set[str]] = {}
    for field in ("page_ids", "node_ids", "formula_ids", "table_ids", "unit_ids"):
        values = raw.get(field)
        if not isinstance(values, list) or not all(
            isinstance(item, str) for item in values
        ):
            raise SemanticCheckError(f"semantic job structure {field} is invalid")
        result[field] = set(cast(list[str], values))
    # Abbreviations were added after the initial structural binding contract.
    # Treat the field as optional for old jobs while validating it when present.
    values = raw.get("abbreviation_ids", [])
    if not isinstance(values, list) or not all(isinstance(item, str) for item in values):
        raise SemanticCheckError("semantic job structure abbreviation_ids is invalid")
    result["abbreviation_ids"] = set(cast(list[str], values))
    return result


def _structural_records(
    bundle: JsonObject,
) -> dict[str, dict[str, JsonObject]]:
    """Index the canonical bundle records used for source-anchor checks."""
    collections: dict[str, tuple[str, list[JsonObject]]] = {
        "page_ids": (
            "page_id",
            [page for page in cast(list[JsonObject], bundle["pages"])],
        ),
        "formula_ids": (
            "formula_id",
            [item for item in cast(list[JsonObject], bundle["formulas"])],
        ),
        "table_ids": (
            "table_id",
            [item for item in cast(list[JsonObject], bundle["tables"])],
        ),
        "unit_ids": (
            "unit_id",
            [item for item in cast(list[JsonObject], bundle["units"])],
        ),
        "abbreviation_ids": (
            "abbreviation_id",
            [item for item in cast(list[JsonObject], bundle.get("abbreviations", []))],
        ),
    }
    blocks = [
        block
        for page in cast(list[JsonObject], bundle["pages"])
        for block in cast(list[JsonObject], page["blocks"])
    ]
    collections["node_ids"] = ("node_id", blocks)

    result: dict[str, dict[str, JsonObject]] = {}
    for collection_name, (id_field, records) in collections.items():
        indexed: dict[str, JsonObject] = {}
        for record in records:
            item_id = record.get(id_field)
            if not isinstance(item_id, str) or not item_id:
                raise SemanticCheckError(f"structural bundle record has invalid {id_field}")
            if item_id in indexed:
                raise SemanticCheckError(f"structural bundle repeats {id_field}: {item_id}")
            indexed[item_id] = record
        result[collection_name] = indexed
    return result


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
        if span_ids is None and isinstance(page.get("blocks"), list):
            span_ids = [
                span
                for block in cast(list[JsonObject], page["blocks"])
                for span in cast(list[str], block.get("source_span_ids", []))
            ]
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


def _validate_input_identity(
    artifact: JsonObject, actual_sha256: str, *, structural: bool
) -> None:
    fields = (
        ("input_structural_bundle_sha256",)
        if structural
        else ("input_job_sha256", "input_bundle_sha256")
    )
    identities = [artifact[field] for field in fields if field in artifact]
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
