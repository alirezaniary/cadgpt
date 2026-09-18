from __future__ import annotations

import hashlib
import json
from pathlib import Path

from cadgpt_regulations.cli import main
from cadgpt_regulations.jsonio import validate_schema
from cadgpt_regulations.resources import load_packaged_json
from cadgpt_regulations.source_reanchor import reanchor_transcript

FIXTURE = Path(__file__).parent / "fixtures" / "inbr_transcript_volume10_page586.json"
EVIDENCE_FIXTURE = (
    Path(__file__).parent / "fixtures" / "inbr_volume10_page586_source_evidence.json"
)


def _graph_from_transcript(transcript: dict[str, object]) -> dict[str, object]:
    source = transcript["source"]
    assert isinstance(source, dict)
    page_id = source["bundle_id"]
    del page_id
    page_id = transcript["tables"][0]["source_page_ids"][0]  # type: ignore[index]
    text = transcript["tables"][0]["text_fa"]  # type: ignore[index]
    assert isinstance(page_id, str)
    assert isinstance(text, str)
    page_number = source["start_pdf_page"]
    assert isinstance(page_number, int)
    lines = text.splitlines()
    nodes = []
    for index, line in enumerate(lines, start=1):
        span = f"{page_id}:line:{index:04d}"
        nodes.append(
            {
                "node_id": f"{page_id}:structure:{index:06d}:native",
                "kind": "paragraph",
                "source_order": index,
                "pdf_page": page_number,
                "parent_id": None,
                "children_ids": [],
                "printed_label": None,
                "source_kind": "native",
                "source_span_ids": [span],
                "raw_text": line,
                "normalized_text": line,
                "bbox": [0, 0, 100, 20],
                "state": "ready",
            }
        )
    table_id = f"{page_id}:table:0000"
    return {
        "schema_version": "1.0.0",
        "catalog_key": source["catalog_key"],
        "catalog_order": 10,
        "source_sha256": source["source_sha256"],
        "pdf_page_count": 1,
        "pages": [
            {
                "page_id": page_id,
                "pdf_page": page_number,
                "printed_page_label": str(page_number),
                "state": "ready",
                "reason_codes": [],
                "source_artifacts": [],
                "node_ids": [node["node_id"] for node in nodes],
                "formula_ids": [],
                "unit_ids": [],
                "abbreviation_ids": [],
                "table_ids": [table_id],
            }
        ],
        "nodes": nodes,
        "tables": [
            {
                "table_id": table_id,
                "pdf_page": page_number,
                "source_span_ids": [node["source_span_ids"][0] for node in nodes],
                "reasons": [],
                "rows": [],
                "state": "needs_review",
                "diagnostics": [],
            }
        ],
        "formulas": [],
        "units": [],
        "abbreviations": [],
        "continuation_edges": [],
        "counts": {
            "pages": 1,
            "nodes": len(nodes),
            "tables": 1,
            "formulas": 0,
            "units": 0,
            "abbreviations": 0,
            "continuation_edges": 0,
            "needs_review": 1,
        },
    }


def test_reanchors_existing_inbr_table_and_regenerates_exact_source_quote() -> None:
    transcript = json.loads(FIXTURE.read_text(encoding="utf-8"))
    result = reanchor_transcript(transcript, _graph_from_transcript(transcript))

    table = result.transcript["tables"][0]
    assert isinstance(table, dict)
    exact = table["text_fa"]
    assert isinstance(exact, str)
    decision = result.report["decisions"][0]
    assert decision["status"] == "anchored"
    assert decision["exact_text_fa"] == exact
    assert decision["exact_text_sha256"] == hashlib.sha256(exact.encode()).hexdigest()
    assert table["source_span_ids"]
    assert result.report["summary"]["publishable"] is True
    validate_schema(
        result.transcript,
        load_packaged_json(
            "cadgpt_regulations.schemas", "structured-transcript.schema.json"
        ),
        description="re-anchored transcript",
    )


