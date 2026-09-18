"""Batch bridge from Luna structured transcripts to sandbox rule candidates.

The model extraction step remains replaceable.  This module makes its durable
boundary deterministic: every source record gets an explicit outcome, and every
candidate keeps its transcript revision and source location.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
from typing import Any, cast

from cadgpt_regulations.errors import RegulationsError
from cadgpt_regulations.jsonio import (
    JsonObject,
    canonical_bytes,
    sha256_json,
    validate_schema,
)
from cadgpt_regulations.provisional_rule import (
    make_candidate_citation,
    make_provisional_rule,
    make_transcript_revision,
)
from cadgpt_regulations.resources import load_packaged_json


class ProvisionalBatchError(RegulationsError):
    """Raised when a transcript extraction batch is malformed."""


def build_provisional_batch(
    transcript: Mapping[str, Any],
    extraction: Mapping[str, Any],
    *,
    revision: str,
    edition_fa: str,
) -> JsonObject:
    """Build immutable candidate records from one structured Luna transcript.

    ``extraction.items`` contains records keyed by the transcript ``record_id``.
    Each item either has ``outcome: no_assertion`` with a reason, or a ``rule``
    payload accepted by :func:`make_provisional_rule`.  The function never drops
    an unmentioned source record: missing records are reported as ``unprocessed``.
    """
    source = transcript.get("source")
    if not isinstance(source, Mapping):
        raise ProvisionalBatchError("transcript source is required")
    catalog_key = _string(source, "catalog_key")
    source_sha256 = _string(source, "source_sha256")
    title_fa = str(transcript.get("title_fa") or catalog_key)
    records = _transcript_records(transcript)
    try:
        validate_schema(
            cast(JsonObject, dict(extraction)),
            load_packaged_json(
                "cadgpt_regulations.schemas", "provisional-extraction.schema.json"
            ),
            description="provisional extraction",
        )
    except RegulationsError as exc:
        raise ProvisionalBatchError(str(exc)) from exc
    items = extraction.get("items")
    if not isinstance(items, Sequence) or isinstance(items, (str, bytes)):
        raise ProvisionalBatchError("extraction items must be an array")
    by_id: dict[str, Mapping[str, Any]] = {}
    for item in items:
        if not isinstance(item, Mapping):
            raise ProvisionalBatchError("each extraction item must be an object")
        record_id = _string(item, "record_id")
        if record_id in by_id:
            raise ProvisionalBatchError(f"duplicate extraction record_id: {record_id}")
        by_id[record_id] = item

    revisions: list[JsonObject] = []
    candidates: list[JsonObject] = []
    outcomes: list[JsonObject] = []
    duplicate_groups: dict[str, list[str]] = {}
    for record_key, record in records.items():
        record_id = str(record["record_id"])
        item = _find_item(by_id, record_key, record_id, records)
        if item is None:
            outcomes.append(
                {
                    "record_id": record_id,
                    "record_kind": record_key.split(":", 1)[0],
                    "outcome": "unprocessed",
                }
            )
            continue
        page = _record_page(record, source)
        text_fa = _string(record, "text_fa")
        revision_record = make_transcript_revision(
            document_key=catalog_key,
            revision=f"{revision}:{record_id}",
            transcript_fa=text_fa,
            pdf_page=page,
            printed_page_label=_optional_string(record, "printed_page_label"),
            table_label=_optional_string(record, "table_label"),
            page_id=_first_page_id(record),
            source_document_sha256=source_sha256,
            transcript_payload=transcript,
            record_key=record_key,
        )
        revisions.append(revision_record)
        outcome = item.get("outcome", "candidate")
        if outcome == "no_assertion":
            reason = _optional_string(item, "reason")
            if not reason:
                raise ProvisionalBatchError(
                    f"no_assertion item {record_id} requires reason"
                )
            outcomes.append(
                {
                    "record_id": record_id,
                    "record_kind": record_key.split(":", 1)[0],
                    "outcome": "no_assertion",
                    "reason": reason,
                }
            )
            continue
        rule = item.get("rule")
        if not isinstance(rule, Mapping):
            raise ProvisionalBatchError(f"candidate item {record_id} has no rule")
        state = str(item.get("state", "needs_review"))
        citation = make_candidate_citation(
            transcript_revision=revision_record,
            book_title_fa=title_fa,
            edition_fa=edition_fa,
            citation_status="needs_review" if state != "candidate" else "candidate",
            table_label=_optional_string(record, "table_label"),
            section_label=_optional_string(record, "section_label"),
        )
        candidate = make_provisional_rule(
            rule=rule,
            transcript_revision=revision_record,
            state=state,
            review_flags=[
                *list(item.get("review_flags", [])),
                "SEMANTIC_REVIEW_PENDING",
            ],
            candidate_citation=citation,
        )
        candidates.append(candidate)
        fingerprint = _semantic_fingerprint(rule)
        duplicate_groups.setdefault(fingerprint, []).append(
            cast(str, candidate["candidate_id"])
        )
        outcomes.append(
            {
                "record_id": record_id,
                "record_kind": record_key.split(":", 1)[0],
                "outcome": "candidate",
                "candidate_id": candidate["candidate_id"],
            }
        )

    for record_id in by_id:
        if record_id not in records and not any(
            str(record["record_id"]) == record_id for record in records.values()
        ):
            raise ProvisionalBatchError(
                f"extraction record is absent from transcript: {record_id}"
            )
    groups = [
        {"semantic_fingerprint": key, "candidate_ids": sorted(value)}
        for key, value in sorted(duplicate_groups.items())
        if len(value) > 1
    ]
    result: JsonObject = {
        "schema_version": "provisional-batch-1.0.0",
        "batch_id": "",
        "document_key": catalog_key,
        "source_document_sha256": source_sha256,
        "transcript_sha256": sha256_json(cast(JsonObject, dict(transcript))),
        "extraction_sha256": sha256_json(cast(JsonObject, dict(extraction))),
        "revision": revision,
        "edition_fa": edition_fa,
        "transcript_revision_ids": [item["revision_id"] for item in revisions],
        "candidate_ids": [item["candidate_id"] for item in candidates],
        "transcript_revisions": revisions,
        "candidates": candidates,
        "outcomes": outcomes,
        "duplicate_groups": groups,
        "summary": {
            "records": len(records),
            "candidates": len(candidates),
            "no_assertion": sum(item["outcome"] == "no_assertion" for item in outcomes),
            "unprocessed": sum(item["outcome"] == "unprocessed" for item in outcomes),
            "duplicate_groups": len(groups),
        },
    }
    identity = {key: value for key, value in result.items() if key != "batch_id"}
    result["batch_id"] = hashlib.sha256(canonical_bytes(identity)).hexdigest()
    return result


def validate_provisional_batch(value: Mapping[str, Any]) -> None:
    """Validate the batch identity and its immutable source summaries."""
    record = dict(value)
    batch_id = record.pop("batch_id", None)
    if not isinstance(batch_id, str) or len(batch_id) != 64:
        raise ProvisionalBatchError("batch_id must be a SHA-256 hash")
    if hashlib.sha256(canonical_bytes(cast(JsonObject, record))).hexdigest() != batch_id:
        raise ProvisionalBatchError("batch_id does not match immutable batch content")
    for field in ("transcript_sha256", "extraction_sha256", "source_document_sha256"):
        value = record.get(field)
        if not isinstance(value, str) or len(value) != 64:
            raise ProvisionalBatchError(f"{field} must be a SHA-256 hash")


def _transcript_records(transcript: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    result: dict[str, Mapping[str, Any]] = {}
    record_groups = (
        "sections",
        "clauses",
        "requirements",
        "prohibitions",
        "permissions",
        "procedures",
        "definitions",
        "formulas",
        "references",
        "tables",
        "uncertainties",
    )
    for key in record_groups:
        values = transcript.get(key, [])
        if not isinstance(values, list):
            raise ProvisionalBatchError(f"transcript {key} must be an array")
        for value in values:
            if not isinstance(value, Mapping):
                raise ProvisionalBatchError(f"transcript {key} contains a non-object")
            record_id = _string(value, "record_id")
            result_key = f"{key}:{record_id}"
            result[result_key] = value
    return result


def _find_item(
    items: Mapping[str, Mapping[str, Any]],
    record_key: str,
    record_id: str,
    records: Mapping[str, Mapping[str, Any]],
) -> Mapping[str, Any] | None:
    exact = items.get(record_key)
    if exact is not None:
        return exact
    matches = [
        item
        for key, item in items.items()
        if key == record_id
        and sum(str(record["record_id"]) == record_id for record in records.values()) == 1
    ]
    if len(matches) > 1:
        raise ProvisionalBatchError(
            f"ambiguous extraction record_id; use record kind prefix: {record_id}"
        )
    return matches[0] if matches else None


def _record_page(record: Mapping[str, Any], source: Mapping[str, Any]) -> int:
    pages = record.get("source_page_ids")
    if isinstance(pages, list) and pages:
        raw = str(pages[0]).rsplit(":", 1)[-1]
        if raw.isdigit():
            return int(raw)
    value = source.get("start_pdf_page")
    if isinstance(value, int) and value > 0:
        return value
    raise ProvisionalBatchError("record has no usable PDF page")


def _first_page_id(record: Mapping[str, Any]) -> str | None:
    values = record.get("source_page_ids")
    return str(values[0]) if isinstance(values, list) and values else None


def _semantic_fingerprint(rule: Mapping[str, Any]) -> str:
    excluded = {"source_citation", "rule_key", "title_fa"}
    value = {key: rule[key] for key in sorted(rule) if key not in excluded}
    return hashlib.sha256(canonical_bytes(cast(JsonObject, value))).hexdigest()


def _string(value: Mapping[str, Any], key: str) -> str:
    result = value.get(key)
    if not isinstance(result, str) or not result.strip():
        raise ProvisionalBatchError(f"{key} must be a non-empty string")
    return result


def _optional_string(value: Mapping[str, Any], key: str) -> str | None:
    result = value.get(key)
    return result if isinstance(result, str) and result else None


__all__ = [
    "ProvisionalBatchError",
    "build_provisional_batch",
    "validate_provisional_batch",
]
