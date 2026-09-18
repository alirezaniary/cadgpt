from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from pathlib import Path

import pytest
from cadgpt_regulations.jsonio import canonical_bytes
from cadgpt_regulations.rule_compiler import compile_native_attribute_rule
from cadgpt_regulations.rule_projection import (
    RuleProjectionError,
    build_page_projection_rows,
    build_projection_rows,
)
from cadgpt_regulations.rule_release import build_rule_release_manifest

FIXTURE = Path(__file__).parent / "fixtures" / "inbr_transcript_volume10_page586.json"
PAGE_586 = (
    "sha256:01d7fd2055f323cc59ed910a4b982f0feb40f39e35fc513f5f6d7840d4b357bc:page:000586"
)
PAGE_587 = (
    "sha256:01d7fd2055f323cc59ed910a4b982f0feb40f39e35fc513f5f6d7840d4b357bc:page:000587"
)


def _page_source() -> dict:
    return {
        "documents": [
            {
                "catalog_key": "volume-10-edition-1401",
                "source_sha256": (
                    "01d7fd2055f323cc59ed910a4b982f0feb40f39e35fc513f5f6d7840d4b357bc"
                ),
                "source_bytes": 10,
                "pdf_page_count": 2,
                "pages": [
                    {
                        "page_id": PAGE_586,
                        "pdf_page": 586,
                        "route": "ocr",
                        "state": "ready",
                        "luna_transcript_json": {"page_id": PAGE_586, "text_fa": "source"},
                        "luna_transcript_text": "source",
                        "luna_transcript_sha256": "1" * 64,
                    },
                    {
                        "page_id": PAGE_587,
                        "pdf_page": 587,
                        "route": "ocr",
                        "state": "ready",
                    },
                ],
            }
        ]
    }


def _compiled(key: str = "fire-factor-a"):
    transcript = json.loads(FIXTURE.read_text(encoding="utf-8"))
    source = transcript["source"]
    table = transcript["tables"][0]
    exact = table["text_fa"]
    transcript_hash = hashlib.sha256(canonical_bytes(transcript)).hexdigest()
    citation = {
        "document_key": source["catalog_key"],
        "book_title_fa": transcript["title_fa"],
        "edition_fa": "ویرایش ۱۴۰۱",
        "document_sha256": source["source_sha256"],
        "pdf_page": source["start_pdf_page"],
        "printed_page_label": str(source["start_pdf_page"]),
        "page_id": table["source_page_ids"][0],
        "source_node_ids": [],
        "source_span_ids": [],
        "exact_text_fa": exact,
        "exact_text_sha256": hashlib.sha256(exact.encode()).hexdigest(),
        "qualifier_text_fa": None,
        "citation_status": "verified",
        "evidence_kind": "transcript",
        "transcript_revision_id": "luna-chunk-300",
        "transcript_sha256": transcript_hash,
    }
    compiled = compile_native_attribute_rule(
        {
            "schema_version": "rule-ir-1.0.0",
            "rule_key": key,
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
    return replace(
        compiled,
        sidecar={
            **compiled.sidecar,
            "source_attestation": {
                "document_sha256": source["source_sha256"],
                "decision": "transcript",
                "transcript_revision_id": "luna-chunk-300",
                "transcript_sha256": transcript_hash,
            },
        },
    )


def test_projection_rows_match_three_table_page_first_shape() -> None:
    compiled = _compiled()
    rows = build_projection_rows(
        build_rule_release_manifest([compiled]), [compiled], page_source=_page_source()
    )

    assert set(rows) == {"pdf_documents", "pdf_pages", "rule_candidates"}
    assert len(rows["pdf_documents"]) == 1
    assert len(rows["pdf_pages"]) == 2
    assert len(rows["rule_candidates"]) == 1
    document = rows["pdf_documents"][0]
    page = next(item for item in rows["pdf_pages"] if item["pdf_page_number"] == 586)
    candidate = rows["rule_candidates"][0]
    assert document["document_key"] == "volume-10-edition-1401"
    assert document["volume_number"] == 10
    assert document["edition_year"] == 1401
    assert document["edition_code"] == "edition-1401"
    assert page["document_key"] == document["document_key"]
    assert page["pdf_page_number"] == 586
    assert page["luna_transcript_json"]["text_fa"]
    assert candidate["document_key"] == document["document_key"]
    assert candidate["primary_page_key"] == page["page_key"]
    assert candidate["implementation_type"] == "native_ids"
    assert (
        candidate["ids_specification"]["applicability"][0]["entity"]["name"] == "IFCMEMBER"
    )
    assert "assertions" not in rows
    assert "source_spans" not in rows


def test_projection_rows_are_idempotent() -> None:
    compiled = _compiled()
    manifest = build_rule_release_manifest([compiled])
    assert build_projection_rows(
        manifest, [compiled], page_source=_page_source()
    ) == build_projection_rows(manifest, [compiled], page_source=_page_source())


def test_projection_rejects_compiled_sidecar_outside_release_manifest() -> None:
    compiled = _compiled()
    manifest = build_rule_release_manifest([compiled])
    sidecar = dict(compiled.sidecar)
    sidecar["compiler_version"] = "tampered"
    with pytest.raises(RuleProjectionError, match="hashes differ"):
        build_projection_rows(
            manifest, [replace(compiled, sidecar=sidecar)], page_source=_page_source()
        )


def test_projection_supports_a_rule_spanning_two_pages() -> None:
    compiled = _compiled("cross-page")
    sidecar = dict(compiled.sidecar)
    sidecar["source_pages"] = [
        {
            "page_id": PAGE_586,
            "pdf_page": 586,
            "role": "source",
        },
        {
            "page_id": PAGE_587,
            "pdf_page": 587,
            "role": "continuation",
        },
    ]
    compiled = replace(compiled, sidecar=sidecar)
    rows = build_projection_rows(
        build_rule_release_manifest([compiled]), [compiled], page_source=_page_source()
    )
    assert len(rows["pdf_pages"]) == 2
    assert rows["rule_candidates"][0]["source_page_ids"] == [
        {
            "page_id": PAGE_586,
            "pdf_page": 586,
            "role": "source",
        },
        {
            "page_id": PAGE_587,
            "pdf_page": 587,
            "role": "continuation",
        },
    ]


def test_page_projection_keeps_physical_pages_without_candidates() -> None:
    source = {
        "documents": [
            {
                "catalog_key": "volume-10-edition-1401",
                "source_sha256": "0" * 64,
                "source_bytes": 10,
                "pdf_page_count": 2,
                "pages": [
                    {
                        "page_id": PAGE_586,
                        "pdf_page": 586,
                        "route": "ocr",
                        "state": "ready",
                    },
                    {
                        "page_id": PAGE_587,
                        "pdf_page": 587,
                        "route": "ocr",
                        "state": "ready",
                    },
                ],
            }
        ]
    }
    documents, pages = build_page_projection_rows(source)
    assert len(documents) == 1
    assert [page["pdf_page_number"] for page in pages] == [586, 587]
