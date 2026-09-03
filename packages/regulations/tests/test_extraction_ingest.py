from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

import pytest
from cadgpt_regulations.extraction_ingest import (
    ExtractionIngestError,
    ingest_extraction_response,
    ingest_validator_response,
    load_ingested_receipt,
)
from cadgpt_regulations.extraction_jobs import build_extraction_jobs
from cadgpt_regulations.extraction_status import build_extraction_status
from cadgpt_regulations.storage import InstallStatus


def _write_json(path: Path, value: object) -> str:
    payload = (json.dumps(value, sort_keys=True) + "\n").encode()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    path.chmod(0o600)
    return hashlib.sha256(payload).hexdigest()


def _fixture(tmp_path: Path) -> tuple[dict[str, object], Path, Path, str]:
    transcription_root = tmp_path / "transcription"
    transcription_root.mkdir(mode=0o700)
    source_sha256 = "a" * 64
    span_id = f"sha256:{source_sha256}:page:000001:native:line:000000"
    for name, payload in (
        ("normalized.txt", b"source\n"),
        ("raw-native.txt", b"source\n"),
        ("model.jpg", b"jpeg"),
    ):
        path = transcription_root / "pages" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)
        path.chmod(0o600)
    bundle_id = f"sha256:{source_sha256}:bundle:000001-000001:test"
    bundle = {
        "bundle_id": bundle_id,
        "catalog_key": "volume-01",
        "source_sha256": source_sha256,
        "sequence": 1,
        "start_pdf_page": 1,
        "end_pdf_page": 1,
        "page_count": 1,
        "input_bytes": 11,
        "pages": [
            {
                "pdf_page": 1,
                "span_ids": [span_id],
                "normalized_text_path": "pages/normalized.txt",
                "raw_native_text_path": "pages/raw-native.txt",
                "model_render_path": "pages/model.jpg",
                "input_bytes": 11,
            }
        ],
        "continuation_edges": [],
    }
    bundle_path = Path("bundles") / "bundle.json"
    digest = _write_json(transcription_root / bundle_path, bundle)
    transcription = {
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
                        "input_bytes": 11,
                        "path": bundle_path.as_posix(),
                        "sha256": digest,
                    }
                ],
            }
        ]
    }
    jobs = build_extraction_jobs(transcription, root=transcription_root)
    job = jobs["jobs"][0]
    response = {
        "schema_version": "1.0.0",
        "input_bundle_sha256": digest,
        "pass": "A",
        "pages": [1],
        "candidates": [
            {
                "candidate_id": "candidate-1",
                "source_span_ids": [span_id],
                "qualifier_span_ids": [],
            }
        ],
    }
    response_path = tmp_path / "response.json"
    _write_json(response_path, response)
    output_root = tmp_path / "extraction"
    output_root.mkdir(mode=0o700)
    return jobs, response_path, transcription_root, job["job_id"]


def test_ingest_extraction_response_is_immutable_and_resumable(tmp_path: Path) -> None:
    jobs, response_path, transcription_root, job_id = _fixture(tmp_path)

    first = ingest_extraction_response(
        jobs,
        job_id=job_id,
        response_path=response_path,
        transcription_root=transcription_root,
        output_root=tmp_path / "extraction",
    )
    second = ingest_extraction_response(
        jobs,
        job_id=job_id,
        response_path=response_path,
        transcription_root=transcription_root,
        output_root=tmp_path / "extraction",
    )

    assert first.state == "needs_validation"
    assert first.semantic.candidates == 1
    assert first.response_status is InstallStatus.INSTALLED
    assert second.response_status is InstallStatus.REUSED
    assert second.receipt_status is InstallStatus.REUSED
    assert load_ingested_receipt(first.receipt_path)["job_id"] == job_id


def test_ingest_rejects_wrong_blind_pass(tmp_path: Path) -> None:
    jobs, response_path, transcription_root, job_id = _fixture(tmp_path)
    response = json.loads(response_path.read_text())
    response["pass"] = "B"
    _write_json(response_path, response)

    with pytest.raises(ExtractionIngestError, match="queued pass"):
        ingest_extraction_response(
            jobs,
            job_id=job_id,
            response_path=response_path,
            transcription_root=transcription_root,
            output_root=tmp_path / "extraction",
        )


