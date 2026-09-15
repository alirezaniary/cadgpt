from __future__ import annotations

import json
import re
from pathlib import Path

FIXTURE = Path(__file__).parent / "fixtures" / "inbr_transcript_volume10_page586.json"
SQL = Path(__file__).parents[1] / "sql" / "rule_projection.sql"


def test_projection_schema_is_page_first_and_keeps_only_core_tables() -> None:
    transcript = json.loads(FIXTURE.read_text(encoding="utf-8"))
    source = transcript["source"]
    sql = SQL.read_text(encoding="utf-8")

    for table in ("pdf_document", "pdf_page", "rule_candidate"):
        assert re.search(rf"CREATE TABLE IF NOT EXISTS {table} [(]", sql)
    for removed in (
        "provisional_batch",
        "transcript_revision",
        "candidate_occurrence",
        "source_span",
        "legal_assertion",
        "rule_occurrence",
        "rule_release",
        "executable_rule",
    ):
        assert not re.search(rf"CREATE TABLE IF NOT EXISTS {removed} [(]", sql)

    assert source["catalog_key"] not in sql
    assert re.fullmatch(r"[0-9a-f]{64}", source["source_sha256"])
    for column in (
        "document_key TEXT NOT NULL UNIQUE",
        "pdf_name TEXT NOT NULL",
        "file_path TEXT NOT NULL",
        "volume_number INTEGER",
        "edition_year INTEGER",
        "edition_code TEXT NOT NULL",
        "native_text TEXT",
        "native_layout_json JSONB",
        "paddle_text TEXT",
        "paddle_result_json JSONB",
        "luna_transcript_json JSONB",
        "luna_response_uri TEXT",
        "luna_response_sha256 CHAR(64)",
        "document_key TEXT NOT NULL REFERENCES pdf_document(document_key)",
        "primary_page_key TEXT NOT NULL",
        "source_record_key TEXT NOT NULL",
        "source_page_ids JSONB NOT NULL",
        "ids_specification JSONB",
        "implementation_type TEXT",
    ):
        assert column in sql
    assert "REFERENCES pdf_document(document_key)" in sql
    assert "FOREIGN KEY (document_key, primary_page_key)" in sql
    assert "REFERENCES pdf_page (document_key, page_key)" in sql
    assert "ON DELETE CASCADE" in sql
    # The IDS facet vocabulary is part of the candidate JSON contract.
    for facet in (
        "entity",
        "partOf",
        "classification",
        "attribute",
        "property",
        "material",
    ):
        assert facet in sql
