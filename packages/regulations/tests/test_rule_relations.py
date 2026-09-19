from __future__ import annotations

import hashlib
import json
from pathlib import Path

from cadgpt_regulations.rule_relations import build_occurrence_assertions

FIXTURE = Path(__file__).parent / "fixtures" / "inbr_transcript_volume10_page586.json"


def _rule(
    transcript: dict[str, object], *, key: str, comparator: str = "gte"
) -> dict[str, object]:
    source = transcript["source"]
    table = transcript["tables"][0]
    exact = table["text_fa"]
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
        "exact_text_fa": exact,
        "exact_text_sha256": hashlib.sha256(exact.encode()).hexdigest(),
        "qualifier_text_fa": None,
        "citation_status": "verified",
    }
    return {
        "schema_version": "rule-ir-1.0.0",
        "rule_key": key,
        "title_fa": "ضریب مقاومت در دمای بالا",
        "ifc_versions": ["IFC4"],
        "entity": "IfcMember",
        "attribute": "Name",
        "comparator": comparator,
        "value": 1,
        "unit": None,
        "source_citation": citation,
    }


def test_groups_duplicate_inbr_rule_occurrences_but_keeps_both_citations() -> None:
    transcript = json.loads(FIXTURE.read_text(encoding="utf-8"))
    relations = build_occurrence_assertions(
        [
            _rule(transcript, key="fire-factor-a"),
            _rule(transcript, key="fire-factor-b"),
        ]
    )

    assert relations["summary"] == {
        "input_occurrences": 2,
        "assertions": 1,
        "duplicates_collapsed": 1,
    }
    assertion = relations["assertions"][0]
    assert len(assertion["occurrence_ids"]) == 2
    assert len(relations["occurrences"]) == 2
    assert all(
        item["source_citation"]["exact_text_fa"] for item in relations["occurrences"]
    )


def test_keeps_distinct_inbr_rule_semantics_as_distinct_assertions() -> None:
    transcript = json.loads(FIXTURE.read_text(encoding="utf-8"))
    relations = build_occurrence_assertions(
        [
            _rule(transcript, key="fire-factor-gte", comparator="gte"),
            _rule(transcript, key="fire-factor-lte", comparator="lte"),
        ]
    )

    assert relations["summary"]["assertions"] == 2
    assert relations["summary"]["duplicates_collapsed"] == 0


def _property_rule(
    transcript: dict[str, object], *, key: str, min_inclusive: float = 9.0
) -> dict[str, object]:
    source = transcript["source"]
    table = transcript["tables"][0]
    exact = table["text_fa"]
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
        "exact_text_fa": exact,
        "exact_text_sha256": hashlib.sha256(exact.encode()).hexdigest(),
        "qualifier_text_fa": None,
        "citation_status": "verified",
    }
    return {
        "schema_version": "rule-ir-1.0.0",
        "rule_key": key,
        "title_fa": "حداقل مساحت خالص فضا",
        "ifc_versions": ["IFC4"],
        "entity": "IfcSpace",
        "requirement_kind": "property",
        "property_set": "Pset_SpaceCommon",
        "property_name": "NetFloorArea",
        "datatype": "double",
        "bounds": {"minInclusive": min_inclusive},
        "unit": "m2",
        "source_citation": citation,
    }


def test_groups_duplicate_property_rule_occurrences_without_crashing() -> None:
    """H1: _semantic_identity used to KeyError on any property-kind rule (T-0105 fix)."""
    transcript = json.loads(FIXTURE.read_text(encoding="utf-8"))
    relations = build_occurrence_assertions(
        [
            _property_rule(transcript, key="space-area-a"),
            _property_rule(transcript, key="space-area-b"),
        ]
    )

    assert relations["summary"] == {
        "input_occurrences": 2,
        "assertions": 1,
        "duplicates_collapsed": 1,
    }
    assert len(relations["assertions"][0]["occurrence_ids"]) == 2


def test_keeps_distinct_property_bounds_as_distinct_assertions() -> None:
    transcript = json.loads(FIXTURE.read_text(encoding="utf-8"))
    relations = build_occurrence_assertions(
        [
            _property_rule(transcript, key="space-area-9", min_inclusive=9.0),
            _property_rule(transcript, key="space-area-12", min_inclusive=12.0),
        ]
    )

    assert relations["summary"]["assertions"] == 2
    assert relations["summary"]["duplicates_collapsed"] == 0


def test_attribute_and_property_rules_never_collide() -> None:
    transcript = json.loads(FIXTURE.read_text(encoding="utf-8"))
    relations = build_occurrence_assertions(
        [
            _rule(transcript, key="fire-factor-attr"),
            _property_rule(transcript, key="space-area-prop"),
        ]
    )

    assert relations["summary"]["assertions"] == 2
    assert relations["summary"]["duplicates_collapsed"] == 0
