import hashlib
import json
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest
from cadgpt_regulations.ids_compiler import CompilerError, compile_native_rule

FIXTURE = Path(__file__).parent / "fixtures" / "inbr_transcript_volume10_page586.json"


def _rule():
    transcript = json.loads(FIXTURE.read_text(encoding="utf-8"))
    source = transcript["source"]
    table = transcript["tables"][0]
    exact = table["text_fa"]
    return {
        "rule_key": "fire-temperature-factor",
        "title": transcript["title_fa"],
        "entity": "IFCMEMBER",
        "ifc_version": ["IFC2X3", "IFC4"],
        "requirement": {
            "kind": "attribute",
            "name": "Name",
            "datatype": "double",
            "comparator": "minInclusive",
            "value": 1,
        },
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
            "citation_status": "verified",
        },
    }


def test_compile_is_deterministic_and_carries_citation():
    transcript = json.loads(FIXTURE.read_text(encoding="utf-8"))
    first = compile_native_rule(_rule())
    second = compile_native_rule(_rule())
    assert first.ids_xml == second.ids_xml
    assert first.sidecar == second.sidecar
    assert first.rule_id.startswith("rule-")
    root = ET.fromstring(first.ids_xml)  # noqa: S314 - parser input is compiler output
    ns = {"ids": "http://standards.buildingsmart.org/IDS"}
    specification = root.find("ids:specifications/ids:specification", ns)
    assert specification is not None
    text = "".join(root.itertext())
    assert transcript["title_fa"] in text
    assert transcript["tables"][0]["text_fa"].splitlines()[0] in text
    assert first.sidecar["source_citation"]["source_span_ids"] == [
        "span:volume-10-edition-1401:page:000586:table:0001"
    ]


def test_rejects_unverified_or_tampered_citation():
    rule = _rule()
    rule["source_citation"]["citation_status"] = "needs_review"
    with pytest.raises(CompilerError, match="citation_status"):
        compile_native_rule(rule)
    rule = _rule()
    rule["source_citation"]["exact_text_sha256"] = "b" * 64
    with pytest.raises(CompilerError, match="does not match"):
        compile_native_rule(rule)


def test_compiles_transcript_citation_without_structural_spans():
    rule = _rule()
    citation = rule["source_citation"]
    citation.pop("source_node_ids")
    citation.pop("source_span_ids")
    citation.pop("page_id")
    citation["evidence_kind"] = "transcript"
    citation["transcript_revision_id"] = "revision-1"
    citation["transcript_sha256"] = citation["exact_text_sha256"]

    compiled = compile_native_rule(rule)

    assert compiled.sidecar["source_citation"]["evidence_kind"] == "transcript"
    assert compiled.sidecar["source_citation"]["page_id"] == "pdf-page:586"
    assert "source_span_ids=" not in compiled.ids_xml.decode("utf-8")


def test_property_rule_requires_property_set():
    rule = _rule()
    rule["requirement"] = {
        "kind": "property",
        "name": "FireRating",
        "datatype": "string",
        "comparator": "exact",
        "value": "EI60",
    }
    with pytest.raises(CompilerError, match="property_set"):
        compile_native_rule(rule)
