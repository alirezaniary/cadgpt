"""Citations verified against the permanent JSON transcript checkpoint only.

PDF hashes and page numbers are copied provenance. This module has no source
file, OCR, structural graph, network, or model dependency.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, cast

from cadgpt_regulations.errors import RegulationsError
from cadgpt_regulations.jsonio import JsonObject
from cadgpt_regulations.provisional_rule import validate_transcript_revision
from cadgpt_regulations.source_citation import validate_source_citation


class TranscriptCitationError(RegulationsError):
    """Raised when a citation differs from its pinned transcript record."""


def make_transcript_citation(
    revision: Mapping[str, Any], *, book_title_fa: str, edition_fa: str
) -> JsonObject:
    """Verify quotation provenance in JSON; this does not approve rule semantics."""
    validate_transcript_revision(revision)
    payload = revision.get("transcript_payload")
    key = revision.get("record_key")
    if not isinstance(payload, Mapping) or not isinstance(key, str) or ":" not in key:
        raise TranscriptCitationError(
            "transcript payload and qualified record_key required"
        )
    collection, record_id = key.split(":", 1)
    records = payload.get(collection)
    if not isinstance(records, list):
        raise TranscriptCitationError("record collection is absent from transcript")
    matches = [
        record
        for record in records
        if isinstance(record, Mapping) and record.get("record_id") == record_id
    ]
    if len(matches) != 1:
        raise TranscriptCitationError("transcript record_key must resolve uniquely")
    record = matches[0]
    source = payload.get("source")
    if (
        not isinstance(source, Mapping)
        or source.get("catalog_key") != revision["document_key"]
        or source.get("source_sha256") != revision["source_document_sha256"]
        or record.get("text_fa") != revision["transcript_fa"]
    ):
        raise TranscriptCitationError("revision differs from transcript record or source")
    pages = record.get("source_page_ids", [])
    page_id = revision.get("page_id")
    if not isinstance(page_id, str):
        page_id = next(
            (
                value
                for value in pages
                if isinstance(value, str)
                and value.rsplit(":", 1)[-1].isdigit()
                and int(value.rsplit(":", 1)[-1]) == revision["pdf_page"]
            ),
            None,
        )
    if not isinstance(page_id, str) or page_id not in pages:
        raise TranscriptCitationError("revision page is absent from transcript record")
    page_number = page_id.rsplit(":", 1)[-1]
    if not page_number.isdigit() or int(page_number) != revision["pdf_page"]:
        raise TranscriptCitationError("revision page number differs from transcript page")
    citation: JsonObject = {
        "document_key": revision["document_key"],
        "book_title_fa": book_title_fa,
        "edition_fa": edition_fa,
        "document_sha256": revision["source_document_sha256"],
        "pdf_page": revision["pdf_page"],
        "printed_page_label": revision["printed_page_label"],
        "page_id": page_id,
        "source_node_ids": [],
        "source_span_ids": [],
        "exact_text_fa": revision["transcript_fa"],
        "exact_text_sha256": revision["transcript_sha256"],
        "qualifier_text_fa": None,
        "citation_status": "verified",
        "evidence_kind": "transcript",
        "transcript_revision_id": revision["revision_id"],
        "transcript_sha256": revision["transcript_sha256"],
    }
    validate_source_citation(citation)
    return citation


def validate_transcript_citation(
    citation: Mapping[str, Any], revision: Mapping[str, Any]
) -> None:
    """Rebuild the citation from JSON and reject any changed identity or text."""
    validate_source_citation(cast(JsonObject, dict(citation)))
    expected = make_transcript_citation(
        revision,
        book_title_fa=cast(str, citation["book_title_fa"]),
        edition_fa=cast(str, citation["edition_fa"]),
    )
    if dict(citation) != expected:
        raise TranscriptCitationError("citation differs from pinned transcript revision")
