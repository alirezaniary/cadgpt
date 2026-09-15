"""The real path: real IFC, real IDS, real output. No mocks anywhere in this file."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from cadgpt_engine import (
    REPORT_SCHEMA_VERSION,
    Applicability,
    InvalidIdsError,
    InvalidIfcError,
    ReasonCode,
    Status,
    run_check,
)

pytestmark = pytest.mark.integration


def test_the_real_path_separates_a_violation_from_missing_data(
    three_doors_ifc: Path, door_width_ids: Path
) -> None:
    """Three real doors, one real IDS, three different answers.

    This is the behaviour the product exists for: `ifctester` alone reports two failures
    here. Only one of them is a code violation.
    """
    report = run_check(three_doors_ifc, door_width_ids)

    assert report.ids_title == "Accessible door width"
    assert report.ifc_filename == "three_doors.ifc"
    assert (report.passed, report.failed, report.indeterminate) == (1, 1, 1)
    assert report.status is Status.FAIL
    assert report.specifications[0].applicability is Applicability.APPLIES
    assert report.specifications[0].matched == 3

    outcomes = {
        e.global_id: e
        for s in report.specifications
        for r in s.requirements
        for e in r.entities
    }
    assert len(outcomes) == 2, "only the two non-passing doors are itemised"

    narrow = outcomes["3worKcMPzD8x0Y1nJVBqA2"]
    assert narrow.status is Status.FAIL
    assert narrow.ifc_class == "IfcDoor"
    assert narrow.reason_code is ReasonCode.ATTRIBUTE_VALUE_MISMATCH
    assert "800.0" in narrow.detail, "the measured value is what a reviewer argues with"

    unknown = outcomes["3worKcMPzD8x0Y1nJVBqA3"]
    assert unknown.status is Status.INDETERMINATE
    assert unknown.reason_code is ReasonCode.ATTRIBUTE_EMPTY


def test_indeterminate_is_never_counted_as_a_pass(
    three_doors_ifc: Path, door_width_ids: Path
) -> None:
    report = run_check(three_doors_ifc, door_width_ids)
    spec = report.specifications[0]
    assert spec.passed == 1
    assert spec.passed + spec.failed + spec.indeterminate == 3
    assert spec.status is not Status.PASS
    assert report.checked == 3


def test_the_report_records_what_produced_it(
    three_doors_ifc: Path, door_width_ids: Path
) -> None:
    """An old run stays explainable only if it says which engine and schema made it."""
    report = run_check(three_doors_ifc, door_width_ids)
    assert report.ifc_schema.startswith("IFC")
    assert report.engine_version


def test_the_report_serializes_to_a_stable_json_document(
    three_doors_ifc: Path, door_width_ids: Path
) -> None:
    """This document is stored in the database and served to the browser."""
    document = run_check(three_doors_ifc, door_width_ids).to_dict()
    round_tripped = json.loads(json.dumps(document))

    assert round_tripped == document, "the document must survive a JSON round trip"
    assert round_tripped["schema_version"] == REPORT_SCHEMA_VERSION
    assert round_tripped["status"] == "FAIL"
    assert round_tripped["specifications"][0]["requirements"][0]["entities_omitted"] == 0

    statuses = {
        e["status"]
        for s in round_tripped["specifications"]
        for r in s["requirements"]
        for e in r["entities"]
    }
    assert statuses == {"FAIL", "INDETERMINATE"}


def test_counts_stay_exact_when_the_itemised_list_is_capped(
    three_doors_ifc: Path, door_width_ids: Path
) -> None:
    """Truncating the detail must never move a count. A capped list states its omission."""
    full = run_check(three_doors_ifc, door_width_ids)
    capped = run_check(three_doors_ifc, door_width_ids, entity_limit=1)

    assert (capped.passed, capped.failed, capped.indeterminate) == (
        full.passed,
        full.failed,
        full.indeterminate,
    )
    requirement = capped.specifications[0].requirements[0]
    assert len(requirement.entities) == 1
    assert requirement.entities_omitted == 1


def test_a_malformed_ids_is_refused_rather_than_partly_evaluated(tmp_path: Path) -> None:
    """A rule set that half-parses under-checks the model while looking complete."""
    bad = tmp_path / "broken.ids"
    bad.write_text("<ids>not an ids file</ids>", encoding="utf-8")
    with pytest.raises(InvalidIdsError):
        run_check(Path("/nonexistent.ifc"), bad)


def test_an_unparseable_ifc_is_a_typed_error(door_width_ids: Path, tmp_path: Path) -> None:
    """The API layer distinguishes a bad upload from a broken engine on this type."""
    bad = tmp_path / "broken.ifc"
    bad.write_text("this is not an IFC file", encoding="utf-8")
    with pytest.raises(InvalidIfcError):
        run_check(bad, door_width_ids)


def test_the_report_can_be_told_what_to_call_the_model(
    three_doors_ifc: Path, door_width_ids: Path
) -> None:
    """On a server the file is stored under a generated key, not its own name.

    A report naming a UUID is one the architect cannot match to their own work.
    """
    report = run_check(three_doors_ifc, door_width_ids, ifc_name="Block A - level 00.ifc")
    assert report.ifc_filename == "Block A - level 00.ifc"


def test_source_citation_in_ids_metadata_survives_engine_report(
    three_doors_ifc: Path, door_width_ids: Path, tmp_path: Path
) -> None:
    """Compiled Persian citations remain available without a corpus lookup."""
    transcript_path = (
        Path(__file__).parents[2]
        / "regulations"
        / "tests"
        / "fixtures"
        / "inbr_transcript_volume10_page586.json"
    )
    transcript = json.loads(transcript_path.read_text(encoding="utf-8"))
    exact_text = transcript["tables"][0]["text_fa"]
    title_fa = transcript["title_fa"]
    source_sha256 = transcript["source"]["source_sha256"]
    assert isinstance(exact_text, str)
    assert isinstance(title_fa, str)
    assert isinstance(source_sha256, str)
    source = door_width_ids.read_text(encoding="utf-8")
    cited = source.replace(
        '<ids:specification ifcVersion="IFC2X3 IFC4" '
        'name="Minimum clear door width 900 mm">',
        '<ids:specification ifcVersion="IFC2X3 IFC4" '
        'name="Minimum clear door width 900 mm" '
        f'description="منبع: {title_fa}؛ صفحه PDF 586؛ source_sha256={source_sha256}." '
        f'instructions="متن دقیق فارسی: {exact_text}">',
    )
    ids_path = tmp_path / "cited.ids"
    ids_path.write_text(cited, encoding="utf-8")

    report = run_check(three_doors_ifc, ids_path)
    specification = report.specifications[0]
    assert title_fa in specification.description
    assert source_sha256 in specification.description
    assert exact_text.splitlines()[0] in specification.instructions
    assert "متن دقیق فارسی" in specification.instructions
    serialized = report.to_dict()["specifications"][0]
    assert title_fa in serialized["description"]
    assert "متن دقیق فارسی" in serialized["instructions"]


def test_compiled_inbr_rule_runs_through_engine_and_keeps_citation(
    three_doors_ifc: Path, tmp_path: Path
) -> None:
    """The IDS consumed by the engine is generated by the citation-bearing compiler."""
    from cadgpt_regulations.rule_compiler import compile_native_attribute_rule

    transcript_path = (
        Path(__file__).parents[2]
        / "regulations"
        / "tests"
        / "fixtures"
        / "inbr_transcript_volume10_page586.json"
    )
    transcript = json.loads(transcript_path.read_text(encoding="utf-8"))
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
    compiled = compile_native_attribute_rule(
        {
            "schema_version": "rule-ir-1.0.0",
            "rule_key": "inbr-fire-factor-engine-regression",
            "title_fa": "ضریب مقاومت در دمای بالا",
            "ifc_versions": ["IFC4"],
            "entity": "IfcMember",
            "attribute": "Name",
            "comparator": "gte",
            "value": 1,
            "unit": None,
            "source_citation": citation,
        }
    )
    ids_path = tmp_path / "compiled-inbr.ids"
    ids_path.write_bytes(compiled.ids_xml)

    report = run_check(three_doors_ifc, ids_path)

    assert report.specifications[0].status is Status.FAIL
    assert report.specifications[0].reason_code is ReasonCode.NO_SUBJECTS_BUT_REQUIRED
    assert report.specifications[0].matched == 0
    assert exact.splitlines()[0] in report.specifications[0].instructions
    assert source["source_sha256"] in report.specifications[0].description


def test_compiled_inbr_rule_reports_compliant_entity_and_keeps_citation(
    three_doors_ifc: Path, tmp_path: Path
) -> None:
    """A compiler-produced Persian rule also preserves a passing engine outcome."""
    from cadgpt_regulations.rule_compiler import compile_native_attribute_rule

    transcript_path = (
        Path(__file__).parents[2]
        / "regulations"
        / "tests"
        / "fixtures"
        / "inbr_transcript_volume10_page586.json"
    )
    transcript = json.loads(transcript_path.read_text(encoding="utf-8"))
    source = transcript["source"]
    exact = transcript["tables"][0]["text_fa"]
    citation = {
        "document_key": source["catalog_key"],
        "book_title_fa": transcript["title_fa"],
        "edition_fa": "ویرایش ۱۴۰۱",
        "document_sha256": source["source_sha256"],
        "pdf_page": source["start_pdf_page"],
        "printed_page_label": str(source["start_pdf_page"]),
        "page_id": transcript["tables"][0]["source_page_ids"][0],
        "source_node_ids": ["node:volume-10-edition-1401:page:000586:table:0001"],
        "source_span_ids": ["span:volume-10-edition-1401:page:000586:table:0001"],
        "exact_text_fa": exact,
        "exact_text_sha256": hashlib.sha256(exact.encode()).hexdigest(),
        "qualifier_text_fa": None,
        "citation_status": "verified",
    }
    compiled = compile_native_attribute_rule(
        {
            "schema_version": "rule-ir-1.0.0",
            "rule_key": "inbr-door-width-engine-pass-regression",
            "title_fa": "حداقل عرض در",
            "ifc_versions": ["IFC4"],
            "entity": "IfcDoor",
            "attribute": "OverallWidth",
            "comparator": "gte",
            "value": 900,
            "unit": "mm",
            "source_citation": citation,
        }
    )
    ids_path = tmp_path / "compiled-inbr-pass.ids"
    ids_path.write_bytes(compiled.ids_xml)
    report = run_check(three_doors_ifc, ids_path)

    assert report.specifications[0].matched == 3
    assert report.specifications[0].passed == 1
    assert report.specifications[0].failed == 1
    assert report.specifications[0].indeterminate == 1
    assert exact.splitlines()[0] in report.specifications[0].instructions
