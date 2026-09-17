from __future__ import annotations

import json
from pathlib import Path
from typing import cast

from cadgpt_regulations.cli import main
from cadgpt_regulations.jsonio import JsonObject, sha256_json
from cadgpt_regulations.transcription_check import (
    _failed_pages_blocker,
    check_transcription,
)


def test_failed_pages_blocker_flags_nonzero_pages_failed() -> None:
    """Regression test for F5: 100% failed pages reported "0 blocker(s)".

    `check_transcription` counted `pages_failed` in its summary but never turned
    it into a blocker, so a manifest where every page failed transcription still
    reported `valid: true` and exit code 0.
    """
    assert _failed_pages_blocker([{"state": "ready"}, {"state": "needs_review"}]) is None

    blocker = _failed_pages_blocker(
        [{"state": "failed"}, {"state": "failed"}, {"state": "ready"}]
    )

    assert blocker is not None
    assert blocker["code"] == "PAGES_FAILED"
    assert "2 of 3" in blocker["diagnostic"]


def _failed_page_transcription() -> JsonObject:
    """A schema-valid transcription manifest whose one page fully failed."""
    configuration_values: JsonObject = {
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
    source_sha256 = "a" * 64
    page_id = f"sha256:{source_sha256}:page:000001"
    page: JsonObject = {
        "page_id": page_id,
        "pdf_page": 1,
        "state": "failed",
        "classification": None,
        "route": None,
        "reason_codes": [],
        "printed_page_label": None,
        "package_path": None,
        "package_sha256": None,
        "normalized_sha256": None,
        "normalized_chars": 0,
        "model_input_bytes": 0,
        "error": {
            "code": "PAGE_TRANSCRIPTION_FAILED",
            "diagnostic": "OCR toolchain is unavailable",
        },
    }
    document: JsonObject = {
        "catalog_key": "volume-01",
        "catalog_order": 1,
        "source_sha256": source_sha256,
        "source_bytes": 100,
        "pdf_page_count": 1,
        "artifact_path": "artifacts/volume-01.pdf",
        "pages": [page],
        "bundles": [],
    }
    return {
        "schema_version": "1.0.0",
        "catalog": {"catalog_id": "fixture"},
        "acquisition": {"receipt_sha256": "b" * 64},
        "probe": {
            "sha256": "c" * 64,
            "configuration_sha256": "d" * 64,
            "toolchain_sha256": "e" * 64,
        },
        "configuration": configuration,
        "ocr_toolchain": None,
        "documents": [document],
        "summary": {
            "documents_expected": 1,
            "documents_processed": 1,
            "pages_expected": 1,
            "pages_ready": 0,
            "pages_needs_review": 0,
            "pages_failed": 1,
            "ocr_pages": 0,
            "bundles": 0,
        },
    }


def test_check_transcription_blocks_on_a_fully_failed_manifest(tmp_path: Path) -> None:
    """End-to-end regression test for F5, through the real `check_transcription`.

    The acquisition receipt and page probe referenced by this manifest do not
    exist on disk, so those two checks fail closed on their own (as they always
    did) -- that is not what this test is about. What matters is that with the
    fix, `PAGES_FAILED` is *also* present, and was never reachable before it:
    without this fix, no code path in `check_transcription` ever added it,
    regardless of how many pages failed.
    """
    root = tmp_path / "root"
    root.mkdir(mode=0o700)
    acquisition_root = tmp_path / "acquisition"
    acquisition_root.mkdir(mode=0o700)
    manifest = _failed_page_transcription()

    check_run = check_transcription(manifest, root=root, acquisition_root=acquisition_root)

    codes = [cast(JsonObject, blocker)["code"] for blocker in check_run.report["blockers"]]
    assert "PAGES_FAILED" in codes
    assert check_run.report["valid"] is False
    assert check_run.report["summary"]["pages_failed"] == 1


def test_transcription_check_cli_exits_nonzero_on_failed_pages(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir(mode=0o700)
    acquisition_root = tmp_path / "acquisition"
    acquisition_root.mkdir(mode=0o700)
    manifest_path = tmp_path / "transcription.json"
    manifest_path.write_text(json.dumps(_failed_page_transcription()), encoding="utf-8")

    exit_code = main(
        [
            "transcription-check",
            str(manifest_path),
            "--root",
            str(root),
            "--acquisition-root",
            str(acquisition_root),
        ]
    )

    assert exit_code == 1