def test_does_not_guess_when_existing_inbr_text_is_not_in_structural_nodes() -> None:
    transcript = json.loads(FIXTURE.read_text(encoding="utf-8"))
    graph = _graph_from_transcript(transcript)
    graph["nodes"] = graph["nodes"][:-1]

    result = reanchor_transcript(transcript, graph)

    table = result.transcript["tables"][0]
    assert isinstance(table, dict)
    assert table["source_span_ids"] == []
    decision = result.report["decisions"][0]
    assert decision["status"] == "unmatched"
    assert result.report["summary"]["publishable"] is False


def test_live_volume10_page586_evidence_fails_closed_without_structural_graph() -> None:
    """The real p586 package is OCR evidence, not yet a T-0027 source graph."""
    transcript = json.loads(FIXTURE.read_text(encoding="utf-8"))
    evidence = json.loads(EVIDENCE_FIXTURE.read_text(encoding="utf-8"))
    assert evidence["native"]["line_count"] == 0
    assert evidence["attestation"]["structural_graph_available"] is False

    page_id = evidence["page_id"]
    graph = {
        "schema_version": "1.0.0",
        "catalog_key": evidence["catalog_key"],
        "catalog_order": 11,
        "source_sha256": evidence["source_sha256"],
        "pdf_page_count": 590,
        "pages": [
            {
                "page_id": page_id,
                "pdf_page": evidence["pdf_page"],
                "printed_page_label": None,
                "state": "needs_review",
                "reason_codes": evidence["reason_codes"],
                "source_artifacts": [],
                "node_ids": [],
                "formula_ids": [],
                "unit_ids": [],
                "abbreviation_ids": [],
                "table_ids": [],
            }
        ],
        "nodes": [],
        "tables": [],
        "formulas": [],
        "units": [],
        "abbreviations": [],
        "continuation_edges": [],
        "counts": {
            "pages": 1,
            "nodes": 0,
            "tables": 0,
            "formulas": 0,
            "units": 0,
            "abbreviations": 0,
            "continuation_edges": 0,
            "needs_review": 1,
        },
    }

    result = reanchor_transcript(transcript, graph)
    assert result.report["summary"]["publishable"] is False
    assert result.report["decisions"][0]["status"] == "unmatched"
    assert result.report["decisions"][0]["reason"] == "no_exact_contiguous_match"
    assert result.transcript["tables"][0]["source_span_ids"] == []


def test_rejects_existing_anchor_that_points_to_different_inbr_text() -> None:
    transcript = json.loads(FIXTURE.read_text(encoding="utf-8"))
    graph = _graph_from_transcript(transcript)
    table = transcript["tables"][0]
    assert isinstance(table, dict)
    table["source_span_ids"] = [graph["nodes"][0]["source_span_ids"][0]]  # type: ignore[index]

    result = reanchor_transcript(transcript, graph)

    decision = result.report["decisions"][0]
    assert decision["status"] == "invalid_existing_anchor"
    assert decision["reason"] == "existing_spans_do_not_match_record_text"
    assert result.report["summary"]["publishable"] is False


def test_cli_reanchors_existing_inbr_fixture(tmp_path: Path) -> None:
    transcript = json.loads(FIXTURE.read_text(encoding="utf-8"))
    transcript_path = tmp_path / "transcript.json"
    graph_path = tmp_path / "graph.json"
    transcript_path.write_text(json.dumps(transcript, ensure_ascii=False), encoding="utf-8")
    graph_path.write_text(
        json.dumps(_graph_from_transcript(transcript), ensure_ascii=False),
        encoding="utf-8",
    )
    output_root = tmp_path / "output"
    output_root.mkdir(mode=0o700)

    assert (
        main(
            [
                "reanchor-transcript",
                "--transcript",
                str(transcript_path),
                "--graph",
                str(graph_path),
                "--output-root",
                str(output_root),
            ]
        )
        == 0
    )
    assert (output_root / "reanchored" / "transcript.json").exists()
    assert (output_root / "reanchored" / "report.json").exists()
