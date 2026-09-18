"""Validated source citations carried from INBR evidence into executable rules."""

from __future__ import annotations

import hashlib
from typing import cast

from cadgpt_regulations.errors import RegulationsError
from cadgpt_regulations.jsonio import JsonObject, canonical_bytes
from cadgpt_regulations.source_citation import (
    citation_evidence_kind,
)
from cadgpt_regulations.source_citation import (
    validate_source_citation as validate_citation_record,
)


class CitationError(RegulationsError):
    """Raised when a rule citation cannot be re-attested to source evidence."""


def validate_source_citation(citation: JsonObject) -> None:
    """Validate identity, anchors, and the exact Persian quotation hash."""
    try:
        validate_citation_record(citation)
    except RegulationsError as exc:
        raise CitationError(str(exc)) from exc
    if citation["citation_status"] != "verified":
        raise CitationError("only verified source citations can reach executable rules")


def citation_description(citation: JsonObject) -> str:
    """Return compact metadata safe to place in IDS specification description."""
    validate_source_citation(citation)
    printed = citation.get("printed_page_label") or str(citation["pdf_page"])
    page_id = citation.get("page_id") or f"pdf-page:{citation['pdf_page']}"
    spans = ",".join(cast(list[str], citation.get("source_span_ids", [])))
    nodes = ",".join(cast(list[str], citation.get("source_node_ids", [])))
    evidence = (
        f"transcript_revision_id={citation['transcript_revision_id']}; "
        f"transcript_sha256={citation['transcript_sha256']}; "
        if citation_evidence_kind(citation) == "transcript"
        else f"source_node_ids={nodes}; source_span_ids={spans}; "
    )
    return (
        f"منبع فارسی: {citation['book_title_fa']}; ویرایش: {citation['edition_fa']}; "
        f"صفحه PDF {citation['pdf_page']} (صفحه چاپی {printed}); "
        f"document_sha256={citation['document_sha256']}; "
        f"{evidence}"
        f"page_id={page_id}; "
        f"exact_text_sha256={citation['exact_text_sha256']}"
    )


def citation_instructions(citation: JsonObject) -> str:
    """Return the exact Persian source text for the IDS instruction metadata."""
    validate_source_citation(citation)
    return f"متن دقیق فارسی: «{citation['exact_text_fa']}»"


def citation_hash(citation: JsonObject) -> str:
    """Return deterministic identity for a verified citation object."""
    validate_source_citation(citation)
    return hashlib.sha256(canonical_bytes(citation)).hexdigest()
