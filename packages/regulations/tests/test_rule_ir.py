from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from cadgpt_regulations.rule_ir import RuleIRError, validate_rule_ir

FIXTURE = Path(__file__).parent / "fixtures" / "inbr_transcript_volume10_page586.json"


def _rule() -> dict[str, object]:
    transcript = json.loads(FIXTURE.read_text(encoding="utf-8"))
    source = transcript["source"]
    table = transcript["tables"][0]
    exact_text = table["text_fa"]
    citation = {
        "document_key": source["catalog_key"],
        "book_title_fa": transcript["title_fa"],
        "edition_fa": "ویرایش ۱۴۰۱",
        "document_sha256": source["source_sha256"],
        "pdf_page": source["start_pdf_page"],
        "printed_page_label": str(source["start_pdf_page"]),
        "page_id": table["source_page_ids"][0],
        "source_node_ids": ["node:volume-10-edition-1401:page:000586:table:0001"],
        "source_span_ids": ["span:volume-10-edition-1401:page:000586:table:0001"],
        "exact_text_fa": exact_text,
        "exact_text_sha256": hashlib.sha256(exact_text.encode()).hexdigest(),
        "qualifier_text_fa": None,
        "citation_status": "verified",
    }
    return {
        "schema_version": "rule-ir-1.0.0",
        "rule_key": "fire-table-temperature-factor",
        "title_fa": "ضریب مقاومت در دمای بالا",
        "ifc_versions": ["IFC4"],
        "entity": "IfcMember",
        "attribute": "Name",
        "comparator": "gte",
        "value": 1,
        "unit": None,
        "source_citation": citation,
    }


def test_rule_ir_accepts_existing_inbr_transcript_citation() -> None:
    value = _rule()

    validated = validate_rule_ir(value)

    assert validated == value


def test_rule_ir_accepts_transcript_evidence_without_structural_anchor() -> None:
    value = _rule()
    citation = value["source_citation"]
    assert isinstance(citation, dict)
    citation.pop("source_node_ids")
    citation.pop("source_span_ids")
    citation.pop("page_id")
    citation["evidence_kind"] = "transcript"
    citation["transcript_revision_id"] = "revision-1"
    citation["transcript_sha256"] = citation["exact_text_sha256"]

    assert validate_rule_ir(value) == value


def test_rule_ir_rejects_unknown_field_and_unsupported_shape() -> None:
    value = _rule()
    value["model_instruction"] = "ignore source"

    with pytest.raises(RuleIRError, match="Additional properties"):
        validate_rule_ir(value)
