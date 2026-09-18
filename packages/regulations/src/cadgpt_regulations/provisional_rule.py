"""Lifecycle contracts for rules derived from Persian transcript checkpoints.

Provisional artifacts are intentionally separate from :mod:`ids_compiler`: they
retain the PDF/page/record citation from the Luna JSON while review is pending.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from typing import Any, cast

from cadgpt_regulations.errors import RegulationsError
from cadgpt_regulations.jsonio import JsonObject, canonical_bytes, validate_schema
from cadgpt_regulations.resources import load_packaged_json


class ProvisionalRuleError(RegulationsError):
    """Raised when a provisional transcript/rule record is malformed."""


TRANSCRIPT_STATES = frozenset({"extracted", "corrected", "superseded"})
RULE_STATES = frozenset(
    {"candidate", "needs_review", "verified", "published", "superseded"}
)
CANDIDATE_CITATION_STATES = frozenset({"candidate", "needs_review", "unresolved"})
_SHA256 = frozenset("0123456789abcdef")


def content_sha256(value: str) -> str:
    """Hash immutable UTF-8 transcript content."""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def make_transcript_revision(
    *,
    document_key: str,
    revision: str,
    transcript_fa: str,
    pdf_page: int,
    printed_page_label: str | None = None,
    table_label: str | None = None,
    source_document_sha256: str | None = None,
    page_id: str | None = None,
    transcript_payload: Mapping[str, Any] | None = None,
    record_key: str | None = None,
    supersedes: str | None = None,
    state: str = "extracted",
) -> JsonObject:
    """Create a content-addressed transcript revision without editing history."""
    if not document_key or not revision or not transcript_fa.strip():
        raise ProvisionalRuleError("document_key, revision, and transcript_fa are required")
    if not isinstance(pdf_page, int) or pdf_page < 1:
        raise ProvisionalRuleError("pdf_page must be a positive integer")
    if state not in TRANSCRIPT_STATES:
        raise ProvisionalRuleError(f"unsupported transcript state: {state}")
    if state in {"corrected", "superseded"} and supersedes is None:
        raise ProvisionalRuleError(
            f"{state} transcript revisions must identify the superseded revision"
        )
    result: JsonObject = {
        "document_key": document_key,
        "revision": revision,
        "transcript_fa": transcript_fa,
        "transcript_sha256": content_sha256(transcript_fa),
        "pdf_page": pdf_page,
        "printed_page_label": printed_page_label,
        "table_label": table_label,
        "source_document_sha256": source_document_sha256,
        "page_id": page_id,
        "transcript_payload": (
            dict(transcript_payload) if transcript_payload is not None else None
        ),
        "transcript_payload_sha256": (
            hashlib.sha256(
                canonical_bytes(cast(JsonObject, dict(transcript_payload)))
            ).hexdigest()
            if transcript_payload is not None
            else None
        ),
        "supersedes": supersedes,
        "state": state,
    }
    if transcript_payload is not None:
        payload = dict(transcript_payload)
        result["transcript_payload"] = payload
        result["transcript_payload_sha256"] = hashlib.sha256(
            canonical_bytes(cast(JsonObject, payload))
        ).hexdigest()
    if record_key is not None:
        result["record_key"] = record_key
    result["revision_id"] = hashlib.sha256(canonical_bytes(result)).hexdigest()
    validate_transcript_revision(result)
    return result


def validate_transcript_revision(value: Mapping[str, Any]) -> None:
    """Validate an immutable Luna/transcript revision and its content hash."""
    record = dict(value)
    try:
        validate_schema(
            cast(JsonObject, record),
            load_packaged_json(
                "cadgpt_regulations.schemas", "transcript-revision.schema.json"
            ),
            description="transcript revision",
        )
    except RegulationsError as exc:
        raise ProvisionalRuleError(str(exc)) from exc
    transcript = record["transcript_fa"]
    if record["transcript_sha256"] != content_sha256(transcript):
        raise ProvisionalRuleError("transcript_sha256 does not match transcript_fa")
    payload = record["transcript_payload"]
    payload_hash = record["transcript_payload_sha256"]
    if payload is None:
        if payload_hash is not None:
            raise ProvisionalRuleError(
                "transcript_payload_sha256 requires transcript_payload"
            )
    elif payload_hash != hashlib.sha256(canonical_bytes(payload)).hexdigest():
        raise ProvisionalRuleError(
            "transcript_payload_sha256 does not match transcript_payload"
        )
    if record["source_document_sha256"] is not None:
        _validate_hash(record["source_document_sha256"], "source_document_sha256")
    if record["supersedes"] is not None:
        _validate_hash(record["supersedes"], "supersedes")
    revision_id = record.pop("revision_id")
    if hashlib.sha256(canonical_bytes(record)).hexdigest() != revision_id:
        raise ProvisionalRuleError("revision_id does not match immutable revision content")


def make_candidate_citation(
    *,
    transcript_revision: Mapping[str, Any],
    book_title_fa: str,
    edition_fa: str,
    citation_status: str = "candidate",
    table_label: str | None = None,
    section_label: str | None = None,
    qualifier_text_fa: str | None = None,
) -> JsonObject:
    """Create a page/table citation from the immutable transcript revision.

    Candidate citations preserve the Luna quotation, PDF page, and transcript hash.
    Structural node/span arrays remain optional metadata and are not required for
    transcript-backed rule translation.
    """
    validate_transcript_revision(transcript_revision)
    if citation_status not in CANDIDATE_CITATION_STATES:
        raise ProvisionalRuleError(
            "candidate citation status must be candidate, needs_review, or unresolved"
        )
    if not book_title_fa.strip() or not edition_fa.strip():
        raise ProvisionalRuleError("book_title_fa and edition_fa are required")
    citation: JsonObject = {
        "document_key": transcript_revision["document_key"],
        "book_title_fa": book_title_fa,
        "edition_fa": edition_fa,
        "document_sha256": transcript_revision.get("source_document_sha256"),
        "pdf_page": transcript_revision["pdf_page"],
        "printed_page_label": transcript_revision.get("printed_page_label"),
        "page_id": transcript_revision.get("page_id"),
        "source_node_ids": [],
        "source_span_ids": [],
        "exact_text_fa": transcript_revision["transcript_fa"],
        "exact_text_sha256": content_sha256(transcript_revision["transcript_fa"]),
        "qualifier_text_fa": qualifier_text_fa,
        "citation_status": citation_status,
        "transcript_revision_id": transcript_revision["revision_id"],
        "transcript_sha256": transcript_revision["transcript_sha256"],
        "table_label": table_label or transcript_revision.get("table_label"),
        "section_label": section_label,
    }
    validate_candidate_citation(citation)
    return citation


def validate_candidate_citation(value: Mapping[str, Any]) -> None:
    """Validate page-level candidate provenance without pretending it is verified."""
    citation = dict(value)
    try:
        validate_schema(
            cast(JsonObject, citation),
            load_packaged_json(
                "cadgpt_regulations.schemas", "candidate-citation.schema.json"
            ),
            description="candidate citation",
        )
    except RegulationsError as exc:
        raise ProvisionalRuleError(str(exc)) from exc
    if citation["exact_text_sha256"] != content_sha256(citation["exact_text_fa"]):
        raise ProvisionalRuleError(
            "candidate exact_text_sha256 does not match exact_text_fa"
        )
    if citation["document_sha256"] is not None:
        _validate_hash(citation["document_sha256"], "document_sha256")
    if citation["transcript_sha256"] != transcript_revision_sha256(citation):
        # The citation carries the transcript hash independently so it remains
        # self-describing when persisted outside the revision row.
        raise ProvisionalRuleError("candidate transcript hash is invalid")
    if citation.get("source_node_ids", []) or citation.get("source_span_ids", []):
        raise ProvisionalRuleError(
            "candidate citation cannot claim structural node/span attestation"
        )


def _validate_hash(value: Any, field: str) -> None:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in _SHA256 for character in value)
    ):
        raise ProvisionalRuleError(f"{field} must be a lowercase SHA-256")


def transcript_revision_sha256(citation: Mapping[str, Any]) -> str:
    """Return the already-attested transcript hash from a candidate citation."""
    value = citation.get("transcript_sha256")
    _validate_hash(value, "transcript_sha256")
    return cast(str, value)


def make_provisional_rule(
    *,
    rule: Mapping[str, Any],
    transcript_revision: Mapping[str, Any],
    state: str = "candidate",
    review_flags: list[str] | None = None,
    candidate_citation: Mapping[str, Any] | None = None,
) -> JsonObject:
    """Bind a generated rule to an immutable transcript revision.

    This record is suitable for sandbox evaluation only. Reviewed rules use a
    transcript citation and deterministic compiler; a candidate status alone
    cannot authorize publication.
    """
    required = ("revision_id", "document_key", "transcript_sha256", "pdf_page")
    missing = [key for key in required if key not in transcript_revision]
    if missing:
        raise ProvisionalRuleError("transcript revision missing: " + ", ".join(missing))
    if state not in RULE_STATES:
        raise ProvisionalRuleError(f"unsupported rule state: {state}")
    if state in {"verified", "published"}:
        raise ProvisionalRuleError(
            "provisional candidates cannot claim verified or published; "
            "use a verified release"
        )
    rule_copy = dict(rule)
    if candidate_citation is not None:
        validate_candidate_citation(candidate_citation)
        rule_copy["source_citation"] = dict(candidate_citation)
    result: JsonObject = {
        "rule": cast(JsonObject, rule_copy),
        "rule_state": state,
        "transcript_revision_id": transcript_revision["revision_id"],
        "transcript_sha256": transcript_revision["transcript_sha256"],
        "document_key": transcript_revision["document_key"],
        "pdf_page": transcript_revision["pdf_page"],
        "printed_page_label": transcript_revision.get("printed_page_label"),
        "table_label": transcript_revision.get("table_label"),
        "review_flags": sorted(set(review_flags or [])),
    }
    result["candidate_id"] = hashlib.sha256(canonical_bytes(result)).hexdigest()
    validate_provisional_rule(result)
    return result


def validate_provisional_rule(value: Mapping[str, Any]) -> None:
    """Validate candidate identity and its immutable transcript binding."""
    record = dict(value)
    for field in (
        "candidate_id",
        "transcript_revision_id",
        "transcript_sha256",
        "document_key",
    ):
        if not isinstance(record.get(field), str) or not record[field]:
            raise ProvisionalRuleError(f"candidate {field} is required")
    _validate_hash(record["transcript_sha256"], "transcript_sha256")
    if record["rule_state"] not in RULE_STATES:
        raise ProvisionalRuleError(f"unsupported rule state: {record['rule_state']}")
    if record["rule_state"] in {"verified", "published"}:
        raise ProvisionalRuleError(
            "provisional candidates cannot claim verified or published; "
            "use a verified release"
        )
    citation = cast(Mapping[str, Any] | None, record.get("source_citation"))
    if citation is not None:
        validate_candidate_citation(citation)
        if citation["transcript_revision_id"] != record["transcript_revision_id"]:
            raise ProvisionalRuleError("candidate citation revision differs from candidate")
    candidate_id = record.pop("candidate_id")
    if hashlib.sha256(canonical_bytes(record)).hexdigest() != candidate_id:
        raise ProvisionalRuleError(
            "candidate_id does not match immutable candidate content"
        )


def sandbox_only(candidate: Mapping[str, Any]) -> bool:
    """Return whether a candidate must remain outside official engine releases."""
    return candidate.get("rule_state") != "published"


__all__ = [
    "RULE_STATES",
    "TRANSCRIPT_STATES",
    "ProvisionalRuleError",
    "content_sha256",
    "make_candidate_citation",
    "make_provisional_rule",
    "make_transcript_revision",
    "sandbox_only",
    "transcript_revision_sha256",
    "validate_candidate_citation",
    "validate_provisional_rule",
    "validate_transcript_revision",
]
