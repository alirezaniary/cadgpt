from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from pathlib import Path

import pytest
from cadgpt_regulations.cli import main
from cadgpt_regulations.jsonio import canonical_bytes
from cadgpt_regulations.provisional_rule import make_transcript_revision
from cadgpt_regulations.rule_compiler import compile_native_attribute_rule
from cadgpt_regulations.rule_release import (
    RuleReleaseError,
    build_rule_release_manifest,
    write_rule_release,
)
from cadgpt_regulations.transcript_citation import make_transcript_citation

FIXTURE = Path(__file__).parent / "fixtures" / "inbr_transcript_volume10_page586.json"


def _compiled(key: str):
    transcript = json.loads(FIXTURE.read_text(encoding="utf-8"))
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
    sidecar = dict(compiled.sidecar)
    sidecar["source_attestation"] = {
        "document_sha256": source["source_sha256"],
        "decision": "anchored",
        "report_sha256": hashlib.sha256(b"unit-reanchor-report").hexdigest(),
    }
    return replace(compiled, sidecar=sidecar)


def test_release_manifest_is_hash_pinned_and_citation_complete(tmp_path: Path) -> None:
    first = _compiled("fire-factor-a")
    second = _compiled("fire-factor-b")
    manifest = build_rule_release_manifest(
        [first, second],
        deferred_records=[{"record_id": "table-review-1"}],
        assertion_count=1,
    )

    assert manifest["release_id"]
    assert manifest["coverage"] == {
        "rules": 2,
        "verified_citations": 2,
        "documents": 1,
        "source_spans": 1,
        "assertions": 1,
        "deferred": 1,
    }
    assert all(item["source_span_ids"] for item in manifest["rules"])
    release_dir = write_rule_release(manifest, [first, second], output_root=tmp_path)
    assert (release_dir / "manifest.json").read_bytes()
    assert len(list((release_dir / "rules").glob("*.ids"))) == 2


def test_release_manifest_rejects_tampered_compiled_hash() -> None:
    compiled = _compiled("fire-factor-a")
    sidecar = dict(compiled.sidecar)
    sidecar["ids_sha256"] = "0" * 64
    tampered = replace(compiled, sidecar=sidecar)

    with pytest.raises(RuleReleaseError, match="IDS hash differs"):
        build_rule_release_manifest([tampered])


def test_release_manifest_rejects_verified_citation_without_attestation() -> None:
    compiled = _compiled("missing-attestation")
    sidecar = dict(compiled.sidecar)
    sidecar.pop("source_attestation", None)
    with pytest.raises(RuleReleaseError, match="source attestation"):
        build_rule_release_manifest([replace(compiled, sidecar=sidecar)])


def test_release_manifest_is_byte_deterministic() -> None:
    compiled = _compiled("fire-factor-a")
    first = build_rule_release_manifest([compiled], assertion_count=1)
    second = build_rule_release_manifest([compiled], assertion_count=1)

    assert first == second


def test_release_accepts_transcript_only_attestation() -> None:
    transcript = json.loads(FIXTURE.read_text(encoding="utf-8"))
    source = transcript["source"]
    table = transcript["tables"][0]
    revision = make_transcript_revision(
        document_key=source["catalog_key"],
        revision="luna-checkpoint-release",
        transcript_fa=table["text_fa"],
        pdf_page=source["start_pdf_page"],
        printed_page_label="۵۷۲",
        page_id=table["source_page_ids"][0],
        source_document_sha256=source["source_sha256"],
        transcript_payload=transcript,
        record_key=f"tables:{table['record_id']}",
    )
    citation = make_transcript_citation(
        revision, book_title_fa=transcript["title_fa"], edition_fa="ویرایش ۱۴۰۱"
    )
    citation.pop("page_id")
    citation.pop("source_node_ids")
    citation.pop("source_span_ids")
    compiled = compile_native_attribute_rule(
        {
            "schema_version": "rule-ir-1.0.0",
            "rule_key": "transcript-only-rule",
            "title_fa": "قاعده از متن JSON",
            "ifc_versions": ["IFC4"],
            "entity": "IfcMember",
            "attribute": "Name",
            "comparator": "gte",
            "value": 1,
            "unit": None,
            "source_citation": citation,
        }
    )
    manifest = build_rule_release_manifest([compiled])
    assert manifest["coverage"]["source_spans"] == 0


def test_cli_writes_transcript_backed_rule_release(tmp_path: Path) -> None:
    compiled = _compiled("fire-factor-a")
    rules_root = tmp_path / "compiled"
    rule_directory = rules_root / "rules" / compiled.rule_id
    rule_directory.mkdir(parents=True, mode=0o700)
    (rule_directory / "rule.ids").write_bytes(compiled.ids_xml)
    (rule_directory / "rule.json").write_bytes(canonical_bytes(compiled.sidecar))
    deferred = tmp_path / "deferred.jsonl"
    deferred.write_text(
        '{"record_id":"table-review-1","reason_code":"TABLE_REQUIRES_REVIEW"}\n',
        encoding="utf-8",
    )
    assertions = tmp_path / "assertions.json"
    assertions.write_text('{"assertions":[{"assertion_id":"a1"}]}', encoding="utf-8")
    output_root = tmp_path / "release"
    output_root.mkdir(mode=0o700)

    assert (
        main(
            [
                "rule-release",
                "--rules-root",
                str(rules_root),
                "--output-root",
                str(output_root),
                "--deferred",
                str(deferred),
                "--assertions",
                str(assertions),
            ]
        )
        == 0
    )
    manifests = list(output_root.glob("releases/*/manifest.json"))
    assert len(manifests) == 1
    assert json.loads(manifests[0].read_text(encoding="utf-8"))["coverage"]["deferred"] == 1


def test_release_writer_rejects_mismatched_release_id(tmp_path: Path) -> None:
    compiled = _compiled("fire-factor-a")
    manifest = build_rule_release_manifest([compiled])
    manifest["release_id"] = "0" * 64

    with pytest.raises(RuleReleaseError, match="release_id"):
        write_rule_release(manifest, [compiled], output_root=tmp_path)
