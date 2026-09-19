from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from cadgpt_regulations.candidate_to_rule_ir import (
    CandidateToRuleIRError,
    build_candidate_to_rule_ir_batch,
    validate_ifc_mapping,
)
from cadgpt_regulations.provisional_rule import (
    make_candidate_citation,
    make_provisional_rule,
    make_transcript_revision,
)

FIXTURE = Path(__file__).parent / "fixtures" / "inbr_transcript_volume10_page586.json"
EDITION_FA = "ویرایش ۱۴۰۱"


def _transcript() -> dict[str, Any]:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def _candidate_and_revision(
    *, rule_key: str, rule_extra: dict[str, Any], record_key_suffix: str = "1"
) -> tuple[dict[str, Any], dict[str, Any]]:
    transcript = _transcript()
    source = transcript["source"]
    table = transcript["tables"][0]
    revision = make_transcript_revision(
        document_key=source["catalog_key"],
        revision=f"luna-join-{record_key_suffix}",
        transcript_fa=table["text_fa"],
        pdf_page=source["start_pdf_page"],
        printed_page_label=str(source["start_pdf_page"]),
        page_id=table["source_page_ids"][0],
        source_document_sha256=source["source_sha256"],
        transcript_payload=transcript,
        record_key=f"tables:{table['record_id']}",
    )
    citation = make_candidate_citation(
        transcript_revision=revision,
        book_title_fa=transcript["title_fa"],
        edition_fa=EDITION_FA,
        citation_status="needs_review",
    )
    candidate = make_provisional_rule(
        rule={
            "rule_key": rule_key,
            "title_fa": "عنوان قاعده",
            "statement_fa": table["text_fa"],
            "implementation_type": "native_ids",
            "classification": "dimensional_requirement",
            "source_record_id": table["record_id"],
            "source_page_ids": table["source_page_ids"],
            **rule_extra,
        },
        transcript_revision=revision,
        state="needs_review",
        candidate_citation=citation,
        review_flags=["SEMANTIC_REVIEW_PENDING"],
    )
    return candidate, revision


def _document_key() -> str:
    return _transcript()["source"]["catalog_key"]


def test_mapped_candidate_produces_valid_property_rule_ir() -> None:
    candidate, revision = _candidate_and_revision(
        rule_key="fire-factor-property", rule_extra={}
    )
    mapping = {
        "schema_version": "ifc-target-mapping-1.0.0",
        "entries": [
            {
                "document_key": _document_key(),
                "rule_key": "fire-factor-property",
                "ifc_versions": ["IFC4"],
                "entity": "IFCMEMBER",
                "requirement_kind": "property",
                "property_set": "Pset_ACC_FireResistance",
                "property_name": "StrengthRetentionFactor",
                "datatype": "double",
                "bounds": {"minInclusive": 0.97},
                "unit": None,
            }
        ],
    }
    result = build_candidate_to_rule_ir_batch([candidate], [revision], mapping)

    assert result["summary"] == {"candidates": 1, "mapped": 1, "unmapped": 0}
    assert len(result["mapped"]) == 1
    rule_ir = result["mapped"][0]
    assert rule_ir["rule_key"] == "fire-factor-property"
    assert rule_ir["requirement_kind"] == "property"
    assert rule_ir["property_set"] == "Pset_ACC_FireResistance"
    assert rule_ir["source_citation"]["citation_status"] == "verified"
    assert rule_ir["source_citation"]["document_key"] == _document_key()
    assert result["unmapped"] == []


def test_mapped_candidate_produces_valid_attribute_rule_ir() -> None:
    candidate, revision = _candidate_and_revision(
        rule_key="fire-factor-attribute", rule_extra={}
    )
    mapping = {
        "schema_version": "ifc-target-mapping-1.0.0",
        "entries": [
            {
                "document_key": _document_key(),
                "rule_key": "fire-factor-attribute",
                "ifc_versions": ["IFC4"],
                "entity": "IFCMEMBER",
                "attribute": "Name",
                "comparator": "gte",
                "value": 1,
                "unit": None,
            }
        ],
    }
    result = build_candidate_to_rule_ir_batch([candidate], [revision], mapping)

    assert result["summary"] == {"candidates": 1, "mapped": 1, "unmapped": 0}
    rule_ir = result["mapped"][0]
    assert rule_ir["rule_key"] == "fire-factor-attribute"
    assert "requirement_kind" not in rule_ir
    assert rule_ir["attribute"] == "Name"
    assert rule_ir["comparator"] == "gte"