def test_ingest_accepts_unambiguous_legacy_pass_label(tmp_path: Path) -> None:
    jobs, response_path, transcription_root, job_id = _fixture(tmp_path)
    response = json.loads(response_path.read_text())
    response["pass"] = "luna-volume1-semantic-extraction-pass-a"
    _write_json(response_path, response)

    result = ingest_extraction_response(
        jobs,
        job_id=job_id,
        response_path=response_path,
        transcription_root=transcription_root,
        output_root=tmp_path / "extraction",
    )

    assert result.state == "needs_validation"


def test_ingest_rejects_unknown_source_span(tmp_path: Path) -> None:
    jobs, response_path, transcription_root, job_id = _fixture(tmp_path)
    response = json.loads(response_path.read_text())
    response["candidates"][0]["source_span_ids"] = [
        "sha256:" + "b" * 64 + ":page:000001:native:line:000000"
    ]
    _write_json(response_path, response)

    with pytest.raises(ExtractionIngestError, match="unknown span IDs"):
        ingest_extraction_response(
            jobs,
            job_id=job_id,
            response_path=response_path,
            transcription_root=transcription_root,
            output_root=tmp_path / "extraction",
        )


def test_ingest_rejects_second_different_response_for_job(tmp_path: Path) -> None:
    jobs, response_path, transcription_root, job_id = _fixture(tmp_path)
    ingest_extraction_response(
        jobs,
        job_id=job_id,
        response_path=response_path,
        transcription_root=transcription_root,
        output_root=tmp_path / "extraction",
    )
    changed = copy.deepcopy(json.loads(response_path.read_text()))
    changed["candidates"][0]["candidate_id"] = "different"
    _write_json(response_path, changed)

    with pytest.raises(ExtractionIngestError, match="different response"):
        ingest_extraction_response(
            jobs,
            job_id=job_id,
            response_path=response_path,
            transcription_root=transcription_root,
            output_root=tmp_path / "extraction",
        )


def test_ingest_validator_binds_both_stored_passes(tmp_path: Path) -> None:
    jobs, response_path, transcription_root, pass_a_job_id = _fixture(tmp_path)
    output_root = tmp_path / "extraction"
    pass_a = ingest_extraction_response(
        jobs,
        job_id=pass_a_job_id,
        response_path=response_path,
        transcription_root=transcription_root,
        output_root=output_root,
    )
    pass_b_job = jobs["jobs"][1]
    response = json.loads(response_path.read_text())
    response["pass"] = "B"
    response["candidates"][0]["candidate_id"] = "candidate-b"
    _write_json(response_path, response)
    pass_b = ingest_extraction_response(
        jobs,
        job_id=pass_b_job["job_id"],
        response_path=response_path,
        transcription_root=transcription_root,
        output_root=output_root,
    )

    job = jobs["jobs"][0]
    candidate = response["candidates"][0]
    validator = {
        "schema_version": "1.0.0",
        "input_bundle_sha256": job["bundle_sha256"],
        "pages": [1],
        "provenance": {
            "bundle_id": job["bundle_id"],
            "bundle_sha256": job["bundle_sha256"],
            "pass_a_sha256": pass_a.response_sha256,
            "pass_b_sha256": pass_b.response_sha256,
        },
        "accepted_candidates": [candidate],
        "merged_candidates": [{"accepted_candidate_id": "candidate-b"}],
        "rejected_candidates": [],
        "deferred_candidates": [],
        "counts": {"accepted": 1, "merged": 1, "rejected": 0, "deferred": 0},
    }
    validator_path = tmp_path / "validator.json"
    _write_json(validator_path, validator)

    result = ingest_validator_response(
        jobs,
        bundle_id=job["bundle_id"],
        response_path=validator_path,
        transcription_root=transcription_root,
        output_root=output_root,
    )

    assert result.state == "accepted_candidate"
    assert result.accepted_candidates == 1
    assert result.deferred_candidates == 0


