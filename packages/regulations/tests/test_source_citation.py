from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from cadgpt_regulations.source_citation import (
    SourceCitation,
    SourceCitationError,
    exact_text_sha256,
    validate_source_citation,
)

FIXTURE = Path(__file__).parent / "fixtures" / "inbr_transcript_volume10_page586.json"


def _citation() -> dict[str, object]:
    transcript = json.loads(FIXTURE.read_text(encoding="utf-8"))
    source = transcript["source"]
    table = transcript["tables"][0]
    text = table["text_fa"]
    return {
        "document_key": source["catalog_key"],
        "book_title_fa": transcript["title_fa"],
        "edition_fa": "ویرایش ۱۴۰۱",
        "document_sha256": source["source_sha256"],
        "pdf_page": source["start_pdf_page"],
        "printed_page_label": str(source["start_pdf_page"]),
        "page_id": table["source_page_ids"][0],
        "source_node_ids": ["node:volume-10-edition-1401:page:000586:table:0001"],
        "source_span_ids": ["span:volume-10-edition-1401:page:000586:table:0001"],
        "exact_text_fa": text,
        "exact_text_sha256": exact_text_sha256(text),
        "qualifier_text_fa": None,
        "citation_status": "verified",
    }


def test_validate_and_round_trip_source_citation() -> None:
    value = _citation()

    validate_source_citation(value)
    citation = SourceCitation.from_mapping(value)

    assert citation.to_mapping() == value
    assert hashlib.sha256(citation.canonical_bytes()).hexdigest()


def test_rejects_exact_text_hash_mismatch() -> None:
    value = _citation()
    value["exact_text_sha256"] = "0" * 64

    with pytest.raises(SourceCitationError, match="exact_text_sha256"):
        validate_source_citation(value)


def test_source_graph_rejects_missing_source_span() -> None:
    value = _citation()
    value["source_span_ids"] = []

    with pytest.raises(SourceCitationError, match="source_span_ids"):
        SourceCitation.from_mapping(value)


def test_transcript_evidence_does_not_need_structural_spans_or_page_id() -> None:
    value = _citation()
    value.pop("source_node_ids")
    value.pop("source_span_ids")
    value.pop("page_id")
    value["printed_page_label"] = None
    value["evidence_kind"] = "transcript"
    value["transcript_revision_id"] = "revision-1"
    value["transcript_sha256"] = value["exact_text_sha256"]

    citation = SourceCitation.from_mapping(value)

    assert citation.page_id == "pdf-page:586"
    assert citation.source_span_ids == ()


def test_rejects_invalid_document_hash() -> None:
    value = _citation()
    value["document_sha256"] = "not-a-sha256"

    with pytest.raises(SourceCitationError, match="document_sha256"):
        validate_source_citation(value)
