from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

import pytest
from cadgpt_regulations.extraction_jobs import (
    ExtractionJobError,
    build_extraction_jobs,
    validate_extraction_jobs,
)


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

    with pytest.raises(ExtractionJobError, match="identity drift"):
        validate_extraction_jobs(manifest)