def test_candidate_without_mapping_entry_is_unmapped_not_dropped() -> None:
    candidate, revision = _candidate_and_revision(rule_key="no-mapping-here", rule_extra={})
    empty_mapping = {"schema_version": "ifc-target-mapping-1.0.0", "entries": []}

    result = build_candidate_to_rule_ir_batch([candidate], [revision], empty_mapping)

    assert result["summary"] == {"candidates": 1, "mapped": 0, "unmapped": 1}
    assert result["mapped"] == []
    unmapped = result["unmapped"][0]
    assert unmapped["rule_key"] == "no-mapping-here"
    assert unmapped["reason_code"] == "no_mapping_entry"
    assert unmapped["candidate_id"] == candidate["candidate_id"]


def test_candidate_with_tampered_transcript_revision_is_rejected_outright() -> None:
    transcript = _transcript()
    source = transcript["source"]
    table = transcript["tables"][0]
    # The revision's own hash fields are internally self-consistent (it passes
    # validate_transcript_revision), but source_document_sha256 disagrees with the
    # transcript payload it carries -- exactly the integrity break a candidate must
    # never be allowed to compile past.
    revision = make_transcript_revision(
        document_key=source["catalog_key"],
        revision="luna-tampered-1",
        transcript_fa=table["text_fa"],
        pdf_page=source["start_pdf_page"],
        printed_page_label=str(source["start_pdf_page"]),
        page_id=table["source_page_ids"][0],
        source_document_sha256="0" * 64,
        transcript_payload=transcript,
        record_key=f"tables:{table['record_id']}",
    )
    citation = {
        "document_key": revision["document_key"],
        "book_title_fa": transcript["title_fa"],
        "edition_fa": EDITION_FA,
        "document_sha256": revision["source_document_sha256"],
        "pdf_page": revision["pdf_page"],
        "printed_page_label": revision["printed_page_label"],
        "page_id": revision["page_id"],
        "source_node_ids": [],
        "source_span_ids": [],
        "exact_text_fa": revision["transcript_fa"],
        "exact_text_sha256": revision["transcript_sha256"],
        "qualifier_text_fa": None,
        "citation_status": "needs_review",
        "transcript_revision_id": revision["revision_id"],
        "transcript_sha256": revision["transcript_sha256"],
        "table_label": None,
        "section_label": None,
    }
    candidate = make_provisional_rule(
        rule={
            "rule_key": "tampered-rule",
            "title_fa": "عنوان قاعده",
            "statement_fa": table["text_fa"],
            "implementation_type": "native_ids",
            "classification": "dimensional_requirement",
        },
        transcript_revision=revision,
        state="needs_review",
        candidate_citation=citation,
    )
    mapping = {"schema_version": "ifc-target-mapping-1.0.0", "entries": []}

    with pytest.raises(CandidateToRuleIRError, match="rejected outright"):
        build_candidate_to_rule_ir_batch([candidate], [revision], mapping)


def test_ifc_mapping_rejects_duplicate_document_and_rule_key() -> None:
    entry = {
        "document_key": "doc-a",
        "rule_key": "rule-a",
        "ifc_versions": ["IFC4"],
        "entity": "IFCWALL",
        "attribute": "Name",
        "comparator": "eq",
        "value": 1,
    }
    with pytest.raises(CandidateToRuleIRError, match="duplicate IFC mapping entry"):
        validate_ifc_mapping(
            {"schema_version": "ifc-target-mapping-1.0.0", "entries": [entry, dict(entry)]}
        )
