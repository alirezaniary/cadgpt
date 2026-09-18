from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from cadgpt_regulations.jsonio import JsonObject, sha256_json
from cadgpt_regulations.luna_transcript import (
    LUNA_MODEL,
    PROMPT_SHA256,
    TRANSCRIPT_PASSES,
    TRANSCRIPT_SCHEMA_SHA256,
    LunaTranscriptError,
    build_luna_chunk_ledger,
    build_luna_transcript_jobs,
    claim_luna_chunks,
    complete_luna_chunk,
    fail_luna_chunk,
    get_next,
    mark_finished,
    mark_started,
    requeue_luna_chunk,
    validate_luna_job,
)
from cadgpt_regulations.paddle_ocr import _parse_result
from cadgpt_regulations.storage import StorageError, install_immutable_bytes
from cadgpt_regulations.transcript_assembly import (
    audit_luna_transcripts,
    install_assembled_transcripts,
)


def test_job_keeps_blank_pages_and_resolves_renders_under_root(tmp_path: Path) -> None:
    acquisition = tmp_path / "acquisition"
    root = tmp_path / "transcription"
    acquisition.mkdir(mode=0o700)
    root.mkdir(mode=0o700)
    pdf = b"source PDF fixture"
    (acquisition / "source.pdf").write_bytes(pdf)
    (acquisition / "source.pdf").chmod(0o600)
    source_hash = hashlib.sha256(pdf).hexdigest()
    pages = []
    for number, text in ((1, ""), (2, "text")):
        package = root / f"page-{number}"
        package.mkdir(mode=0o700)
        (package / "native.json").write_text("{}")
        artifacts = []
        for name, role in (
            ("raw.txt", "raw_native_text"),
            ("text.txt", "normalized_search_text"),
        ):
            (package / name).write_text(text)
            artifacts.append(
                {
                    "role": role,
                    "path": f"page-{number}/{name}",
                    "sha256": hashlib.sha256(text.encode()).hexdigest(),
                }
            )
        if number == 2:
            (package / "render.png").write_bytes(b"render fixture")
        evidence = {
            "artifacts": artifacts,
            "probe": {
                "package_path": f"page-{number}",
                "classification": "blank" if number == 1 else "native_text",
                "route": "none" if number == 1 else "native",
            },
        }
        (package / "evidence.json").write_text(json.dumps(evidence))
        pages.append(
            {
                "normalized_text_path": f"page-{number}/text.txt",
                "input_bytes": len(text),
                "page_id": f"sha256:{source_hash}:page:{number:06d}",
                "pdf_page": number,
                "state": "ready",
            }
        )
    bundle = json.dumps({"pages": pages}).encode()
    (root / "bundle.json").write_bytes(bundle)
    transcription = {
        "documents": [
            {
                "source_sha256": source_hash,
                "source_bytes": len(pdf),
                "artifact_path": "source.pdf",
                "catalog_key": "volume-01",
                "catalog_order": 1,
                "bundles": [
                    {
                        "path": "bundle.json",
                        "sha256": hashlib.sha256(bundle).hexdigest(),
                        "bundle_id": "bundle-1",
                        "start_pdf_page": 1,
                        "end_pdf_page": 2,
                    }
                ],
            }
        ]
    }
    for path in root.rglob("*"):
        if path.is_file():
            path.chmod(0o600)
    queue = build_luna_transcript_jobs(
        transcription, transcription_root=root, acquisition_root=acquisition
    )
    job = queue["jobs"][0]
    assert [page["pdf_page"] for page in job["pages"]] == [1, 2]
    assert job["pages"][0]["page_render_path"] is None
    assert job["pages"][1]["page_render_path"] == "page-2/render.png"
    assert (
        job["pages"][1]["page_render_sha256"]
        == hashlib.sha256(b"render fixture").hexdigest()
    )
    assert job["overlap_page_ids"] == []


def test_job_rejects_duplicate_page_records() -> None:
    job = _job()
    job["pages"] = job["pages"] * 2
    with pytest.raises(LunaTranscriptError, match="missing or reordered pages"):
        validate_luna_job(job)


def test_paddle_result_groups_rows_and_orders_persian_tokens_rtl() -> None:
    result = _parse_result(
        {
            "rec_texts": ["اول", "دوم", "سطر دوم"],
            "rec_scores": [0.95, 0.9, 0.8],
            "rec_boxes": [[200, 10, 260, 30], [100, 11, 160, 31], [120, 60, 250, 85]],
        },
        page_id=f"sha256:{'a' * 64}:page:000001",
    )

    assert result.raw_text == "اول دوم\nسطر دوم"
    assert [token["raw_text"] for token in result.tokens] == ["اول", "دوم", "سطر دوم"]
    assert result.lines[0]["confidence_permyriad"] == 9250


