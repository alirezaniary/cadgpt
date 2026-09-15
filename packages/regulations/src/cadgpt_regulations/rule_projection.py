"""Build the small, page-first database projection for compiled rules.

The projection deliberately mirrors ``sql/rule_projection.sql``: one document
row, one row per cited page, and one row per rule candidate. Raw Luna chunks and
compiled artifacts remain immutable files; this module only records their URIs,
hashes, and the page/rule data needed for queries.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Iterable, Mapping
from typing import Any, cast

from cadgpt_regulations.citation import citation_hash, validate_source_citation
from cadgpt_regulations.errors import RegulationsError
from cadgpt_regulations.jsonio import JsonObject, canonical_bytes
from cadgpt_regulations.rule_release import _compiled_parts


class RuleProjectionError(RegulationsError):
    """Raised when compiled artifacts cannot map to page-first projection rows."""


_DOCUMENT_KEY_RE = re.compile(r"^volume-(?P<volume>[0-9]+)-edition-(?P<edition>[0-9]+)$")


def build_projection_rows(
    manifest: JsonObject,
    compiled_rules: Iterable[Any],
    *,
    relations: JsonObject | None = None,
    page_source: Mapping[str, Any],
) -> JsonObject:
    """Return deterministic ``pdf_document``, ``pdf_page``, and ``rule_candidate`` rows.

    ``relations`` is accepted for source compatibility but intentionally ignored:
    the reduced schema has no assertion/relation tables. Every compiled rule is
    represented as one candidate row and its citation pages are represented in
    ``source_page_ids`` on that row.
    """
    del relations
    release_id = _required_hash(manifest, "release_id")
    body = dict(manifest)
    body.pop("release_id", None)
    manifest_hash = hashlib.sha256(canonical_bytes(body)).hexdigest()
    if manifest_hash != release_id:
        raise RuleProjectionError("release_id does not match manifest body")
    expected = {
        _required_string(item, "rule_id"): item for item in _records(manifest, "rules")
    }
    documents: dict[str, JsonObject] = {}
    pages: dict[tuple[str, int], JsonObject] = {}
    candidates: list[JsonObject] = []
    seen: set[str] = set()
    source_documents, source_pages = build_page_projection_rows(page_source)
    for row in source_documents:
        documents[_required_string(row, "document_key")] = row
    for row in source_pages:
        key = (
            _required_string(row, "document_key"),
            cast(int, row["pdf_page_number"]),
        )
        pages[key] = row
    for compiled in compiled_rules:
        rule_id, ids_xml, sidecar = _compiled_parts(compiled)
        if rule_id in seen or rule_id not in expected:
            raise RuleProjectionError(f"compiled rule is not uniquely covered: {rule_id}")
        seen.add(rule_id)
        if not isinstance(ids_xml, (bytes, bytearray)) or not isinstance(sidecar, Mapping):
            raise RuleProjectionError(f"compiled rule {rule_id} has invalid artifacts")
        entry = expected[rule_id]
        sidecar_object = cast(JsonObject, dict(sidecar))
        citation = sidecar_object.get("source_citation")
        if not isinstance(citation, dict):
            raise RuleProjectionError(f"compiled rule has no source citation: {rule_id}")
        citation_obj = cast(JsonObject, citation)
        validate_source_citation(citation_obj)
        ids_hash = hashlib.sha256(bytes(ids_xml)).hexdigest()
        sidecar_hash = hashlib.sha256(canonical_bytes(sidecar_object)).hexdigest()
        if (
            entry.get("ids_sha256") != ids_hash
            or entry.get("sidecar_sha256") != sidecar_hash
        ):
            raise RuleProjectionError(
                f"compiled rule hashes differ from manifest: {rule_id}"
            )
        if entry.get("source_citation_sha256") != citation_hash(citation_obj):
            raise RuleProjectionError(
                f"compiled citation hash differs from manifest: {rule_id}"
            )

        document_key = _machine_identifier(citation_obj, "document_key")
        document_sha256 = _required_hash(citation_obj, "document_sha256")
        document_row = _document_row(citation_obj, document_key, document_sha256)
        previous_document = documents.get(document_key)
        documents[document_key] = (
            _merge_document_rows(previous_document, document_row, document_key)
            if previous_document is not None
            else document_row
        )

        page_number = citation_obj.get("pdf_page")
        if not isinstance(page_number, int) or page_number < 1:
            raise RuleProjectionError(f"citation has invalid pdf_page: {rule_id}")
        page_id = citation_obj.get("page_id") or f"{document_key}:page:{page_number}"
        if not isinstance(page_id, str) or not page_id:
            raise RuleProjectionError(f"citation has invalid page_id: {rule_id}")
        source_pages = _source_pages(sidecar_object, document_key, page_number, page_id)
        for source_page in source_pages:
            source_page_number = cast(int, source_page["pdf_page"])
            source_page_key = cast(str, source_page["page_id"])
            existing = pages.get((document_key, source_page_number))
            if existing is None or existing.get("page_key") != source_page_key:
                raise RuleProjectionError(
                    "source page ID is not present in the supplied page source"
                )
            page_key = (document_key, source_page_number)
            previous_page = pages.get(page_key)
            if previous_page is None:
                raise RuleProjectionError(
                    "source page disappeared from the supplied page source"
                )
        source_page_ids = [
            {
                "page_id": item["page_id"],
                "pdf_page": item["pdf_page"],
                "role": item["role"],
            }
            for item in source_pages
        ]
        _validate_source_page_ids(source_page_ids, document_key, pages)
        candidates.append(
            {
                "candidate_key": _machine_identifier(
                    {"candidate_key": rule_id}, "candidate_key"
                ),
                "document_key": document_key,
                "primary_page_key": page_id,
                "source_record_key": str(
                    sidecar_object.get("source_record_key") or page_id
                ),
                "source_record_type": str(
                    sidecar_object.get("source_record_type") or "rule"
                ),
                "source_page_ids": source_page_ids,
                "source_text_fa": citation_obj["exact_text_fa"],
                "source_text_sha256": citation_obj["exact_text_sha256"],
                "transcript_sha256": citation_obj.get("transcript_sha256"),
                "extraction_file_uri": None,
                "extraction_file_sha256": None,
                "extraction_json": {"release_id": release_id, "rule_id": rule_id},
                "rule_key": _canonical_rule_key(sidecar_object, rule_id),
                "implementation_type": _implementation_type(sidecar_object),
                "semantic_fingerprint": _semantic_fingerprint(sidecar_object),
                "ids_specification": _ids_specification(sidecar_object),
                "ids_xml_uri": f"cas://sha256/{ids_hash}",
                "ids_xml_sha256": ids_hash,
                "sidecar_uri": f"cas://sha256/{sidecar_hash}",
                "sidecar_sha256": sidecar_hash,
                "compiler_version": sidecar_object.get("compiler_version"),
                "status": "compiled",
                "reason_code": None,
                "validation_json": {"release_id": release_id},
            }
        )
    if seen != set(expected):
        raise RuleProjectionError("manifest rules do not match compiled artifacts")
    return {
        "pdf_documents": sorted(documents.values(), key=lambda item: item["document_key"]),
        "pdf_pages": sorted(
            pages.values(), key=lambda item: (item["document_key"], item["pdf_page_number"])
        ),
        "rule_candidates": sorted(candidates, key=lambda item: item["candidate_key"]),
    }


def _document_row(
    citation: Mapping[str, Any], document_key: str, source_sha256: str
) -> JsonObject:
    match = _DOCUMENT_KEY_RE.fullmatch(document_key)
    volume = int(match.group("volume")) if match else None
    edition_year = int(match.group("edition")) if match else None
    edition_code = citation.get("edition_code")
    if not isinstance(edition_code, str) or not edition_code:
        edition_code = f"edition-{edition_year}" if edition_year else "unknown"
    edition_code = _machine_identifier({"edition_code": edition_code}, "edition_code")
    return {
        "document_key": document_key,
        "pdf_name": str(citation.get("pdf_name") or f"{document_key}.pdf"),
        "file_path": str(citation.get("file_path") or f"cas://sha256/{source_sha256}"),
        "storage_uri": f"cas://sha256/{source_sha256}",
        "volume_number": volume,
        "edition_year": edition_year,
        "edition_code": edition_code,
        "title_fa": citation["book_title_fa"],
        "source_sha256": source_sha256,
        "file_size_bytes": None,
        "page_count": None,
        "metadata": {"edition_display": citation["edition_fa"]},
    }


def _merge_document_rows(
    previous: JsonObject, current: JsonObject, document_key: str
) -> JsonObject:
    if previous.get("source_sha256") != current.get("source_sha256"):
        raise RuleProjectionError(f"document has conflicting hashes: {document_key}")
    result = dict(previous)
    for key, value in current.items():
        if value is None or value == "":
            continue
        if result.get(key) in (None, "") or (
            key == "title_fa" and result.get(key) == document_key
        ):
            result[key] = value
        elif (
            key == "metadata"
            and isinstance(result.get(key), dict)
            and isinstance(value, dict)
        ):
            result[key] = {**cast(JsonObject, result[key]), **cast(JsonObject, value)}
    return result


def build_page_projection_rows(
    source: Mapping[str, Any],
) -> tuple[list[JsonObject], list[JsonObject]]:
    """Project every physical page from a transcription/Luna manifest.

    This path is independent of compiled rules, so pages with no actionable
    candidate are still imported. The input accepts the existing transcription
    shape (``documents[].pages[]``); extraction payloads remain referenced by
    their package paths and hashes rather than copied into this result.
    """
    raw_documents = source.get("documents")
    if not isinstance(raw_documents, list):
        raise RuleProjectionError("page source must contain a documents list")
    documents: list[JsonObject] = []
    pages: list[JsonObject] = []
    seen_documents: set[str] = set()
    seen_pages: set[tuple[str, int]] = set()
    for raw_document in raw_documents:
        if not isinstance(raw_document, Mapping):
            raise RuleProjectionError("page source document is not an object")
        document_key = _machine_identifier(raw_document, "catalog_key")
        source_sha256 = _required_hash(raw_document, "source_sha256")
        if document_key in seen_documents:
            raise RuleProjectionError(f"duplicate page source document: {document_key}")
        seen_documents.add(document_key)
        document = _document_row(
            {
                "book_title_fa": str(raw_document.get("title_fa") or document_key),
                "edition_fa": str(raw_document.get("edition_fa") or ""),
                "pdf_name": raw_document.get("pdf_name"),
                "file_path": raw_document.get("artifact_path"),
            },
            document_key,
            source_sha256,
        )
        document["file_size_bytes"] = raw_document.get("source_bytes")
        document["page_count"] = raw_document.get("pdf_page_count")
        documents.append(document)
        raw_pages = raw_document.get("pages")
        if not isinstance(raw_pages, list):
            raise RuleProjectionError(f"page source document has no pages: {document_key}")
        for raw_page in raw_pages:
            if not isinstance(raw_page, Mapping):
                raise RuleProjectionError("page source page is not an object")
            page_number = raw_page.get("pdf_page")
            page_id = raw_page.get("page_id")
            if not isinstance(page_number, int) or page_number < 1:
                raise RuleProjectionError(f"invalid page number in {document_key}")
            if not isinstance(page_id, str) or not page_id:
                raise RuleProjectionError(
                    f"invalid page ID in {document_key}/{page_number}"
                )
            key = (document_key, page_number)
            if key in seen_pages:
                raise RuleProjectionError(
                    f"duplicate page source: {document_key}/{page_number}"
                )
            seen_pages.add(key)
            route = {
                "none": "blank",
                "native": "native",
                "ocr": "paddle",
                "native_plus_ocr": "native_plus_paddle",
            }.get(raw_page.get("route"), "pending")
            state = raw_page.get("state")
            status = "failed" if state == "failed" else "extracted"
            if raw_page.get("luna_transcript_json") is not None:
                status = "transcribed"
            pages.append(
                {
                    "document_key": document_key,
                    "page_key": page_id,
                    "pdf_page_number": page_number,
                    "printed_page_label": raw_page.get("printed_page_label"),
                    "extraction_route": route,
                    "status": status,
                    "native_text": raw_page.get("native_text"),
                    "native_layout_json": raw_page.get("native_layout_json"),
                    "native_text_sha256": raw_page.get("native_text_sha256"),
                    "paddle_text": raw_page.get("paddle_text"),
                    "paddle_result_json": raw_page.get("paddle_result_json"),
                    "paddle_text_sha256": raw_page.get("paddle_text_sha256"),
                    "luna_transcript_json": raw_page.get("luna_transcript_json"),
                    "luna_transcript_text": raw_page.get("luna_transcript_text"),
                    "luna_transcript_sha256": raw_page.get("luna_transcript_sha256"),
                    "luna_response_uri": raw_page.get("luna_response_uri"),
                    "luna_response_sha256": raw_page.get("luna_response_sha256"),
                    "metadata": {
                        "package_path": raw_page.get("package_path"),
                        "package_sha256": raw_page.get("package_sha256"),
                    },
                }
            )
    return documents, pages


def _source_pages(
    sidecar: Mapping[str, Any],
    document_key: str,
    page_number: int,
    page_id: str,
) -> list[JsonObject]:
    raw = sidecar.get("source_pages")
    if raw is None:
        return [{"page_id": page_id, "pdf_page": page_number, "role": "source"}]
    if not isinstance(raw, list) or not raw:
        raise RuleProjectionError("source_pages must be a non-empty list")
    result: list[JsonObject] = []
    seen: set[str] = set()
    for item in raw:
        if not isinstance(item, Mapping):
            raise RuleProjectionError("source_pages entries must be objects")
        source_id = item.get("page_id")
        source_number = item.get("pdf_page")
        source_document = item.get("document_key", document_key)
        if (
            not isinstance(source_id, str)
            or not source_id
            or not isinstance(source_number, int)
            or source_number < 1
            or source_document != document_key
            or source_id in seen
        ):
            raise RuleProjectionError("source page IDs must belong to the cited document")
        seen.add(source_id)
        result.append(
            {
                "page_id": source_id,
                "pdf_page": source_number,
                "role": str(item.get("role") or "source"),
            }
        )
    return result


def _validate_source_page_ids(
    source_page_ids: list[JsonObject],
    document_key: str,
    pages: Mapping[tuple[str, int], JsonObject],
) -> None:
    for item in source_page_ids:
        page_id = item.get("page_id")
        page_number = item.get("pdf_page")
        if not isinstance(page_id, str) or not isinstance(page_number, int):
            raise RuleProjectionError(
                "source_page_ids entries must include page_id/pdf_page"
            )
        page = pages.get((document_key, page_number))
        if page is None or page.get("page_key") != page_id:
            raise RuleProjectionError(
                "source_page_ids contains a page outside the document"
            )


def _canonical_rule_key(sidecar: Mapping[str, Any], fallback: str) -> str:
    canonical = sidecar.get("canonical_rule")
    if isinstance(canonical, Mapping) and isinstance(canonical.get("rule_key"), str):
        return cast(str, canonical["rule_key"])
    return fallback


def _implementation_type(sidecar: Mapping[str, Any]) -> str:
    canonical = sidecar.get("canonical_rule")
    if isinstance(canonical, Mapping):
        return "native_ids"
    return "unsupported"


def _semantic_fingerprint(sidecar: Mapping[str, Any]) -> str | None:
    canonical = sidecar.get("canonical_rule")
    if not isinstance(canonical, Mapping):
        return None
    return hashlib.sha256(canonical_bytes(cast(JsonObject, dict(canonical)))).hexdigest()


def _ids_specification(sidecar: Mapping[str, Any]) -> JsonObject | None:
    supplied = sidecar.get("ids_specification")
    if isinstance(supplied, Mapping):
        result = cast(JsonObject, dict(supplied))
        _validate_ids_specification(result)
        return result
    canonical = sidecar.get("canonical_rule")
    if not isinstance(canonical, Mapping):
        return None
    entity = canonical.get("entity")
    attribute = canonical.get("attribute")
    if (
        not isinstance(entity, str)
        or not entity
        or not isinstance(attribute, str)
        or not attribute
    ):
        raise RuleProjectionError("canonical rule cannot be mapped to IDS facets")
    citation = sidecar.get("source_citation")
    instructions = citation.get("exact_text_fa") if isinstance(citation, Mapping) else None
    result = {
        "ifc_versions": list(canonical.get("ifc_versions", [])),
        "name": canonical.get("rule_key", "candidate"),
        "description": canonical.get("title_fa", ""),
        "instructions": instructions,
        "applicability": [{"entity": {"name": entity}}],
        "requirements": [
            {
                "attribute": {
                    "name": attribute,
                    "cardinality": "required",
                    "comparator": canonical.get("comparator"),
                    "value": canonical.get("value"),
                    "unit": canonical.get("unit"),
                }
            }
        ],
    }
    _validate_ids_specification(result)
    return result


def _validate_ids_specification(value: Mapping[str, Any]) -> None:
    facets = {"entity", "partOf", "classification", "attribute", "property", "material"}
    versions = value.get("ifc_versions")
    if (
        not isinstance(versions, list)
        or not versions
        or not all(isinstance(item, str) and item for item in versions)
    ):
        raise RuleProjectionError("IDS specification has invalid ifc_versions")
    for field in ("applicability", "requirements"):
        records = value.get(field)
        if not isinstance(records, list) or not records:
            raise RuleProjectionError(f"IDS specification has invalid {field}")
        for record in records:
            if not isinstance(record, Mapping):
                raise RuleProjectionError(f"IDS {field} facet is not an object")
            names = [name for name in record if name in facets]
            if len(names) != 1 or not isinstance(record[names[0]], Mapping):
                raise RuleProjectionError(f"IDS {field} facet is invalid")


def _records(value: JsonObject, field: str) -> list[JsonObject]:
    raw = value.get(field)
    if not isinstance(raw, list) or not all(isinstance(item, dict) for item in raw):
        raise RuleProjectionError(f"release has invalid {field}")
    return [cast(JsonObject, item) for item in raw]


def _required_string(value: Mapping[str, Any], field: str) -> str:
    result = value.get(field)
    if not isinstance(result, str) or not result:
        raise RuleProjectionError(f"{field} must be a non-empty string")
    return result


def _required_hash(value: Mapping[str, Any], field: str) -> str:
    result = _required_string(value, field)
    if len(result) != 64 or any(char not in "0123456789abcdef" for char in result):
        raise RuleProjectionError(f"{field} must be a lowercase SHA-256")
    return result


def _machine_identifier(value: Mapping[str, Any], field: str) -> str:
    result = _required_string(value, field)
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", result):
        raise RuleProjectionError(f"{field} must use an ASCII machine identifier")
    return result
