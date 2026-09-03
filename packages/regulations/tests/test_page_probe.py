from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest
from cadgpt_regulations.errors import TranscriptionError
from cadgpt_regulations.jsonio import JsonObject, sha256_json
from cadgpt_regulations.page_probe import validate_page_probe


def _manifest() -> JsonObject:
    configuration_values: JsonObject = {
        "schema_version": "1.0.0",
        "render_dpi": 300,
        "page_timeout_seconds": 180,
        "parser_boundary": "crop_box",
        "thresholds": {
            "minimum_native_nonspace_chars": 20,
            "mixed_bitmap_coverage_permyriad": 1000,
            "scan_bitmap_coverage_permyriad": 8000,
            "blank_ink_coverage_permyriad": 30,
        },
    }
    configuration: JsonObject = {
        **configuration_values,
        "sha256": sha256_json(configuration_values),
    }
    toolchain: JsonObject = {
        "docling_parse": "7.16.0",
        "pypdfium2": "5.13.0",
        "pillow": "11.3.0",
        "tesseract": "tesseract 5.3.4",
        "tessdata_models": [],
    }
    source_sha256 = "a" * 64
    page = {
        "page_id": f"sha256:{source_sha256}:page:000001",
        "pdf_page": 1,
        "state": "ready",
        "classification": "native_text",
        "route": "native",
        "reason_codes": ["SUFFICIENT_NATIVE_TEXT"],
        "metrics": {
            "native_char_cells": 20,
            "native_nonspace_chars": 20,
            "native_word_cells": 4,
            "native_line_cells": 1,
            "bitmap_count": 0,
            "shape_count": 0,
            "bitmap_coverage_permyriad": 0,
            "ink_coverage_permyriad": 50,
            "render_width_pixels": 100,
            "render_height_pixels": 100,
        },
        "package_path": (
            f"pages/{source_sha256}/{configuration['sha256']}/"
            f"{sha256_json(toolchain)}/000001"
        ),
        "package_sha256": "b" * 64,
        "error": None,
    }
    document = {
        "catalog_key": "volume-01",
        "catalog_order": 1,
        "source_sha256": source_sha256,
        "source_bytes": 100,
        "pdf_page_count": 1,
        "artifact_path": "artifacts/volume-01.pdf",
        "pages": [page],
    }
    return {
        "schema_version": "1.0.0",
        "catalog": {
            "catalog_id": "fixture",
            "schema_version": "1.0.0",
            "sha256": "c" * 64,
            "provenance": [],
        },
        "acquisition": {"receipt_sha256": "d" * 64},
        "configuration": configuration,
        "toolchain": toolchain,
        "toolchain_sha256": sha256_json(toolchain),
        "selection": {"catalog_keys": ["volume-01"], "page_ranges": []},
        "documents": [document],
        "summary": {
            "documents_expected": 1,
            "documents_processed": 1,
            "pages_expected": 1,
            "pages_ready": 1,
            "pages_needs_review": 0,
            "pages_failed": 0,
            "classifications": {
                "blank": 0,
                "native_text": 1,
                "suspect_native": 0,
                "image_scan": 0,
                "mixed": 0,
                "degraded_photo": 0,
            },
            "routes": {"none": 0, "native": 1, "ocr": 0, "native_plus_ocr": 0},
        },
    }


def test_page_probe_rejects_missing_stored_package(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir(mode=0o700)

    with pytest.raises(TranscriptionError, match="cannot inspect"):
        validate_page_probe(_manifest(), root=root)


def test_page_probe_binds_document_coverage_to_acquisition() -> None:
    manifest = _manifest()
    document = manifest["documents"][0]  # type: ignore[index]
    acquisition: JsonObject = {
        "catalog": manifest["catalog"],
        "artifacts": [
            {
                "catalog_key": document["catalog_key"],
                "catalog_order": document["catalog_order"],
                "sha256": document["source_sha256"],
                "bytes": document["source_bytes"],
                "pdf_page_count": document["pdf_page_count"],
                "artifact_path": document["artifact_path"],
            }
        ],
    }
    acquisition_identity = manifest["acquisition"]
    assert isinstance(acquisition_identity, dict)
    acquisition_identity["receipt_sha256"] = sha256_json(acquisition)

    validate_page_probe(manifest, acquisition=acquisition)

    acquisition["artifacts"][0]["sha256"] = "e" * 64  # type: ignore[index]
    acquisition_identity["receipt_sha256"] = sha256_json(acquisition)
    with pytest.raises(TranscriptionError, match="coverage differs"):
        validate_page_probe(manifest, acquisition=acquisition)


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ("wrong_page_id", "page ID differs"),
        ("false_summary", "summary differs"),
        ("false_package_path", "false identity"),
        ("duplicate_page", "missing, duplicated, or reordered"),
        ("reverse_documents", "duplicated or reordered"),
        ("invalid_range", "positive, disjoint, and ordered"),
    ],
)
def test_page_probe_rejects_semantically_false_manifests(
    mutation: str, message: str
) -> None:
    manifest = deepcopy(_manifest())
    documents = manifest["documents"]
    assert isinstance(documents, list)
    document = documents[0]
    assert isinstance(document, dict)
    pages = document["pages"]
    assert isinstance(pages, list)
    page = pages[0]
    assert isinstance(page, dict)
    if mutation == "wrong_page_id":
        page["page_id"] = f"sha256:{'a' * 64}:page:000002"
    elif mutation == "false_summary":
        summary = manifest["summary"]
        assert isinstance(summary, dict)
        summary["pages_ready"] = 0
    elif mutation == "false_package_path":
        page["package_path"] = "pages/wrong/package"
    elif mutation == "duplicate_page":
        pages.append(deepcopy(page))
        summary = manifest["summary"]
        assert isinstance(summary, dict)
        summary["pages_expected"] = 2
        summary["pages_ready"] = 2
        classifications = summary["classifications"]
        routes = summary["routes"]
        assert isinstance(classifications, dict)
        assert isinstance(routes, dict)
        classifications["native_text"] = 2
        routes["native"] = 2
    elif mutation == "reverse_documents":
        second = deepcopy(document)
        second["catalog_key"] = "volume-02"
        second["catalog_order"] = 2
        documents.append(second)
        documents.reverse()
        selection = manifest["selection"]
        summary = manifest["summary"]
        assert isinstance(selection, dict)
        assert isinstance(summary, dict)
        selection["catalog_keys"] = ["volume-01", "volume-02"]
        summary["documents_expected"] = 2
        summary["documents_processed"] = 2
        summary["pages_expected"] = 2
        summary["pages_ready"] = 2
        classifications = summary["classifications"]
        routes = summary["routes"]
        assert isinstance(classifications, dict)
        assert isinstance(routes, dict)
        classifications["native_text"] = 2
        routes["native"] = 2
    else:
        selection = manifest["selection"]
        assert isinstance(selection, dict)
        selection["page_ranges"] = [{"start": 2, "end": 1}]

    with pytest.raises(TranscriptionError, match=message):
        validate_page_probe(manifest)
