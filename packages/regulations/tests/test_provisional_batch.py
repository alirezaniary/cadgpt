from __future__ import annotations

import json
from pathlib import Path

import pytest
from cadgpt_regulations.provisional_batch import (
    ProvisionalBatchError,
    build_provisional_batch,
)

FIXTURE = Path(__file__).parent / "fixtures" / "inbr_transcript_volume10_page586.json"


def test_batch_preserves_existing_transcript_and_explicit_no_assertion() -> None:
    transcript = json.loads(FIXTURE.read_text(encoding="utf-8"))
    record_id = transcript["tables"][0]["record_id"]
    extraction = {
        "schema_version": "provisional-extraction-1.0.0",
        "items": [
            {
                "record_id": record_id,
                "outcome": "no_assertion",
                "reason": "table semantics require human review",
            }
        ],
    }
    result = build_provisional_batch(
        transcript,
        extraction,
        revision="luna-page-586",
        edition_fa="ویرایش ۱۴۰۱",
    )
    assert result["summary"] == {
        "records": 1,
        "candidates": 0,
        "no_assertion": 1,
        "unprocessed": 0,
        "duplicate_groups": 0,
    }
    assert result["outcomes"][0]["outcome"] == "no_assertion"


def test_batch_groups_duplicate_rules_without_dropping_candidates() -> None:
    transcript = json.loads(FIXTURE.read_text(encoding="utf-8"))
    table = transcript["tables"][0]
    transcript["tables"] = [
        dict(table, record_id="table-a"),
        dict(table, record_id="table-b"),
    ]
    extraction = {
        "schema_version": "provisional-extraction-1.0.0",
        "items": [
            {
                "record_id": "table-a",
                "outcome": "candidate",
                "rule": {"rule_key": "a", "value": 1},
            },
            {
                "record_id": "table-b",
                "outcome": "candidate",
                "rule": {"rule_key": "b", "value": 1},
            },
        ],
    }
    result = build_provisional_batch(
        transcript,
        extraction,
        revision="luna-duplicate",
        edition_fa="ویرایش ۱۴۰۱",
    )
    assert result["summary"]["candidates"] == 2
    assert result["summary"]["duplicate_groups"] == 1
    assert len(result["duplicate_groups"][0]["candidate_ids"]) == 2


def test_batch_reports_missing_transcript_records_as_unprocessed() -> None:
    transcript = json.loads(FIXTURE.read_text(encoding="utf-8"))
    result = build_provisional_batch(
        transcript,
        {"schema_version": "provisional-extraction-1.0.0", "items": []},
        revision="luna-unprocessed",
        edition_fa="ویرایش ۱۴۰۱",
    )
    assert result["summary"]["unprocessed"] == 1


def test_batch_qualifies_duplicate_record_ids_by_source_kind() -> None:
    transcript = json.loads(FIXTURE.read_text(encoding="utf-8"))
    table = transcript["tables"][0]
    transcript["sections"] = [dict(table, record_id=table["record_id"])]
    result = build_provisional_batch(
        transcript,
        {"schema_version": "provisional-extraction-1.0.0", "items": []},
        revision="luna-duplicate-record-id",
        edition_fa="ویرایش ۱۴۰۱",
    )
    assert result["summary"]["records"] == 2
    assert result["summary"]["unprocessed"] == 2


def test_batch_rejects_unversioned_extraction_response() -> None:
    transcript = json.loads(FIXTURE.read_text(encoding="utf-8"))
    with pytest.raises(ProvisionalBatchError, match="schema error"):
        build_provisional_batch(
            transcript,
            {"items": []},
            revision="luna-invalid-response",
            edition_fa="ویرایش ۱۴۰۱",
        )