def _job() -> JsonObject:
    page_id = f"sha256:{'a' * 64}:page:000001"
    job: JsonObject = {
        "state": "pending",
        "model": LUNA_MODEL,
        "passes": list(TRANSCRIPT_PASSES),
        "prompt_version": "persian-structured-transcript-1.0.0",
        "prompt_sha256": PROMPT_SHA256,
        "response_schema_sha256": TRANSCRIPT_SCHEMA_SHA256,
        "catalog_key": "volume-01",
        "catalog_order": 1,
        "source_sha256": "a" * 64,
        "source_bytes": 100,
        "original_pdf": {"path": "artifacts/source.pdf", "sha256": "a" * 64, "bytes": 100},
        "bundle_id": "bundle-1",
        "bundle_path": "bundles/one.json",
        "bundle_sha256": "b" * 64,
        "start_pdf_page": 1,
        "end_pdf_page": 1,
        "pages": [
            {
                "page_id": page_id,
                "pdf_page": 1,
                "state": "ready",
                "classification": "native_text",
                "route": "native",
                "evidence_path": "transcriptions/one/evidence.json",
                "evidence_sha256": "c" * 64,
                "native_layout_path": "pages/one/native.json",
                "native_layout_sha256": "d" * 64,
                "native_text_path": "transcriptions/one/raw-native.txt",
                "native_text_sha256": "e" * 64,
                "paddle_result_path": None,
                "paddle_result_sha256": None,
                "page_render_path": "pages/one/render.png",
                "page_render_sha256": "f" * 64,
                "normalized_text_path": "transcriptions/one/normalized.txt",
                "normalized_text_sha256": "0" * 64,
            }
        ],
    }
    identity: JsonObject = {
        "source_sha256": job["source_sha256"],
        "bundle_id": job["bundle_id"],
        "bundle_sha256": job["bundle_sha256"],
        "start_pdf_page": 1,
        "end_pdf_page": 1,
        "model": LUNA_MODEL,
        "passes": list(TRANSCRIPT_PASSES),
        "prompt_sha256": PROMPT_SHA256,
        "response_schema_sha256": TRANSCRIPT_SCHEMA_SHA256,
    }
    job["job_id"] = f"sha256:{sha256_json(identity)}"
    validate_luna_job(job)
    return job


def _structured(job: JsonObject) -> JsonObject:
    return {
        "schema_version": "1.0.0",
        "source": {
            "catalog_key": job["catalog_key"],
            "source_sha256": job["source_sha256"],
            "bundle_id": job["bundle_id"],
            "start_pdf_page": 1,
            "end_pdf_page": 1,
        },
        "transcript_fa": "متن فارسی",
        "title_fa": "عنوان",
        "sections": [],
        "clauses": [],
        "definitions": [],
        "requirements": [],
        "prohibitions": [],
        "permissions": [],
        "procedures": [],
        "tables": [],
        "formulas": [],
        "references": [],
        "uncertainties": [],
    }


def _response(job: JsonObject, pass_name: str) -> JsonObject:
    value: JsonObject = {
        "schema_version": "1.0.0",
        "job_id": job["job_id"],
        "pass": pass_name,
        "model": job["model"],
        "source_sha256": job["source_sha256"],
        "prompt_sha256": job["prompt_sha256"],
        "response_schema_sha256": job["response_schema_sha256"],
        "transcript_fa": "متن فارسی",
    }
    if pass_name == "structured_transcript":
        value["structured_transcript"] = _structured(job)
    return value


