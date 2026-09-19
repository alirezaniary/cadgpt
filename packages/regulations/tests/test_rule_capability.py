from __future__ import annotations

import hashlib
import json
from pathlib import Path

from cadgpt_regulations.rule_capability import classify_rule

FIXTURE = Path(__file__).parent / "fixtures" / "inbr_transcript_volume10_page586.json"


def _rule(extra: dict[str, object] | None = None) -> dict[str, object]:
    transcript = json.loads(FIXTURE.read_text(encoding="utf-8"))
    source = transcript["source"]
    table = transcript["tables"][0]
    exact = table["text_fa"]
    rule: dict[str, object] = {
        "schema_version": "rule-ir-1.0.0",
        "rule_key": "fire-factor",
        "title_fa": "ضریب مقاومت در دمای بالا",
        "ifc_versions": ["IFC4"],
        "entity": "IfcMember",
        "attribute": "Name",
        "comparator": "gte",
        "value": 1,
        "unit": None,
        "source_citation": {
            "document_key": source["catalog_key"],
            "book_title_fa": transcript["title_fa"],
            "edition_fa": "ویرایش ۱۴۰۱",
            "document_sha256": source["source_sha256"],
            "pdf_page": source["start_pdf_page"],
            "printed_page_label": str(source["start_pdf_page"]),
            "page_id": table["source_page_ids"][0],
            "source_node_ids": ["node:volume-10-edition-1401:page:000586:table:0001"],
            "source_span_ids": ["span:volume-10-edition-1401:page:000586:table:0001"],
            "exact_text_fa": exact,
            "exact_text_sha256": hashlib.sha256(exact.encode()).hexdigest(),
            "qualifier_text_fa": None,
            "citation_status": "verified",
        },
    }
    rule.update(extra or {})
    return rule


def test_classifies_native_inbr_rule_as_supported() -> None:
    result = classify_rule(_rule())

    assert result["status"] == "native_supported"
    assert result["source_citation"]["exact_text_fa"].startswith("جدول")


def test_defers_inbr_formula_without_losing_citation() -> None:
    result = classify_rule(_rule({"formula_fa": "F = ma"}))

    assert result["status"] == "deferred"
    assert result["reason_code"] == "FORMULA_REQUIRES_DERIVED_OBSERVATION"
    assert result["source_citation"]["exact_text_fa"].startswith("جدول")
    assert result["original_rule"]["formula_fa"] == "F = ma"


def test_defers_unsupported_comparator_deterministically() -> None:
    first = classify_rule(_rule({"comparator": "between"}))
    second = classify_rule(_rule({"comparator": "between"}))

    assert first == second
    assert first["reason_code"] == "UNSUPPORTED_COMPARATOR"


def _property_rule() -> dict[str, object]:
    transcript = json.loads(FIXTURE.read_text(encoding="utf-8"))
    source = transcript["source"]
    table = transcript["tables"][0]
    exact = table["text_fa"]
    return {
        "schema_version": "rule-ir-1.0.0",
        "rule_key": "space-min-net-floor-area",
        "title_fa": "حداقل مساحت خالص فضا",
        "ifc_versions": ["IFC4"],
        "entity": "IfcSpace",
        "requirement_kind": "property",
        "property_set": "Pset_SpaceCommon",
        "property_name": "NetFloorArea",
        "datatype": "double",
        "bounds": {"minInclusive": 9.0},
        "unit": "m2",
        "source_citation": {
            "document_key": source["catalog_key"],
            "book_title_fa": transcript["title_fa"],
            "edition_fa": "ویرایش ۱۴۰۱",
            "document_sha256": source["source_sha256"],
            "pdf_page": source["start_pdf_page"],
            "printed_page_label": str(source["start_pdf_page"]),
            "page_id": table["source_page_ids"][0],
            "source_node_ids": ["node:volume-10-edition-1401:page:000586:table:0001"],
            "source_span_ids": ["span:volume-10-edition-1401:page:000586:table:0001"],
            "exact_text_fa": exact,
            "exact_text_sha256": hashlib.sha256(exact.encode()).hexdigest(),
            "qualifier_text_fa": None,
            "citation_status": "verified",
        },
    }


def test_classifies_property_bounds_rule_as_supported() -> None:
    """H2: classify_rule hardcoded the attribute comparator set and deferred every
    property rule as UNSUPPORTED_COMPARATOR even though the compiler supports the
    shape natively (T-0105 fix). T-0108 is told to reuse classify_rule as-is."""
    result = classify_rule(_property_rule())

    assert result["status"] == "native_supported"
    assert result["source_citation"]["exact_text_fa"].startswith("جدول")


def test_still_defers_malformed_property_rule() -> None:
    malformed = _property_rule()
    malformed["datatype"] = "string"  # bounds stays numeric -> schema/shape mismatch
    result = classify_rule(malformed)

    assert result["status"] == "deferred"
    assert result["reason_code"] == "RULE_IR_INVALID"
