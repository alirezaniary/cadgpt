from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from cadgpt_regulations.citation import citation_instructions, validate_source_citation
from cadgpt_regulations.cli import main
from cadgpt_regulations.rule_compiler import RuleCompileError, compile_native_attribute_rule

FIXTURE = Path(__file__).parent / "fixtures" / "inbr_transcript_volume10_page586.json"


def _citation(transcript: dict[str, object]) -> dict[str, object]:
    source = transcript["source"]
    assert isinstance(source, dict)
    table = transcript["tables"][0]
    assert isinstance(table, dict)
    exact = table["text_fa"]
    assert isinstance(exact, str)
    return {
        "document_key": source["catalog_key"],
        "book_title_fa": transcript["title_fa"],
        "edition_fa": "ویرایش ۱۴۰۱",
        "document_sha256": source["source_sha256"],
        "pdf_page": 586,
        "printed_page_label": "586",
        "page_id": table["source_page_ids"][0],
        # Structural anchors are optional for transcript-backed citations.
        "source_node_ids": ["node:volume-10-edition-1401:page:000586:table:0001"],
        "source_span_ids": ["span:volume-10-edition-1401:page:000586:table:0001"],
        "exact_text_fa": exact,
        "exact_text_sha256": hashlib.sha256(exact.encode("utf-8")).hexdigest(),
        "qualifier_text_fa": None,
        "citation_status": "verified",
    }


def test_citation_is_built_from_existing_persian_transcript_fixture() -> None:
    transcript = json.loads(FIXTURE.read_text(encoding="utf-8"))
    citation = _citation(transcript)
    validate_source_citation(citation)
    assert citation["exact_text_fa"].splitlines()[0] in citation_instructions(citation)
    assert citation["pdf_page"] == transcript["source"]["start_pdf_page"]


def test_native_compiler_injects_exact_persian_source_metadata() -> None:
    transcript = json.loads(FIXTURE.read_text(encoding="utf-8"))
    citation = _citation(transcript)
    compiled = compile_native_attribute_rule(
        {
            "schema_version": "rule-ir-1.0.0",
            "rule_key": "fire-table-temperature-factor",
            "title_fa": "ضریب مقاومت در دمای بالا",
            "ifc_versions": ["IFC2X3", "IFC4"],
            "entity": "IfcMember",
            "attribute": "Name",
            "comparator": "gte",
            "value": 1,
            "unit": None,
            "source_citation": citation,
        }
    )
    xml = compiled.ids_xml.decode("utf-8")
    assert "مبحث دهم - حفاظت در برابر آتش" in xml
    assert "صفحه PDF 586" in xml
    assert citation["exact_text_fa"].splitlines()[0] in xml
    assert compiled.sidecar["source_citation"] == citation


def test_compiler_accepts_transcript_record_without_structural_spans() -> None:
    transcript = json.loads(FIXTURE.read_text(encoding="utf-8"))
    citation = _citation(transcript)
    citation.pop("source_node_ids")
    citation.pop("source_span_ids")
    citation.pop("page_id")
    citation["printed_page_label"] = None
    citation["evidence_kind"] = "transcript"
    citation["transcript_revision_id"] = "revision-1"
    citation["transcript_sha256"] = citation["exact_text_sha256"]

    compiled = compile_native_attribute_rule(
        {
            "schema_version": "rule-ir-1.0.0",
            "rule_key": "fire-table-temperature-factor",
            "title_fa": "ضریب مقاومت در دمای بالا",
            "ifc_versions": ["IFC4"],
            "entity": "IfcMember",
            "attribute": "Name",
            "comparator": "gte",
            "value": 1,
            "source_citation": citation,
        }
    )

    assert compiled.sidecar["source_citation"].get("source_span_ids", []) == []


def test_compiler_rejects_unsupported_comparator() -> None:
    transcript = json.loads(FIXTURE.read_text(encoding="utf-8"))
    citation = _citation(transcript)
    with pytest.raises(RuleCompileError, match="unsupported attribute comparator"):
        compile_native_attribute_rule(
            {
                "schema_version": "rule-ir-1.0.0",
                "rule_key": "fire-table-temperature-factor",
                "title_fa": "ضریب مقاومت در دمای بالا",
                "ifc_versions": ["IFC4"],
                "entity": "IfcMember",
                "attribute": "Name",
                "comparator": "between",
                "value": 1,
                "source_citation": citation,
            }
        )


def test_cli_compiles_rule_from_existing_transcript_fixture(tmp_path: Path) -> None:
    transcript = json.loads(FIXTURE.read_text(encoding="utf-8"))
    citation = _citation(transcript)
    rule_path = tmp_path / "rule.json"
    rule = {
        "schema_version": "rule-ir-1.0.0",
        "rule_key": "fire-table-temperature-factor",
        "title_fa": "ضریب مقاومت در دمای بالا",
        "ifc_versions": ["IFC4"],
        "entity": "IfcMember",
        "attribute": "Name",
        "comparator": "gte",
        "value": 1,
        "source_citation": citation,
    }
    rule_path.write_text(json.dumps(rule, ensure_ascii=False), encoding="utf-8")
    output_root = tmp_path / "rules"
    output_root.mkdir(mode=0o700)
    assert (
        main(
            [
                "compile-native-rule",
                "--rule",
                str(rule_path),
                "--output-root",
                str(output_root),
            ]
        )
        == 0
    )
    compiled = next(output_root.glob("rules/*/rule.ids"))
    assert citation["exact_text_fa"].splitlines()[0] in compiled.read_text(encoding="utf-8")