def _assembly_fixture(tmp_path: Path) -> tuple[JsonObject, JsonObject, JsonObject, Path]:
    acquisition_root = tmp_path / "source"
    acquisition_root.mkdir(mode=0o700)
    payload = b"immutable source fixture"
    install_immutable_bytes(acquisition_root / "source.pdf", payload)
    job = _job()
    job.update(
        {
            "chunk_order": 1,
            "overlap_page_ids": [],
            "source_bytes": len(payload),
            "source_sha256": hashlib.sha256(payload).hexdigest(),
        }
    )
    job["original_pdf"] = {
        "path": "source.pdf",
        "sha256": job["source_sha256"],
        "bytes": len(payload),
    }
    job["pages"][0]["page_id"] = f"sha256:{job['source_sha256']}:page:000001"
    identity = {
        key: job[key]
        for key in (
            "source_sha256",
            "bundle_id",
            "bundle_sha256",
            "start_pdf_page",
            "end_pdf_page",
            "model",
            "passes",
            "prompt_sha256",
            "response_schema_sha256",
        )
    }
    job["job_id"] = f"sha256:{sha256_json(identity)}"
    queue = {
        "schema_version": "1.0.0",
        "model": LUNA_MODEL,
        "passes": list(TRANSCRIPT_PASSES),
        "prompt_version": job["prompt_version"],
        "prompt_sha256": PROMPT_SHA256,
        "response_schema_sha256": TRANSCRIPT_SCHEMA_SHA256,
        "transcription_sha256": "1" * 64,
        "jobs": [job],
        "summary": {"jobs": 1, "pending": 1, "completed": 0},
    }
    acquisition = {
        "artifacts": [
            {
                "state": "ready",
                "catalog_key": job["catalog_key"],
                "catalog_order": 1,
                "sha256": job["source_sha256"],
                "bytes": len(payload),
                "artifact_path": "source.pdf",
                "pdf_page_count": 1,
            }
        ]
    }
    response = _response(job, "structured_transcript")
    page_id = job["pages"][0]["page_id"]
    response.update(
        {
            "chunk_order": 1,
            "catalog_order": 1,
            "overlap_page_ids": [],
            "ordered_page_ids": [page_id],
            "page_transcripts": [
                {"page_id": page_id, "pdf_page": 1, "text_fa": response["transcript_fa"]}
            ],
        }
    )
    section = {
        "record_id": "page-1",
        "kind": "page_transcript",
        "text_fa": response["transcript_fa"],
        "source_page_ids": [page_id],
        "source_span_ids": [],
        "conditions_fa": [],
        "exceptions_fa": [],
        "references_fa": [],
    }
    section.update(
        dict.fromkeys(("subject_fa", "predicate_fa", "modality", "value_fa", "uncertainty"))
    )
    response["structured_transcript"]["sections"] = [section]
    return queue, acquisition, response, acquisition_root


def _complete_fixture(queue: JsonObject, response: JsonObject, root: Path) -> JsonObject:
    claims = claim_luna_chunks(
        build_luna_chunk_ledger(queue), worker_id="luna-1", max_workers=1, queue=queue
    )
    claim = claims.claims[0]
    return complete_luna_chunk(
        claims.ledger,
        queue,
        job_id=claim.job_id,
        worker_id=claim.worker_id,
        lease_token=claim.lease_token,
        response=response,
        output_root=root,
    ).ledger


def test_assembly_is_idempotent_and_attests_source_and_both_results(tmp_path: Path) -> None:
    queue, acquisition, response, source_root = _assembly_fixture(tmp_path)
    ledger = _complete_fixture(queue, response, tmp_path)
    report, books = audit_luna_transcripts(
        queue, ledger, acquisition, output_root=tmp_path, acquisition_root=source_root
    )
    assert report["complete"]
    assert report["summary"]["pages_completed"] == 1
    path = install_assembled_transcripts(report, books, output_root=tmp_path)
    modified = path.stat().st_mtime_ns
    assert install_assembled_transcripts(report, books, output_root=tmp_path) == path
    assert path.stat().st_mtime_ns == modified
    result_path = tmp_path / ledger["jobs"][0]["structured_transcript_path"]
    result_path.write_bytes(b"corrupt")
    with pytest.raises(StorageError):
        audit_luna_transcripts(
            queue, ledger, acquisition, output_root=tmp_path, acquisition_root=source_root
        )


def test_assembly_refuses_pending_chunks_and_missing_tail_pages(tmp_path: Path) -> None:
    queue, acquisition, _, source_root = _assembly_fixture(tmp_path)
    ledger = build_luna_chunk_ledger(queue)
    report, books = audit_luna_transcripts(
        queue, ledger, acquisition, output_root=tmp_path, acquisition_root=source_root
    )
    assert not report["complete"]
    with pytest.raises(LunaTranscriptError, match="incomplete"):
        install_assembled_transcripts(report, books, output_root=tmp_path)
    assert not (tmp_path / "assembled").exists()
    acquisition["artifacts"][0]["pdf_page_count"] = 2
    with pytest.raises(LunaTranscriptError, match="missing or duplicated pages"):
        audit_luna_transcripts(
            queue, ledger, acquisition, output_root=tmp_path, acquisition_root=source_root
        )


@pytest.mark.parametrize(
    "mutation", ["missing_page", "wrong_page", "wrong_range", "wrong_section"]
)
def test_assembly_rejects_schema_valid_but_inconsistent_results(
    tmp_path: Path, mutation: str
) -> None:
    queue, _, response, _ = _assembly_fixture(tmp_path)
    if mutation == "missing_page":
        response["page_transcripts"] = []
    elif mutation == "wrong_page":
        response["page_transcripts"][0]["pdf_page"] = 2
    elif mutation == "wrong_range":
        response["structured_transcript"]["source"]["end_pdf_page"] = 2
    else:
        response["structured_transcript"]["sections"][0]["text_fa"] = "other"
    with pytest.raises(LunaTranscriptError):
        _complete_fixture(queue, response, tmp_path)