def test_ingest_validator_rejects_false_counts(tmp_path: Path) -> None:
    jobs, response_path, transcription_root, pass_a_job_id = _fixture(tmp_path)
    output_root = tmp_path / "extraction"
    pass_a = ingest_extraction_response(
        jobs,
        job_id=pass_a_job_id,
        response_path=response_path,
        transcription_root=transcription_root,
        output_root=output_root,
    )
    pass_b_job = jobs["jobs"][1]
    response = json.loads(response_path.read_text())
    response["pass"] = "B"
    _write_json(response_path, response)
    pass_b = ingest_extraction_response(
        jobs,
        job_id=pass_b_job["job_id"],
        response_path=response_path,
        transcription_root=transcription_root,
        output_root=output_root,
    )
    job = jobs["jobs"][0]
    validator = {
        "schema_version": "1.0.0",
        "input_bundle_sha256": job["bundle_sha256"],
        "pages": [1],
        "provenance": {
            "bundle_id": job["bundle_id"],
            "bundle_sha256": job["bundle_sha256"],
            "pass_a_sha256": pass_a.response_sha256,
            "pass_b_sha256": pass_b.response_sha256,
        },
        "accepted_candidates": [response["candidates"][0]],
        "merged_candidates": [],
        "rejected_candidates": [],
        "deferred_candidates": [],
        "counts": {"accepted": 99, "merged": 0, "rejected": 0, "deferred": 0},
    }
    validator_path = tmp_path / "validator.json"
    _write_json(validator_path, validator)

    with pytest.raises(ExtractionIngestError, match="counts are false"):
        ingest_validator_response(
            jobs,
            bundle_id=job["bundle_id"],
            response_path=validator_path,
            transcription_root=transcription_root,
            output_root=output_root,
        )


def test_extraction_status_accounts_for_pending_and_validated_bundles(
    tmp_path: Path,
) -> None:
    jobs, response_path, transcription_root, pass_a_job_id = _fixture(tmp_path)
    output_root = tmp_path / "extraction"
    pending = build_extraction_status(jobs, output_root=output_root)
    assert pending["summary"]["jobs_pending"] == 2
    assert pending["summary"]["bundles_pending"] == 1

    pass_a = ingest_extraction_response(
        jobs,
        job_id=pass_a_job_id,
        response_path=response_path,
        transcription_root=transcription_root,
        output_root=output_root,
    )
    pass_b_job = jobs["jobs"][1]
    response = json.loads(response_path.read_text())
    response["pass"] = "B"
    _write_json(response_path, response)
    pass_b = ingest_extraction_response(
        jobs,
        job_id=pass_b_job["job_id"],
        response_path=response_path,
        transcription_root=transcription_root,
        output_root=output_root,
    )
    needs_validation = build_extraction_status(jobs, output_root=output_root)
    assert needs_validation["summary"]["jobs_ingested"] == 2
    assert needs_validation["summary"]["bundles_needs_validation"] == 1

    job = jobs["jobs"][0]
    validator = {
        "schema_version": "1.0.0",
        "input_bundle_sha256": job["bundle_sha256"],
        "pages": [1],
        "provenance": {
            "bundle_id": job["bundle_id"],
            "bundle_sha256": job["bundle_sha256"],
            "pass_a_sha256": pass_a.response_sha256,
            "pass_b_sha256": pass_b.response_sha256,
        },
        "accepted_candidates": [response["candidates"][0]],
        "merged_candidates": [],
        "rejected_candidates": [],
        "deferred_candidates": [],
        "counts": {"accepted": 1, "merged": 0, "rejected": 0, "deferred": 0},
    }
    validator_path = tmp_path / "validator.json"
    _write_json(validator_path, validator)
    ingest_validator_response(
        jobs,
        bundle_id=job["bundle_id"],
        response_path=validator_path,
        transcription_root=transcription_root,
        output_root=output_root,
    )

    accepted = build_extraction_status(jobs, output_root=output_root)
    assert accepted["summary"]["bundles_accepted"] == 1
    assert accepted["bundles"][0]["validation"]["counts"]["accepted"] == 1
