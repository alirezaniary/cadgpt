from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from cadgpt_regulations.semantic_check import (
    SemanticCheckError,
    check_semantic_artifact,
)


def _write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, sort_keys=True), encoding="utf-8")
    path.chmod(0o600)


def _file_record(path: Path) -> dict[str, object]:
    payload = path.read_bytes()
    return {
        "path": str(path),
        "sha256": hashlib.sha256(payload).hexdigest(),
        "bytes": len(payload),
    }


def _fixture(tmp_path: Path) -> tuple[Path, Path, str]:
    page_id = "sha256:" + "a" * 64 + ":page:000001"
    span_id = page_id + ":native:line:000000"
    native = tmp_path / "native.json"
    _write_json(
        native,
        {
            "chars": [],
            "lines": [{"span_id": span_id}],
            "words": [],
        },
    )
    files: dict[str, dict[str, object]] = {"native": _file_record(native)}
    for role in ("evidence", "model", "normalized", "page"):
        path = tmp_path / role
        path.write_bytes(role.encode())
        path.chmod(0o600)
        files[role] = _file_record(path)
    job_path = tmp_path / "job.json"
    _write_json(
        job_path,
        {
            "pages": [
                {
                    "pdf_page": 1,
                    "page_id": page_id,
                    "state": "ready",
                    "files": files,
                }
            ]
        },
    )
    artifact_path = tmp_path / "artifact.json"
    _write_json(
        artifact_path,
        {
            "input_job_sha256": hashlib.sha256(job_path.read_bytes()).hexdigest(),
            "pages": [1],
            "candidates": [
                {
                    "candidate_id": "C1",
                    "source_span_ids": [span_id],
                    "qualifier_span_ids": [],
                }
            ],
        },
    )
    return job_path, artifact_path, span_id


def test_check_semantic_artifact_uses_native_lines_as_valid_spans(
    tmp_path: Path,
) -> None:
    job_path, artifact_path, _ = _fixture(tmp_path)

    result = check_semantic_artifact(job_path, artifact_path, root=tmp_path)

    assert result.candidates == 1
    assert result.unique_span_references == 1
    assert result.files_checked == 5


def test_check_semantic_artifact_rejects_unknown_span(tmp_path: Path) -> None:
    job_path, artifact_path, span_id = _fixture(tmp_path)
    artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
    artifact["candidates"][0]["source_span_ids"] = [span_id.replace("000000", "999999")]
    _write_json(artifact_path, artifact)

    with pytest.raises(SemanticCheckError, match="unknown span IDs"):
        check_semantic_artifact(job_path, artifact_path, root=tmp_path)


def test_check_semantic_artifact_rejects_tampered_job_file(tmp_path: Path) -> None:
    job_path, artifact_path, _ = _fixture(tmp_path)
    (tmp_path / "normalized").write_text("changed", encoding="utf-8")

    with pytest.raises(SemanticCheckError, match="differs from its job record"):
        check_semantic_artifact(job_path, artifact_path, root=tmp_path)


def test_check_semantic_artifact_rejects_wrong_input_hash(tmp_path: Path) -> None:
    job_path, artifact_path, _ = _fixture(tmp_path)
    artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
    artifact["input_job_sha256"] = "0" * 64
    _write_json(artifact_path, artifact)

    with pytest.raises(SemanticCheckError, match="input hash"):
        check_semantic_artifact(job_path, artifact_path, root=tmp_path)


def test_check_semantic_artifact_accepts_transcription_bundle(tmp_path: Path) -> None:
    page_id = "sha256:" + "b" * 64 + ":page:000001"
    span_id = page_id + ":native:line:000000"
    inputs: dict[str, Path] = {}
    for name, payload in {
        "normalized.txt": b"normalized",
        "raw-native.txt": b"raw source",
        "model.jpg": b"image",
    }.items():
        path = tmp_path / name
        path.write_bytes(payload)
        path.chmod(0o600)
        inputs[name] = path
    model_input_bytes = (
        inputs["normalized.txt"].stat().st_size + inputs["model.jpg"].stat().st_size
    )
    job_path = tmp_path / "bundle.json"
    _write_json(
        job_path,
        {
            "input_bytes": model_input_bytes,
            "pages": [
                {
                    "pdf_page": 1,
                    "page_id": page_id,
                    "state": "ready",
                    "span_ids": [span_id],
                    "normalized_text_path": "normalized.txt",
                    "raw_native_text_path": "raw-native.txt",
                    "model_render_path": "model.jpg",
                    "input_bytes": model_input_bytes,
                }
            ],
        },
    )
    artifact_path = tmp_path / "artifact.json"
    _write_json(
        artifact_path,
        {
            "input_bundle_sha256": hashlib.sha256(job_path.read_bytes()).hexdigest(),
            "pages": [{"pdf_page": 1}],
            "candidates": [
                {
                    "candidate_id": "C1",
                    "source_span_ids": [span_id],
                    "qualifier_span_ids": [],
                }
            ],
        },
    )

    result = check_semantic_artifact(job_path, artifact_path, root=tmp_path)

    assert result.allowed_span_ids == 1
    assert result.files_checked == 3