def test_parallel_chunk_ledger_claims_in_order_and_completes_idempotently(
    tmp_path: Path,
) -> None:
    job = _job()
    job["chunk_order"] = 1
    queue: JsonObject = {
        "schema_version": "1.0.0",
        "model": LUNA_MODEL,
        "passes": list(TRANSCRIPT_PASSES),
        "prompt_version": job["prompt_version"],
        "prompt_sha256": PROMPT_SHA256,
        "response_schema_sha256": TRANSCRIPT_SCHEMA_SHA256,
        "transcription_sha256": "1" * 64,
        "jobs": [job],
        "summary": {"jobs": 1, "pending": 1, "completed": 0},
    }
    ledger = build_luna_chunk_ledger(queue)
    claimed = claim_luna_chunks(ledger, worker_id="luna-1", max_workers=3, queue=queue)
    assert len(claimed.claims) == 1
    claim = claimed.claims[0]
    assert claim.chunk_order == 1
    response = _response(job, "structured_transcript")
    completed = complete_luna_chunk(
        claimed.ledger,
        queue,
        job_id=job["job_id"],
        worker_id="luna-1",
        lease_token=claim.lease_token,
        response=response,
        output_root=tmp_path,
    )
    assert completed.ledger["summary"]["completed"] == 1
    repeated = complete_luna_chunk(
        completed.ledger,
        queue,
        job_id=job["job_id"],
        worker_id="luna-1",
        lease_token=claim.lease_token,
        response=response,
        output_root=tmp_path,
    )
    assert repeated.ledger == completed.ledger


def test_parallel_chunk_ledger_failure_can_be_requeued(tmp_path: Path) -> None:
    job = _job()
    job["chunk_order"] = 1
    queue: JsonObject = {
        "schema_version": "1.0.0",
        "model": LUNA_MODEL,
        "passes": list(TRANSCRIPT_PASSES),
        "prompt_version": job["prompt_version"],
        "prompt_sha256": PROMPT_SHA256,
        "response_schema_sha256": TRANSCRIPT_SCHEMA_SHA256,
        "transcription_sha256": "1" * 64,
        "jobs": [job],
        "summary": {"jobs": 1, "pending": 1, "completed": 0},
    }
    ledger = build_luna_chunk_ledger(queue)
    claim = claim_luna_chunks(
        ledger, worker_id="luna-1", max_workers=1, queue=queue
    ).claims[0]
    failed = fail_luna_chunk(
        claim_luna_chunks(ledger, worker_id="luna-1", max_workers=1, queue=queue).ledger,
        job_id=job["job_id"],
        worker_id="luna-1",
        lease_token=claim.lease_token,
        error="timeout",
        queue=queue,
    )
    retried = requeue_luna_chunk(failed, job_id=job["job_id"], queue=queue)
    assert retried["jobs"][0]["status"] == "pending"


def test_coordinator_wrappers_keep_json_persistence_inside_module(tmp_path: Path) -> None:
    job = _job()
    job["chunk_order"] = 1
    queue: JsonObject = {
        "schema_version": "1.0.0",
        "model": LUNA_MODEL,
        "passes": list(TRANSCRIPT_PASSES),
        "prompt_version": job["prompt_version"],
        "prompt_sha256": PROMPT_SHA256,
        "response_schema_sha256": TRANSCRIPT_SCHEMA_SHA256,
        "transcription_sha256": "1" * 64,
        "jobs": [job],
        "summary": {"jobs": 1, "pending": 1, "completed": 0},
    }
    # Read-only selection does not create or alter a ledger file.
    assert get_next(queue, output_root=tmp_path)[0]["status"] == "pending"
    assert not (tmp_path / "ledger.json").exists()
    started = mark_started(queue, output_root=tmp_path, worker_id="luna-1")
    claim = started.claims[0]
    finished = mark_finished(
        queue,
        output_root=tmp_path,
        job_id=job["job_id"],
        worker_id=claim.worker_id,
        lease_token=claim.lease_token,
        response=_response(job, "structured_transcript"),
    )
    assert mark_started(queue, output_root=tmp_path, worker_id="luna-2").claims == ()
    repeated = mark_finished(
        queue,
        output_root=tmp_path,
        job_id=job["job_id"],
        worker_id=claim.worker_id,
        lease_token=claim.lease_token,
        response=_response(job, "structured_transcript"),
    )
    assert repeated.ledger == finished.ledger
    assert json.loads((tmp_path / "ledger.json").read_text())["summary"]["completed"] == 1
