from __future__ import annotations

import json
from pathlib import Path

import pytest
from cadgpt_regulations.cli import main
from cadgpt_regulations.provisional_rule import (
    ProvisionalRuleError,
    make_candidate_citation,
    make_provisional_rule,
    make_transcript_revision,
    sandbox_only,
    validate_provisional_rule,
)
from cadgpt_regulations.transcript_citation import make_transcript_citation

FIXTURE = Path(__file__).parent / "fixtures" / "inbr_transcript_volume10_page586.json"


def test_existing_inbr_transcript_can_create_sandbox_candidate() -> None:
    transcript = json.loads(FIXTURE.read_text(encoding="utf-8"))
    source = transcript["source"]
    table = transcript["tables"][0]
    revision = make_transcript_revision(
        document_key=source["catalog_key"],
        revision="luna-fixture-1",
        transcript_fa=table["text_fa"],
        pdf_page=source["start_pdf_page"],
        printed_page_label=str(source["start_pdf_page"]),
        table_label=table.get("label_fa"),
        source_document_sha256=source["source_sha256"],
    )
    candidate = make_provisional_rule(
        rule={"rule_key": "fixture-rule", "requirement": {"kind": "attribute"}},
        transcript_revision=revision,
        review_flags=["OCR_SOURCE_NOT_EXACT", "OCR_SOURCE_NOT_EXACT"],
    )

    assert candidate["pdf_page"] == source["start_pdf_page"]
    assert candidate["table_label"] == table.get("label_fa")
    assert candidate["review_flags"] == ["OCR_SOURCE_NOT_EXACT"]
    assert sandbox_only(candidate)


def test_existing_inbr_luna_payload_gets_page_table_candidate_citation() -> None:
    transcript = json.loads(FIXTURE.read_text(encoding="utf-8"))
    source = transcript["source"]
    table = transcript["tables"][0]
    revision = make_transcript_revision(
        document_key=source["catalog_key"],
        revision="luna-page-586-1",
        transcript_fa=table["text_fa"],
        pdf_page=source["start_pdf_page"],
        printed_page_label=None,
        page_id=table["source_page_ids"][0],
        table_label="\u06f1\u06f0-\u06f6-\u06f5",
        source_document_sha256=source["source_sha256"],
        transcript_payload=transcript,
    )
    citation = make_candidate_citation(
        transcript_revision=revision,
        book_title_fa=transcript["title_fa"],
        edition_fa="ویرایش ۱۴۰۱",
        citation_status="needs_review",
    )
    candidate = make_provisional_rule(
        rule={"rule_key": "fire-temperature-factor", "requirement": {"kind": "table"}},
        transcript_revision=revision,
        candidate_citation=citation,
        review_flags=["OCR_SOURCE_NOT_EXACT"],
    )

    assert citation["pdf_page"] == 586
    assert citation["printed_page_label"] is None
    assert citation["table_label"] == "\u06f1\u06f0-\u06f6-\u06f5"
    assert citation["source_span_ids"] == []
    assert candidate["rule"]["source_citation"]["citation_status"] == "needs_review"
    assert candidate["transcript_sha256"] == revision["transcript_sha256"]
    assert revision["transcript_payload"] == transcript
    assert len(revision["transcript_payload_sha256"]) == 64
    assert sandbox_only(candidate)


def test_transcript_citation_uses_json_checkpoint_without_source_spans() -> None:
    transcript = json.loads(FIXTURE.read_text(encoding="utf-8"))
    source = transcript["source"]
    table = transcript["tables"][0]
    revision = make_transcript_revision(
        document_key=source["catalog_key"],
        revision="luna-checkpoint-1",
        transcript_fa=table["text_fa"],
        pdf_page=source["start_pdf_page"],
        printed_page_label=None,
        page_id=table["source_page_ids"][0],
        source_document_sha256=source["source_sha256"],
        transcript_payload=transcript,
        record_key=f"tables:{table['record_id']}",
    )
    citation = make_transcript_citation(
        revision, book_title_fa=transcript["title_fa"], edition_fa="ویرایش ۱۴۰۱"
    )
    assert citation["evidence_kind"] == "transcript"
    assert citation["source_node_ids"] == []
    assert citation["source_span_ids"] == []
    assert citation["printed_page_label"] is None
    assert citation["transcript_revision_id"] == revision["revision_id"]


def test_provisional_constructor_cannot_mark_candidate_published() -> None:
    revision = make_transcript_revision(
        document_key="inbr-volume-10",
        revision="luna-3",
        transcript_fa="متن جدول",
        pdf_page=586,
    )
    with pytest.raises(ProvisionalRuleError, match="cannot claim verified or published"):
        make_provisional_rule(
            rule={"rule_key": "x"}, transcript_revision=revision, state="published"
        )


def test_transcript_revision_is_immutable_and_correction_supersedes() -> None:
    first = make_transcript_revision(
        document_key="inbr-volume-10",
        revision="luna-1",
        transcript_fa="متن اولیه",
        pdf_page=586,
    )
    corrected = make_transcript_revision(
        document_key="inbr-volume-10",
        revision="human-2",
        transcript_fa="متن اصلاح‌شده",
        pdf_page=586,
        supersedes=first["revision_id"],
        state="corrected",
    )

    assert corrected["revision_id"] != first["revision_id"]
    assert corrected["supersedes"] == first["revision_id"]
    assert first["transcript_fa"] == "متن اولیه"


def test_revision_rejects_invalid_page() -> None:
    with pytest.raises(ProvisionalRuleError, match="pdf_page"):
        make_transcript_revision(
            document_key="inbr-volume-10",
            revision="bad",
            transcript_fa="متن",
            pdf_page=0,
        )


def test_candidate_constructor_cannot_bypass_release_as_published() -> None:
    revision = make_transcript_revision(
        document_key="inbr-volume-10",
        revision="luna-1",
        transcript_fa="متن",
        pdf_page=586,
    )
    with pytest.raises(
        ProvisionalRuleError,
        match="cannot claim verified or published",
    ):
        make_provisional_rule(
            rule={"rule_key": "r"}, transcript_revision=revision, state="published"
        )


def test_candidate_validator_rejects_tampered_published_state() -> None:
    revision = make_transcript_revision(
        document_key="inbr-volume-10",
        revision="luna-4",
        transcript_fa="متن",
        pdf_page=586,
    )
    candidate = make_provisional_rule(rule={"rule_key": "r"}, transcript_revision=revision)
    candidate["rule_state"] = "published"
    with pytest.raises(ProvisionalRuleError, match="cannot claim verified or published"):
        validate_provisional_rule(candidate)


def test_cli_writes_content_addressed_sandbox_candidate(tmp_path: Path) -> None:
    rule_path = tmp_path / "rule.json"
    rule_path.write_text('{"rule_key":"fire-factor-candidate"}', encoding="utf-8")
    output_root = tmp_path / "candidates"
    output_root.mkdir(mode=0o700)
    assert (
        main(
            [
                "provisional-rule",
                "--transcript",
                str(FIXTURE),
                "--rule",
                str(rule_path),
                "--output-root",
                str(output_root),
                "--revision",
                "luna-page-586-1",
                "--edition",
                "ویرایش ۱۴۰۱",
                "--table-index",
                "0",
                "--state",
                "needs_review",
            ]
        )
        == 0
    )
    assert len(list((output_root / "transcript-revisions").glob("*.json"))) == 1
    assert len(list((output_root / "candidates").glob("*.json"))) == 1
