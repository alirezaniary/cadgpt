"""Transactional import of source-bound provisional INBR rule extractions."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from django.db import transaction
from jsonschema import ValidationError, validate

from .models import PdfDocument, PdfPage, RuleCandidate


class RuleExtractionImportError(ValueError):
    """Raised when an extraction cannot be bound to the stored transcript."""


def _read(path: Path) -> tuple[dict[str, Any], str]:
    try:
        raw = path.read_bytes()
        value = json.loads(raw)
    except (OSError, json.JSONDecodeError) as exc:
        raise RuleExtractionImportError(f"cannot read JSON {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise RuleExtractionImportError(f"JSON root is not an object: {path}")
    return value, hashlib.sha256(raw).hexdigest()


def _sections(transcript: dict[str, Any]) -> list[dict[str, Any]]:
    value = transcript.get("structured_transcript", transcript)
    sections = value.get("sections") if isinstance(value, dict) else None
    if not isinstance(sections, list):
        raise RuleExtractionImportError("transcript has no sections list")
    if not all(isinstance(item, dict) for item in sections):
        raise RuleExtractionImportError("transcript contains an invalid section")
    return sections


def _schema_path() -> Path:
    return Path(__file__).resolve().parents[5] / "packages/regulations/src/cadgpt_regulations/schemas/provisional-extraction.schema.json"


def _candidate_key(document_key: str, record_id: str, rule_key: str, extraction_hash: str) -> str:
    seed = f"{document_key}\0{record_id}\0{rule_key}\0{extraction_hash}".encode()
    return "inbr-" + hashlib.sha256(seed).hexdigest()


@dataclass(frozen=True)
class ImportResult:
    candidates: int
    no_assertions: int
    pages_touched: int
    dry_run: bool


def import_rule_extraction(
    transcript_path: Path,
    extraction_path: Path,
    *,
    document_key: str,
    dry_run: bool = False,
) -> ImportResult:
    transcript, transcript_hash = _read(transcript_path)
    extraction, extraction_hash = _read(extraction_path)
    try:
        validate(extraction, json.loads(_schema_path().read_text(encoding="utf-8")))
    except (OSError, json.JSONDecodeError, ValidationError) as exc:
        raise RuleExtractionImportError(f"invalid provisional extraction: {exc}") from exc

    document = PdfDocument.objects.filter(document_key=document_key).first()
    if document is None:
        raise RuleExtractionImportError(f"unknown document: {document_key}")
    source = transcript.get("source")
    source_key = source.get("catalog_key") if isinstance(source, dict) else None
    if source_key is not None and source_key != document_key:
        raise RuleExtractionImportError("transcript document key does not match --document-key")
    source_hash = source.get("sha256") if isinstance(source, dict) else None
    if source_hash is not None and source_hash != document.source_sha256:
        raise RuleExtractionImportError("transcript source hash does not match stored document")

    sections = {str(item.get("record_id")): item for item in _sections(transcript)}
    items = extraction["items"]
    if len(sections) != len(_sections(transcript)):
        raise RuleExtractionImportError("duplicate transcript record_id")
    if {str(item["record_id"]) for item in items} != set(sections):
        raise RuleExtractionImportError("extraction record IDs do not exactly cover transcript")

    rows: list[dict[str, Any]] = []
    coverage: dict[str, list[str]] = {}
    no_assertion_records = 0
    for item in items:
        record_id = str(item["record_id"])
        section = sections[record_id]
        page_ids = section.get("source_page_ids") or []
        if not isinstance(page_ids, list) or not page_ids:
            raise RuleExtractionImportError(f"record has no source pages: {record_id}")
        pages = list(PdfPage.objects.filter(document=document, page_key__in=page_ids))
        if len(pages) != len(set(page_ids)):
            raise RuleExtractionImportError(f"source pages are not stored: {record_id}")
        coverage.setdefault("asserted" if item["outcome"] == "candidate" else "no_assertion", []).extend(page_ids)
        if item["outcome"] != "candidate":
            no_assertion_records += 1
            continue
        rule = item.get("rule")
        if not isinstance(rule, dict):
            raise RuleExtractionImportError(f"candidate has no rule: {record_id}")
        rule_key = str(rule.get("rule_key") or record_id)
        primary = pages[0]
        rows.append({
            "candidate_key": _candidate_key(document_key, record_id, rule_key, extraction_hash),
            "document": document,
            "primary_page": primary,
            "source_record_key": record_id,
            "source_record_type": section.get("kind"),
            "source_page_ids": page_ids,
            "source_text_fa": section.get("text_fa"),
            "source_text_sha256": hashlib.sha256(str(section.get("text_fa", "")).encode()).hexdigest(),
            "transcript_sha256": transcript_hash,
            "extraction_file_uri": str(extraction_path),
            "extraction_file_sha256": extraction_hash,
            "extraction_json": item,
            "rule_key": rule_key,
            "implementation_type": rule.get("implementation_type"),
            "status": "needs_review" if item.get("state") == "needs_review" or rule.get("implementation_type") == "unsupported" else "extracted",
            "reason_code": rule.get("unsupported_reason"),
            "validation_json": {"review_flags": item.get("review_flags", [])},
        })

    if dry_run:
        return ImportResult(len(rows), no_assertion_records, len(set(sum(coverage.values(), []))), True)
    with transaction.atomic():
        for row in rows:
            existing = RuleCandidate.objects.filter(candidate_key=row["candidate_key"]).first()
            if existing and existing.extraction_file_sha256 != extraction_hash:
                raise RuleExtractionImportError("immutable extraction hash changed for candidate")
            RuleCandidate.objects.update_or_create(candidate_key=row.pop("candidate_key"), defaults=row)
        for kind, page_ids in coverage.items():
            for page_id in set(page_ids):
                page = PdfPage.objects.get(document=document, page_key=page_id)
                metadata = dict(page.metadata or {})
                metadata.setdefault("rule_extraction_coverage", {})[kind] = True
                page.metadata = metadata
                page.save(update_fields=["metadata", "updated_at"])
    return ImportResult(len(rows), no_assertion_records, len(set(sum(coverage.values(), []))), False)
