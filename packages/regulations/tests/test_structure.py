from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

import pytest
from cadgpt_regulations.errors import StructureError
from cadgpt_regulations.jsonio import sha256_json
from cadgpt_regulations.structure import (
    _align_alternate_lines,
    _formula_record,
    _page_lines,
    _printed_label,
    _repeated_numeric_labels,
    _unit_record,
    _validate_graph_schema,
    build_structure,
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
                "source_artifacts": [],
                "node_ids": [node_id],
                "formula_ids": [],
                "unit_ids": [],
                "abbreviation_ids": [],
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
                "normalized_text": "source",
                "bbox": [0, 0, 10, 10],
                "state": "ready",
            }
        ],
        "tables": [],
        "formulas": [],
        "units": [],
        "abbreviations": [],
        "continuation_edges": [],
        "counts": {
            "pages": 1,
            "nodes": 1,
            "tables": 0,
            "formulas": 0,
            "units": 0,
            "abbreviations": 0,
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


def test_alternate_lines_are_not_linked_by_position_when_text_differs() -> None:
    canonical = [
        {"span_id": "ocr-1", "raw_text": "اول"},
        {"span_id": "ocr-2", "raw_text": "دوم"},
    ]
    native = [
        {"span_id": "native-extra", "raw_text": "عنوان"},
        {"span_id": "native-1", "raw_text": "اول"},
        {"span_id": "native-2", "raw_text": "دوم"},
    ]

    aligned = _align_alternate_lines(canonical, native)

    assert [line["span_id"] if line is not None else None for line in aligned] == [
        "native-1",
        "native-2",
    ]


@pytest.mark.parametrize(
    ("raw_text", "expected"),
    [
        ("  2  -5  -1  -1  عنوان", "2-5-1-1"),
        ("\u06f2 - \u06f5 - \u06f1", "\u06f2-\u06f5-\u06f1"),
        ("978-600-301-002-4 ISBN", None),
        (
            (
                "\u06f9\u06f7\u06f8-\u06f6\u06f0\u06f0-"
                "\u06f3\u06f0\u06f1-\u06f0\u06f0\u06f2-\u06f4 ISBN"
            ),
            None,
        ),
        ("30.000", None),
    ],
)
def test_printed_label_normalizes_spaced_hyphens_and_rejects_numeric_artifacts(
    raw_text: str, expected: str | None
) -> None:
    assert _printed_label({"raw_text": raw_text, "bbox": [100, 100, 300, 200]}) == expected


def test_printed_label_rejects_running_header_in_page_margin() -> None:
    line = {
        "raw_text": "1-1",
        "bbox": [100, 900, 300, 950],
        "_coordinate_height": 1000,
    }

    assert _printed_label(line) is None


def test_repeated_numeric_labels_are_identified_as_running_headers(tmp_path: Path) -> None:
    pages: list[dict[str, object]] = []
    for page_number in (1, 2, 3):
        probe_path = Path("probe") / f"{page_number:06d}"
        evidence_path = Path("evidence") / f"{page_number:06d}"
        native = {
            "coordinate_space": {
                "height": 1000,
                "origin": "bottom_left",
            },
            "lines": [
                {
                    "span_id": f"native-{page_number}",
                    "raw_text": "1-1",
                    "bbox": [100, 450, 200, 470],
                }
            ],
        }
        _write_bytes(tmp_path / probe_path / "native.json", json.dumps(native).encode())
        evidence = {
            "probe": {
                "package_path": probe_path.as_posix(),
                "route": "native",
            }
        }
        _write_bytes(
            tmp_path / evidence_path / "evidence.json", json.dumps(evidence).encode()
        )
        pages.append({"pdf_page": page_number, "package_path": evidence_path.as_posix()})

    repeated = _repeated_numeric_labels(
        {"pages": pages},
        root=tmp_path,
    )

    assert repeated == {"1-1"}


def test_mixed_native_plus_ocr_keeps_native_text_and_adds_unique_ocr_lines(
    tmp_path: Path,
) -> None:
    package = Path("page")
    native_path = tmp_path / "probe" / "native.json"
    ocr_path = tmp_path / package / "ocr.json"
    _write_bytes(
        native_path,
        json.dumps(
            {
                "coordinate_space": {"height": 1000},
                "lines": [
                    {
                        "span_id": "native-1",
                        "raw_text": "Native text",
                        "bbox": [0, 100, 10, 110],
                    }
                ],
            }
        ).encode(),
    )
    _write_bytes(
        ocr_path,
        json.dumps(
            {
                "coordinate_space": {"height": 1000},
                "lines": [
                    {
                        "span_id": "ocr-duplicate",
                        "raw_text": "Native text",
                        "bbox": [0, 100, 10, 110],
                    },
                    {
                        "span_id": "ocr-unique",
                        "raw_text": "OCR figure caption",
                        "bbox": [0, 200, 10, 210],
                    },
                ],
            }
        ).encode(),
    )
    evidence = {
        "probe": {
            "package_path": "probe",
            "route": "native_plus_ocr",
            "classification": "mixed",
        }
    }

    lines = _page_lines(evidence, package=package, root=tmp_path)

    assert [line["span_id"] for line in lines] == ["native-1", "ocr-unique"]


def _write_bytes(path: Path, payload: bytes) -> None:
    missing: list[Path] = []
    current = path.parent
    while not current.exists():
        missing.append(current)
        current = current.parent
    for directory in reversed(missing):
        directory.mkdir(mode=0o700)
    path.write_bytes(payload)
    path.chmod(0o600)


def _sha_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _real_transcription_with_abbreviation(root: Path) -> dict[str, object]:
    """Build a real, on-disk transcription with a page carrying a real LRFD mention.

    Mirrors the on-disk package layout `cadgpt_regulations.transcription` writes, so
    `build_structure()` exercises its real re-attestation path rather than a
    hand-mutated manifest (per the review's note that none of the four existing
    tests here ever call `build_structure()`).
    """
    source_sha256 = "b" * 64
    page_id = f"sha256:{source_sha256}:page:000001"
    span_id = f"{page_id}:native:line:000000"

    probe_relative = Path("probe") / "000001"
    native_bytes = json.dumps(
        {
            "lines": [
                {"span_id": span_id, "raw_text": "Design per LRFD", "bbox": [0, 0, 10, 10]}
            ]
        },
        sort_keys=True,
    ).encode()
    render_bytes = b"render-bytes"
    _write_bytes(root / probe_relative / "native.json", native_bytes)
    _write_bytes(root / probe_relative / "render.png", render_bytes)
    page_package_bytes = json.dumps(
        {
            "artifacts": [
                {
                    "role": "native_layout",
                    "path": (probe_relative / "native.json").as_posix(),
                    "sha256": _sha_bytes(native_bytes),
                    "bytes": len(native_bytes),
                    "media_type": "application/json",
                },
                {
                    "role": "source_render",
                    "path": (probe_relative / "render.png").as_posix(),
                    "sha256": _sha_bytes(render_bytes),
                    "bytes": len(render_bytes),
                    "media_type": "image/png",
                },
            ]
        },
        sort_keys=True,
    ).encode()
    _write_bytes(root / probe_relative / "page.json", page_package_bytes)

    evidence_relative = Path("evidence") / "000001"
    raw_native_bytes = b"Design per LRFD\n"
    normalized_bytes = b"Design per LRFD\n"
    digits_bytes = b"Design per LRFD\n"
    model_bytes = b"jpeg-bytes"
    _write_bytes(root / evidence_relative / "raw-native.txt", raw_native_bytes)
    _write_bytes(root / evidence_relative / "normalized.txt", normalized_bytes)
    _write_bytes(root / evidence_relative / "digits-ascii.txt", digits_bytes)
    _write_bytes(root / evidence_relative / "model.jpg", model_bytes)

    abbreviation_candidate = {
        "candidate_id": f"{page_id}:abbreviation:0000",
        "kind": "method_abbreviation",
        "source_kind": "native",
        "span_id": span_id,
        "raw_text": "LRFD",
        "bbox": [0, 0, 10, 10],
        "crop_file": None,
    }
    evidence = {
        "schema_version": "1.0.0",
        "page_id": page_id,
        "source": {
            "catalog_key": "volume-01",
            "catalog_order": 1,
            "sha256": source_sha256,
            "bytes": 100,
            "pdf_page_count": 1,
            "pdf_page": 1,
            "printed_page_label": None,
        },
        "probe": {
            "package_path": probe_relative.as_posix(),
            "package_sha256": _sha_bytes(page_package_bytes),
            "configuration_sha256": "b" * 64,
            "toolchain_sha256": "c" * 64,
            "classification": "native_text",
            "route": "native",
        },
        "configuration_sha256": "d" * 64,
        "state": "ready",
        "reason_codes": ["SUFFICIENT_NATIVE_TEXT"],
        "normalization": {
            "native": {"version": "1.0.0", "operations": [], "protected_views": []},
            "ocr": None,
            "combined_policy": "native",
            "digit_view": "persian_and_arabic_indic_to_ascii",
        },
        "ocr": None,
        "semantic_evidence": {"symbols": [abbreviation_candidate], "tables": []},
        "artifacts": [
            {
                "role": "raw_native_text",
                "path": (evidence_relative / "raw-native.txt").as_posix(),
                "sha256": _sha_bytes(raw_native_bytes),
                "bytes": len(raw_native_bytes),
                "media_type": "text/plain; charset=utf-8",
            },
            {
                "role": "normalized_search_text",
                "path": (evidence_relative / "normalized.txt").as_posix(),
                "sha256": _sha_bytes(normalized_bytes),
                "bytes": len(normalized_bytes),
                "media_type": "text/plain; charset=utf-8",
            },
            {
                "role": "ascii_digit_view",
                "path": (evidence_relative / "digits-ascii.txt").as_posix(),
                "sha256": _sha_bytes(digits_bytes),
                "bytes": len(digits_bytes),
                "media_type": "text/plain; charset=utf-8",
            },
            {
                "role": "model_input_render",
                "path": (evidence_relative / "model.jpg").as_posix(),
                "sha256": _sha_bytes(model_bytes),
                "bytes": len(model_bytes),
                "media_type": "image/jpeg",
            },
        ],
        "error": None,
    }
    evidence_bytes = json.dumps(evidence, sort_keys=True).encode()
    _write_bytes(root / evidence_relative / "evidence.json", evidence_bytes)

    model_input_bytes = len(model_bytes) + len(normalized_bytes)
    page_record = {
        "page_id": page_id,
        "pdf_page": 1,
        "state": "ready",
        "classification": "native_text",
        "route": "native",
        "reason_codes": ["SUFFICIENT_NATIVE_TEXT"],
        "printed_page_label": None,
        "package_path": evidence_relative.as_posix(),
        "package_sha256": _sha_bytes(evidence_bytes),
        "normalized_sha256": _sha_bytes(normalized_bytes),
        "normalized_chars": len(normalized_bytes.decode()),
        "model_input_bytes": model_input_bytes,
        "error": None,
    }

    bundle_relative = Path("bundles") / "000001.json"
    bundle_id = f"sha256:{source_sha256}:bundle:000001-000001:test"
    bundle = {
        "schema_version": "1.0.0",
        "bundle_id": bundle_id,
        "catalog_key": "volume-01",
        "source_sha256": source_sha256,
        "configuration_sha256": "e" * 64,
        "sequence": 1,
        "start_pdf_page": 1,
        "end_pdf_page": 1,
        "page_count": 1,
        "input_bytes": model_input_bytes,
        "byte_ceiling": 8 * 1024 * 1024,
        "pages": [
            {
                "page_id": page_id,
                "pdf_page": 1,
                "state": "ready",
                "span_ids": [span_id],
                "raw_native_text_path": (evidence_relative / "raw-native.txt").as_posix(),
                "normalized_text_path": (evidence_relative / "normalized.txt").as_posix(),
                "model_render_path": (evidence_relative / "model.jpg").as_posix(),
                "input_bytes": model_input_bytes,
            }
        ],
        "continuation_edges": [],
        "fallback": "page_by_page",
    }
    bundle_bytes = json.dumps(bundle, sort_keys=True).encode()
    _write_bytes(root / bundle_relative, bundle_bytes)

    document = {
        "catalog_key": "volume-01",
        "catalog_order": 1,
        "source_sha256": source_sha256,
        "source_bytes": 100,
        "pdf_page_count": 1,
        "artifact_path": "artifacts/volume-01.pdf",
        "pages": [page_record],
        "bundles": [
            {
                "bundle_id": bundle_id,
                "sequence": 1,
                "start_pdf_page": 1,
                "end_pdf_page": 1,
                "page_count": 1,
                "input_bytes": model_input_bytes,
                "path": bundle_relative.as_posix(),
                "sha256": _sha_bytes(bundle_bytes),
            }
        ],
    }

    configuration_values = {
        "schema_version": "1.0.0",
        "normalization_version": "1.0.0",
        "ocr_timeout_seconds": 180,
        "ocr_languages": ["fas", "eng"],
        "ocr_primary_psm": 3,
        "ocr_dense_fallback_psm": 6,
        "ocr_general_review_confidence_permyriad": 6000,
        "ocr_critical_review_confidence_permyriad": 7500,
        "bundle_max_pages": 10,
        "bundle_max_bytes": 8 * 1024 * 1024,
        "model_max_edge": 1600,
        "model_jpeg_quality": 82,
    }
    configuration = {**configuration_values, "sha256": sha256_json(configuration_values)}

    return {
        "schema_version": "1.0.0",
        "catalog": {"catalog_id": "fixture"},
        "acquisition": {"receipt_sha256": "f" * 64},
        "probe": {
            "sha256": "1" * 64,
            "configuration_sha256": "2" * 64,
            "toolchain_sha256": "3" * 64,
        },
        "configuration": configuration,
        "ocr_toolchain": None,
        "documents": [document],
        "summary": {
            "documents_expected": 1,
            "documents_processed": 1,
            "pages_expected": 1,
            "pages_ready": 1,
            "pages_needs_review": 0,
            "pages_failed": 0,
            "ocr_pages": 0,
            "bundles": 1,
        },
    }


def test_build_structure_anchors_method_abbreviation_candidates(tmp_path: Path) -> None:
    """Regression test for F8: `method_abbreviation` candidates were dropped.

    `_build_document_graph` only branched on ``kind == "equation"`` and
    ``kind == "unit_mention"``; a ``method_abbreviation`` candidate (e.g. "LRFD")
    was read off the page evidence and never appended anywhere. This calls the
    real `build_structure()` (per the review's note that the existing four tests
    never do) and asserts the candidate now lands in a real `abbreviations` list,
    anchored to its source span like formulas and units are.
    """
    transcription_root = tmp_path / "transcription"
    transcription_root.mkdir(mode=0o700)
    transcription = _real_transcription_with_abbreviation(transcription_root)
    structure_output_root = tmp_path / "structure"
    structure_output_root.mkdir(mode=0o700)

    run = build_structure(
        transcription,
        transcription_root=transcription_root,
        output_root=structure_output_root,
    )

    document = run.manifest["documents"][0]
    assert document["counts"]["abbreviations"] == 1
    assert run.manifest["summary"]["abbreviations"] == 1

    graph_path = structure_output_root / document["path"]
    graph = json.loads(graph_path.read_text(encoding="utf-8"))
    assert len(graph["abbreviations"]) == 1
    record = graph["abbreviations"][0]
    assert record["printed"] == "LRFD"
    source_sha256 = "b" * 64
    page_id = f"sha256:{source_sha256}:page:000001"
    span_id = f"{page_id}:native:line:000000"
    assert record["source_span_ids"] == [span_id]
    assert graph["pages"][0]["abbreviation_ids"] == [record["abbreviation_id"]]
