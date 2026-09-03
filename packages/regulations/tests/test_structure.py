from __future__ import annotations

import copy

import pytest
from cadgpt_regulations.errors import StructureError
from cadgpt_regulations.structure import (
    _formula_record,
    _unit_record,
    _validate_graph_schema,
)


def _span() -> str:
    return "sha256:" + "a" * 64 + ":page:000007:native:line:000003"


def _graph() -> dict[str, object]:
    span = _span()
    page_id = "sha256:" + "a" * 64 + ":page:000007"
    node_id = f"{page_id}:structure:000001:native"
    return {
        "schema_version": "1.0.0",
        "catalog_key": "volume-01",
        "catalog_order": 1,
        "source_sha256": "a" * 64,
        "pdf_page_count": 1,
        "pages": [
            {
                "page_id": page_id,
                "pdf_page": 7,
                "printed_page_label": "1",
                "state": "ready",
                "reason_codes": [],
                "node_ids": [node_id],
                "formula_ids": [],
                "unit_ids": [],
                "table_ids": [],
            }
        ],
        "nodes": [
            {
                "node_id": node_id,
                "kind": "paragraph",
                "source_order": 1,
                "pdf_page": 7,
                "parent_id": None,
                "children_ids": [],
                "printed_label": None,
                "source_kind": "native",
                "source_span_ids": [span],
                "raw_text": "source",
                "bbox": [0, 0, 10, 10],
                "state": "ready",
            }
        ],
        "tables": [],
        "formulas": [],
        "units": [],
        "continuation_edges": [],
        "counts": {
            "pages": 1,
            "nodes": 1,
            "tables": 0,
            "formulas": 0,
            "units": 0,
            "continuation_edges": 0,
            "needs_review": 0,
        },
    }


def test_formula_record_preserves_source_and_defers_semantic_math() -> None:
    span = _span()
    record = _formula_record(
        {
            "candidate_id": "formula-1",
            "crop_file": "formula-crops/0000.png",
            "raw_text": "F = ma",
            "span_id": span,
            "source_kind": "native",
            "bbox": [1, 2, 3, 4],
        },
        crop_artifacts={
            "0000.png": {
                "path": "page/formula-crops/0000.png",
                "sha256": "b" * 64,
                "bytes": 12,
            }
        },
    )

    assert record["raw_transcription"] == "F = ma"
    assert record["unicode"] == "F = ma"
    assert record["latex"] is None
    assert record["content_mathml"] is None
    assert record["parse_status"] == "needs_review"
    assert "<mtext>F = ma</mtext>" in record["presentation_mathml"]


def test_unit_record_maps_only_known_printed_units() -> None:
    candidate = {
        "candidate_id": "unit-1",
        "raw_text": "MPa",
        "span_id": _span(),
        "source_kind": "native",
        "bbox": [1, 2, 3, 4],
    }

    assert _unit_record(candidate, page_id="page")["ucum_code"] == "MPa"
    candidate["raw_text"] = "ambiguous"
    unknown = _unit_record(candidate, page_id="page")
    assert unknown["ucum_code"] is None
    assert unknown["mapping_status"] == "unknown"


def test_source_graph_schema_rejects_unknown_fields() -> None:
    graph = _graph()
    _validate_graph_schema(graph)
    invalid = copy.deepcopy(graph)
    invalid["invented"] = True

    with pytest.raises(StructureError, match="schema error"):
        _validate_graph_schema(invalid)
