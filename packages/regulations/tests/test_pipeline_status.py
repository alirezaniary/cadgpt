from __future__ import annotations

import importlib.util
import json
from argparse import Namespace
from pathlib import Path
from typing import Any


def _module() -> Any:
    path = Path(__file__).parents[3] / "tools" / "inbr_pipeline_status.py"
    spec = importlib.util.spec_from_file_location("inbr_pipeline_status", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_status_blocks_unsafe_acquisition_path(tmp_path: Path) -> None:
    module = _module()
    receipt = tmp_path / "acquisition.json"
    receipt.write_text(
        json.dumps(
            {
                "summary": {
                    "artifacts_ready": 1,
                    "artifacts_expected": 1,
                    "artifacts_quarantined": 0,
                },
                "artifacts": [
                    {"artifact_path": "../outside.pdf", "sha256": "a" * 64, "bytes": 1}
                ],
            }
        ),
        encoding="utf-8",
    )

    status = module._check_acquisition(receipt)

    assert status["state"] == "blocked"
    assert any("unsafe relative path" in error for error in status["errors"])


def test_next_action_requires_three_parallel_workers() -> None:
    module = _module()
    stages = {
        "acquisition": {"state": "ready"},
        "page_probe": {"state": "ready"},
        "transcription": {"state": "ready"},
        "queue": {"state": "ready"},
        "chunk_ledger": {
            "state": "ready",
            "summary": {"jobs": 4, "pending": 4, "leased": 0, "completed": 0, "failed": 0},
        },
    }

    action, safe = module._next_action(stages, [])

    assert safe is False
    assert "exactly three parallel Luna workers" in action
    assert "one chunk per worker" in action


def test_probe_guard_rejects_render_for_native_page(tmp_path: Path) -> None:
    module = _module()
    package = tmp_path / "pages" / "source" / "000001"
    package.mkdir(parents=True)
    (package / "render.png").write_bytes(b"legacy-render")
    manifest = {
        "acquisition": {"receipt_sha256": "a" * 64},
        "configuration": {"native_first": True},
        "documents": [
            {
                "pages": [
                    {
                        "page_id": "page-1",
                        "package_path": "pages/source/000001",
                        "route": "native",
                    }
                ]
            }
        ],
    }

    errors = module._native_first_violations(tmp_path, manifest)

    assert errors == ["native-first violation: native page page-1 has render.png"]


def test_queue_allows_native_without_render_but_requires_ocr_render(tmp_path: Path) -> None:
    module = _module()
    page = {"route": "native", "page_render_path": None}
    for field in ("evidence_path", "native_layout_path", "normalized_text_path"):
        page[field] = field
        (tmp_path / field).write_text("evidence")
    queue = {"jobs": [{"job_id": "job-1", "pages": [page]}]}
    (tmp_path / "jobs.json").write_text(json.dumps(queue))
    assert module._check_queue(tmp_path, tmp_path)["state"] == "ready"
    page["route"] = "ocr"
    (tmp_path / "jobs.json").write_text(json.dumps(queue))
    assert module._check_queue(tmp_path, tmp_path)["state"] == "blocked"


def test_next_action_does_not_confuse_probe_path_with_probe_process() -> None:
    module = _module()
    action, _ = module._next_action(
        {},
        [
            {
                "state": "running",
                "command": (
                    "cadgpt-regulations transcribe --probe /manifests/page-probe/hash.json"
                ),
            }
        ],
    )
    assert "running transcription process" in action


def test_inspect_reports_persian_boundary_without_writing(tmp_path: Path) -> None:
    module = _module()
    args = Namespace(
        repo_root=tmp_path,
        state=None,
        acquisition_receipt=None,
        transcription_root=None,
        extraction_root=None,
        as_json=True,
    )

    result = module.inspect(args)

    assert result["boundary"] == "persian_structured_transcript"
    assert result["forbidden_downstream"] == ["english_rules", "ids", "publication"]
    assert not list(tmp_path.iterdir())
