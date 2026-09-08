from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

import pytest
from cadgpt_regulations.extraction_jobs import (
    ExtractionJobError,
    build_extraction_jobs,
    build_structured_extraction_jobs,
    validate_extraction_jobs,
)
from cadgpt_regulations.jsonio import sha256_json
from cadgpt_regulations.structure import build_structure


def _write_json(path: Path, value: object) -> str:
    payload = (json.dumps(value, sort_keys=True) + "\n").encode()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    path.chmod(0o600)
    return hashlib.sha256(payload).hexdigest()


def _fixture(tmp_path: Path) -> dict[str, object]:
    source_sha256 = "a" * 64
    bundle_id = f"sha256:{source_sha256}:bundle:000001-000001:test"
    bundle = {
        "bundle_id": bundle_id,
        "catalog_key": "volume-01",
        "source_sha256": source_sha256,
        "sequence": 1,
        "start_pdf_page": 1,
        "end_pdf_page": 1,
        "page_count": 1,
        "input_bytes": 7,
        "pages": [
            {
                "pdf_page": 1,
                "span_ids": [f"sha256:{source_sha256}:page:000001:native:line:000000"],
            }
        ],
        "continuation_edges": [],
    }
    bundle_path = Path("bundles") / "bundle.json"
    digest = _write_json(tmp_path / bundle_path, bundle)
    return {
        "documents": [
            {
                "catalog_key": "volume-01",
                "catalog_order": 1,
                "source_sha256": source_sha256,
                "bundles": [
                    {
                        "bundle_id": bundle_id,
                        "sequence": 1,
                        "start_pdf_page": 1,
                        "end_pdf_page": 1,
                        "page_count": 1,
                        "input_bytes": 7,
                        "path": bundle_path.as_posix(),
                        "sha256": digest,
                    }
                ],
            }
        ]
    }


def test_build_extraction_jobs_creates_two_blind_jobs_per_bundle(
    tmp_path: Path,
) -> None:
    manifest = build_extraction_jobs(_fixture(tmp_path), root=tmp_path)

    assert [job["pass"] for job in manifest["jobs"]] == ["A", "B"]
    assert manifest["summary"] == {
        "documents": 1,
        "bundles": 1,
        "jobs": 2,
        "pending": 2,
    }
    assert manifest["jobs"][0]["job_id"] != manifest["jobs"][1]["job_id"]


def test_build_extraction_jobs_rejects_tampered_bundle(tmp_path: Path) -> None:
    transcription = _fixture(tmp_path)
    (tmp_path / "bundles" / "bundle.json").write_text("{}", encoding="utf-8")

    with pytest.raises(ExtractionJobError, match=r"digest|hash|SHA|differs"):
        build_extraction_jobs(transcription, root=tmp_path)


def test_validate_extraction_jobs_rejects_missing_blind_pass(tmp_path: Path) -> None:
    manifest = build_extraction_jobs(_fixture(tmp_path), root=tmp_path)
    incomplete = copy.deepcopy(manifest)
    incomplete["jobs"] = incomplete["jobs"][:1]
    incomplete["summary"]["jobs"] = 1
    incomplete["summary"]["pending"] = 1

    with pytest.raises(ExtractionJobError, match="both blind passes"):
        validate_extraction_jobs(incomplete)


def test_validate_extraction_jobs_rejects_job_identity_drift(tmp_path: Path) -> None:
    manifest = build_extraction_jobs(_fixture(tmp_path), root=tmp_path)
    manifest["jobs"][0]["model"] = "different-model"

    with pytest.raises(ExtractionJobError, match=r"identity drift|differs"):
        validate_extraction_jobs(manifest)


def test_validate_extraction_jobs_rejects_non_pending_queue_state(tmp_path: Path) -> None:
    manifest = build_extraction_jobs(_fixture(tmp_path), root=tmp_path)
    manifest["jobs"][0]["state"] = "accepted_candidate"

    with pytest.raises(ExtractionJobError, match="invalid state"):
        validate_extraction_jobs(manifest)


def test_validate_extraction_jobs_rejects_stale_top_level_structure_hash(
    tmp_path: Path,
) -> None:
    manifest = build_extraction_jobs(_fixture(tmp_path), root=tmp_path)
    manifest["structure_sha256"] = "a" * 64

    with pytest.raises(ExtractionJobError, match="structure hash"):
        validate_extraction_jobs(manifest)


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


def _real_transcription_with_unit(root: Path) -> dict[str, object]:
    """Build a real, on-disk transcription with one page carrying a real unit mention.

    This mirrors the exact package layout `cadgpt_regulations.transcription` writes
    (a page-probe package plus a transcription evidence package), so `build_structure`
    exercises its real re-attestation path rather than a hand-mutated manifest.
    """
    source_sha256 = "a" * 64
    page_id = f"sha256:{source_sha256}:page:000001"
    span_id = f"{page_id}:native:line:000000"

    probe_relative = Path("probe") / "000001"
    native_bytes = json.dumps(
        {"lines": [{"span_id": span_id, "raw_text": "m", "bbox": [0, 0, 10, 10]}]},
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
    raw_native_bytes = b"m\n"
    normalized_bytes = b"m\n"
    digits_bytes = b"m\n"
    model_bytes = b"jpeg-bytes"
    _write_bytes(root / evidence_relative / "raw-native.txt", raw_native_bytes)
    _write_bytes(root / evidence_relative / "normalized.txt", normalized_bytes)
    _write_bytes(root / evidence_relative / "digits-ascii.txt", digits_bytes)
    _write_bytes(root / evidence_relative / "model.jpg", model_bytes)

    unit_candidate = {
        "candidate_id": f"{page_id}:unit:0000",
        "kind": "unit_mention",
        "source_kind": "native",
        "span_id": span_id,
        "raw_text": "m",
        "bbox": [0, 0, 10, 10],
        "crop_file": None,
    }
    abbreviation_candidate = {
        "candidate_id": f"{page_id}:abbreviation:0001",
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
        "semantic_evidence": {
            "symbols": [unit_candidate, abbreviation_candidate],
            "tables": [],
        },
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


def test_build_structured_extraction_jobs_binds_real_structure_units(
    tmp_path: Path,
) -> None:
    """Regression test for F1: `extract-jobs` crashed with KeyError: 'units'.

    `_bundle_structure_binding` reads `value["units"]` unconditionally, but
    `_structure_binding` never put a "units" key in that dict, so every call
    raised. This exercises the real path: a real `build_structure()` graph (not
    a hand-mutated manifest) that actually contains a unit record, fed into
    `build_structured_extraction_jobs`.
    """
    transcription_root = tmp_path / "transcription"
    transcription_root.mkdir(mode=0o700)
    transcription = _real_transcription_with_unit(transcription_root)
    structure_root = tmp_path / "structure"
    structure_root.mkdir(mode=0o700)

    structure_run = build_structure(
        transcription, transcription_root=transcription_root, output_root=structure_root
    )
    assert structure_run.manifest["summary"]["units"] == 1
    assert structure_run.manifest["summary"]["abbreviations"] == 1

    queue = build_structured_extraction_jobs(
        transcription,
        root=transcription_root,
        structure=structure_run.manifest,
        structure_root=structure_root,
    )

    assert len(queue["jobs"]) == 2
    for job in queue["jobs"]:
        assert job["structure"]["unit_ids"] != []
        assert job["structure"]["abbreviation_ids"] != []
