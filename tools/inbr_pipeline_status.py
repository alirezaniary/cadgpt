#!/usr/bin/env python3
"""Read-only status and handoff inspector for the INBR transcript pipeline.

The inspector intentionally lives outside the generated corpus tree.  It never starts,
stops, leases, or rewrites a process or artifact; it only re-attests the receipts that
already exist and reports the next safe operation.
"""

# This file is itself a terminal-facing CLI; its output is deliberate.
# ruff: noqa: T201

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
from contextlib import suppress
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

Json = dict[str, Any]
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


def _sha256(path: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
            size += len(chunk)
    return digest.hexdigest(), size


def _load(path: Path) -> Json:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} is not a JSON object")
    return value


def _record(state: str, *, errors: list[str] | None = None, **values: Any) -> Json:
    return {"state": state, "errors": errors or [], **values}


def _safe_relative(value: Any) -> bool:
    if not isinstance(value, str) or not value or value.startswith("/") or "\\" in value:
        return False
    parts = value.split("/")
    return all(part not in {"", ".", ".."} for part in parts)


def _relative_file(root: Path, value: Any) -> tuple[Path | None, str | None]:
    if not _safe_relative(value):
        return None, f"unsafe relative path: {value!r}"
    path = root.joinpath(*str(value).split("/"))
    try:
        path.relative_to(root)
    except ValueError:
        return None, f"path escapes root: {value!r}"
    return path, None


def _pid_status(path: Path) -> Json:
    try:
        pid = int(path.read_text(encoding="ascii").strip())
    except (OSError, ValueError) as exc:
        return {"path": str(path), "state": "invalid", "error": str(exc)}
    if pid <= 0:
        return {
            "path": str(path),
            "pid": pid,
            "state": "invalid",
            "error": "PID must be positive",
        }
    alive = True
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        alive = False
    except PermissionError:
        alive = True
    command = ""
    cmdline = Path(f"/proc/{pid}/cmdline")
    with suppress(OSError):
        command = cmdline.read_bytes().replace(b"\0", b" ").decode(errors="replace").strip()
    return {
        "path": str(path),
        "pid": pid,
        "state": "running" if alive else "exited",
        "command": command,
    }


def _processes(root: Path) -> list[Json]:
    results: list[Json] = []
    seen: set[int] = set()
    for path in sorted(root.rglob("*.pid")) if root.is_dir() else []:
        status = _pid_status(path)
        results.append(status)
        pid = status.get("pid")
        if isinstance(pid, int):
            seen.add(pid)
    markers = (str(root), root.name)
    proc_root = Path("/proc")
    for proc in (
        sorted(proc_root.iterdir(), key=lambda item: item.name)
        if proc_root.is_dir()
        else []
    ):
        if not proc.name.isdigit() or int(proc.name) in seen:
            continue
        try:
            command = (
                proc.joinpath("cmdline")
                .read_bytes()
                .replace(b"\0", b" ")
                .decode(errors="replace")
                .strip()
            )
        except OSError:
            continue
        if not any(marker in command for marker in markers):
            continue
        results.append({"pid": int(proc.name), "state": "running", "command": command})
    return results


def _check_acquisition(path: Path) -> Json:
    errors: list[str] = []
    if not path.is_file() or path.is_symlink():
        return _record(
            "missing", errors=[f"missing acquisition receipt: {path}"], receipt=str(path)
        )
    try:
        receipt = _load(path)
    except (OSError, ValueError) as exc:
        return _record("invalid", errors=[str(exc)], receipt=str(path))
    try:
        raw_hash, raw_bytes = _sha256(path)
        if path.name == "acquisition.json" and not _SHA256.match(raw_hash):
            errors.append("acquisition receipt hash is not a SHA-256 digest")
    except OSError as exc:
        errors.append(f"cannot hash acquisition receipt: {exc}")
        raw_hash, raw_bytes = None, None
    summary = receipt.get("summary")
    if not isinstance(summary, dict):
        errors.append("receipt lacks summary")
        summary = {}
    if summary.get("artifacts_ready") != summary.get("artifacts_expected"):
        errors.append("not every acquisition artifact is ready")
    if summary.get("artifacts_quarantined", 0):
        errors.append("acquisition has quarantined artifacts")
    artifacts = receipt.get("artifacts")
    checked = 0
    if not isinstance(artifacts, list):
        errors.append("receipt lacks artifacts list")
        artifacts = []
    for item in artifacts:
        if not isinstance(item, dict):
            errors.append("acquisition artifact record is not an object")
            continue
        artifact_path, path_error = _relative_file(path.parent, item.get("artifact_path"))
        if path_error:
            errors.append(path_error)
            continue
        assert artifact_path is not None
        if not artifact_path.is_file() or artifact_path.is_symlink():
            errors.append(f"missing or symlinked artifact: {artifact_path}")
            continue
        expected_hash = item.get("sha256") or item.get("expected_sha256")
        expected_bytes = item.get("bytes") or item.get("expected_bytes")
        if not isinstance(expected_hash, str) or not _SHA256.match(expected_hash):
            errors.append(f"invalid artifact hash: {artifact_path}")
            continue
        try:
            actual_hash, actual_bytes = _sha256(artifact_path)
        except OSError as exc:
            errors.append(f"cannot hash artifact {artifact_path}: {exc}")
            continue
        checked += 1
        if actual_hash != expected_hash or (
            isinstance(expected_bytes, int) and actual_bytes != expected_bytes
        ):
            errors.append(f"artifact attestation mismatch: {artifact_path}")
    return _record(
        "ready" if not errors else "blocked",
        errors=errors,
        receipt=str(path),
        receipt_sha256=raw_hash,
        receipt_bytes=raw_bytes,
        artifacts_checked=checked,
        summary=summary,
    )


def _manifest_candidates(root: Path, kind: str) -> list[tuple[Path, Json, str | None]]:
    results: list[tuple[Path, Json, str | None]] = []
    directory = root / "manifests" / kind
    for path in sorted(directory.glob("*.json")) if directory.is_dir() else []:
        try:
            value = _load(path)
            actual, _ = _sha256(path)
        except (OSError, ValueError) as exc:
            results.append((path, {}, str(exc)))
            continue
        if path.stem != actual:
            results.append((path, value, "manifest filename does not match its SHA-256"))
        else:
            results.append((path, value, None))
    return results


def _check_probe(
    root: Path, acquisition_sha256: str | None, expected_pages: int | None
) -> Json:
    candidates = _manifest_candidates(root, "page-probe")
    valid: list[tuple[Path, Json]] = []
    errors: list[str] = []
    for path, value, error in candidates:
        if error:
            errors.append(f"{path}: {error}")
            continue
        identity = value.get("acquisition")
        summary = value.get("summary")
        toolchain = value.get("toolchain")
        if (
            not isinstance(identity, dict)
            or identity.get("receipt_sha256") != acquisition_sha256
        ):
            continue
        if not isinstance(summary, dict) or not isinstance(toolchain, dict):
            errors.append(f"{path}: missing summary or toolchain")
            continue
        if expected_pages is not None and summary.get("pages_expected") != expected_pages:
            continue
        if summary.get("pages_failed") != 0:
            errors.append(f"{path}: page-probe has failed pages")
            continue
        if (
            toolchain.get("paddle_cuda") is not True
            or toolchain.get("paddle_device") != "gpu:0"
        ):
            errors.append(f"{path}: probe is not CUDA Paddle GPU evidence")
            continue
        native_first_errors = _native_first_violations(root, value)
        if native_first_errors:
            errors.extend(f"{path}: {error}" for error in native_first_errors)
            continue
        valid.append((path, value))
    if not valid:
        state = (
            "running"
            if any(item["state"] == "running" for item in _processes(root))
            else "missing"
        )
        if any("native-first" in error for error in errors):
            state = "blocked"
        return _record(
            state,
            errors=errors or ["no complete CUDA Paddle page-probe manifest"],
            candidates=len(candidates),
        )
    path, value = max(valid, key=lambda item: item[0].stat().st_mtime_ns)
    return _record(
        "ready",
        errors=errors,
        manifest=str(path),
        manifest_sha256=path.stem,
        summary=value.get("summary"),
        toolchain=value.get("toolchain"),
    )


def _native_first_violations(root: Path, manifest: Json) -> list[str]:
    """Reject legacy probes that rendered pages whose route is native-only."""
    violations: list[str] = []
    configuration = manifest.get("configuration")
    if isinstance(configuration, dict):
        if configuration.get("native_first") is False:
            violations.append("manifest explicitly disables native-first routing")
        policy = configuration.get("render_policy")
        if policy in {"all", "all_pages", "render_all_pages"}:
            violations.append(f"manifest render policy is {policy!r}, not native-first")
    documents = manifest.get("documents")
    if not isinstance(documents, list):
        return violations
    for document in documents:
        if not isinstance(document, dict) or not isinstance(document.get("pages"), list):
            continue
        for page in document["pages"]:
            if not isinstance(page, dict) or page.get("route") != "native":
                continue
            package_path, path_error = _relative_file(root, page.get("package_path"))
            if path_error:
                violations.append(f"native page has {path_error}")
                continue
            assert package_path is not None
            for filename in ("render.png", "page_render.png"):
                render = package_path / filename
                if render.is_file() and not render.is_symlink():
                    violations.append(
                        "native-first violation: native page "
                        f"{page.get('page_id', page.get('pdf_page'))} has {filename}"
                    )
    if len(violations) > 10:
        return [
            *violations[:10],
            "native-first violation: "
            f"{len(violations) - 10} more native pages have render evidence",
        ]
    return violations


def _check_transcription(
    root: Path, probe: Json | None, expected_pages: int | None
) -> Json:
    candidates = _manifest_candidates(root, "transcription")
    probe_sha = probe.get("manifest_sha256") if isinstance(probe, dict) else None
    valid: list[tuple[Path, Json]] = []
    errors: list[str] = []
    for path, value, error in candidates:
        if error:
            errors.append(f"{path}: {error}")
            continue
        identity = value.get("probe")
        summary = value.get("summary")
        if (
            not isinstance(identity, dict)
            or probe_sha is None
            or identity.get("sha256") != probe_sha
        ):
            continue
        if not isinstance(summary, dict):
            errors.append(f"{path}: missing summary")
            continue
        if expected_pages is not None and summary.get("pages_expected") != expected_pages:
            continue
        if summary.get("pages_failed") != 0:
            errors.append(f"{path}: transcription has failed pages")
            continue
        valid.append((path, value))
    if not valid:
        return _record(
            "missing",
            errors=errors or ["no transcription manifest matching selected page-probe"],
            candidates=len(candidates),
        )
    path, value = max(valid, key=lambda item: item[0].stat().st_mtime_ns)
    return _record(
        "ready",
        errors=errors,
        manifest=str(path),
        manifest_sha256=path.stem,
        summary=value.get("summary"),
    )


def _check_queue(root: Path, transcription_root: Path) -> Json:
    path = root / "jobs.json"
    if not path.is_file() or path.is_symlink():
        return _record("missing", errors=[f"missing Luna queue: {path}"], queue=str(path))
    errors: list[str] = []
    try:
        queue = _load(path)
    except (OSError, ValueError) as exc:
        return _record("invalid", errors=[str(exc)], queue=str(path))
    jobs = queue.get("jobs")
    if not isinstance(jobs, list) or not jobs:
        errors.append("queue has no jobs")
        jobs = []
    checked = 0
    for job in jobs:
        if not isinstance(job, dict):
            errors.append("queue job is not an object")
            continue
        pages = job.get("pages")
        if not isinstance(pages, list) or not pages:
            errors.append(f"job {job.get('job_id')!r} has no pages")
            continue
        for page in pages:
            if not isinstance(page, dict):
                errors.append("queue page is not an object")
                continue
            for field in (
                "evidence_path",
                "native_layout_path",
                "page_render_path",
                "normalized_text_path",
            ):
                # Native-only and blank pages intentionally have no render.
                if (
                    field == "page_render_path"
                    and page.get(field) is None
                    and page.get("route") in {"native", "none"}
                ):
                    continue
                candidate, path_error = _relative_file(transcription_root, page.get(field))
                if path_error:
                    errors.append(f"{job.get('job_id')}: {field}: {path_error}")
                elif candidate is not None and (
                    not candidate.is_file() or candidate.is_symlink()
                ):
                    errors.append(f"{job.get('job_id')}: missing {field}: {candidate}")
        checked += 1
    return _record(
        "ready" if not errors else "blocked",
        errors=errors,
        queue=str(path),
        jobs=len(jobs),
        jobs_checked=checked,
    )


def _ledger_candidates(root: Path) -> list[Path]:
    names = {"ledger.json", "luna-transcript-ledger.json", "chunk-ledger.json"}
    return (
        sorted({path for path in root.rglob("*.json") if path.name in names})
        if root.is_dir()
        else []
    )


def _check_ledger(root: Path, queue: Json | None) -> Json:
    paths = _ledger_candidates(root)
    if not paths:
        return _record("missing", errors=["no chunk ledger found"], candidates=0)
    path = paths[-1]
    errors: list[str] = []
    try:
        ledger = _load(path)
    except (OSError, ValueError) as exc:
        return _record("invalid", errors=[str(exc)], ledger=str(path))
    jobs = ledger.get("jobs")
    summary = ledger.get("summary")
    if not isinstance(jobs, list) or not isinstance(summary, dict):
        return _record("invalid", errors=["ledger lacks jobs or summary"], ledger=str(path))
    counts = {
        name: sum(isinstance(job, dict) and job.get("status") == name for job in jobs)
        for name in ("pending", "leased", "completed", "failed")
    }
    for name, value in counts.items():
        if summary.get(name) != value:
            errors.append(f"ledger summary {name}={summary.get(name)!r}, observed {value}")
    expected_jobs = (
        len(queue.get("jobs", []))
        if isinstance(queue, dict) and isinstance(queue.get("jobs"), list)
        else None
    )
    if expected_jobs is not None and len(jobs) != expected_jobs:
        errors.append(f"ledger has {len(jobs)} jobs but queue has {expected_jobs}")
    output_refs = 0
    pending_chunks: list[Json] = []
    leased_chunks: list[Json] = []
    for job in jobs:
        if not isinstance(job, dict):
            errors.append("ledger job is not an object")
            continue
        for field in ("response_path", "structured_transcript_path"):
            value = job.get(field)
            if value is None:
                continue
            if not _safe_relative(value):
                errors.append(f"unsafe ledger {field}: {value!r}")
                continue
            output_refs += 1
            target = root / value
            if not target.is_file() or target.is_symlink():
                errors.append(f"missing ledger {field}: {target}")
            else:
                expected_hash = job.get(field.replace("_path", "_sha256"))
                if isinstance(expected_hash, str):
                    actual, _ = _sha256(target)
                    if actual != expected_hash:
                        errors.append(f"ledger hash mismatch: {target}")
        summary_record = {
            "job_id": job.get("job_id"),
            "bundle_id": job.get("bundle_id"),
            "chunk_order": job.get("chunk_order"),
            "worker_id": job.get("worker_id"),
            "attempts": job.get("attempts"),
        }
        if job.get("status") == "pending":
            pending_chunks.append(summary_record)
        elif job.get("status") == "leased":
            leased_chunks.append(summary_record)
    pending_chunks.sort(
        key=lambda value: (value.get("chunk_order", 0), str(value.get("job_id")))
    )
    leased_chunks.sort(
        key=lambda value: (value.get("chunk_order", 0), str(value.get("job_id")))
    )
    state = "ready" if not errors else "blocked"
    return _record(
        state,
        errors=errors,
        ledger=str(path),
        jobs=len(jobs),
        summary=summary,
        output_references=output_refs,
        next_chunks=pending_chunks[:3],
        leased_chunks=leased_chunks,
    )


def _check_worker_outputs(root: Path) -> Json:
    """Account for response and final-transcript files emitted by Luna workers."""
    if not root.is_dir():
        return _record("missing", errors=[f"missing worker output root: {root}"])
    response_files = (
        sorted((root / "responses").rglob("*.json"))
        if (root / "responses").is_dir()
        else []
    )
    structured_files = (
        sorted((root / "structured").rglob("*.json"))
        if (root / "structured").is_dir()
        else []
    )
    errors: list[str] = []
    checked = 0
    for path in response_files + structured_files:
        if path.is_symlink() or not path.is_file():
            errors.append(f"worker output is not a regular file: {path}")
            continue
        try:
            _load(path)
            _sha256(path)
        except (OSError, ValueError) as exc:
            errors.append(f"invalid worker output {path}: {exc}")
            continue
        checked += 1
    state = (
        "ready"
        if not errors and (response_files or structured_files)
        else "empty"
        if not errors
        else "blocked"
    )
    return _record(
        state,
        errors=errors,
        responses=len(response_files),
        structured_transcripts=len(structured_files),
        files_checked=checked,
    )


def _next_action(stages: Json, processes: list[Json]) -> tuple[str, bool]:
    active = [
        item.get("command", "") for item in processes if item.get("state") == "running"
    ]
    if any(
        re.search(r"cadgpt-regulations\s+page-probe(?:\s|$)", command) for command in active
    ):
        return (
            "Wait for the running Paddle page-probe process to finish, then rerun "
            "this status check.",
            False,
        )
    if any(
        re.search(r"cadgpt-regulations\s+transcribe(?:\s|$)", command) for command in active
    ):
        return (
            "Wait for the running transcription process to finish, then rerun "
            "this status check.",
            False,
        )
    acquisition = stages["acquisition"]["state"]
    if acquisition != "ready":
        return "Repair or rerun acquisition, then rerun this status check.", False
    probe = stages["page_probe"]["state"]
    if probe == "blocked" and any(
        "native-first" in error for error in stages["page_probe"].get("errors", [])
    ):
        return (
            "Implement or rerun the native-first page-probe; native pages must "
            "not have render.png/page_render.png before transcription.",
            False,
        )
    if probe != "ready":
        running = any(item.get("state") == "running" for item in processes)
        return (
            "Wait for the running Paddle page-probe process to finish, then rerun "
            "this status check."
            if running
            else "Run page-probe with Paddle CUDA gpu:0, then rerun this status check."
        ), False
    transcription = stages["transcription"]["state"]
    if transcription != "ready":
        return (
            "Run transcribe against the selected CUDA Paddle page-probe manifest, "
            "then rerun this status check.",
            False,
        )
    queue = stages["queue"]["state"]
    if queue != "ready":
        return (
            "Create the Luna transcript queue from the checked transcription "
            "manifest, then rerun this status check.",
            False,
        )
    ledger = stages["chunk_ledger"]["state"]
    if ledger == "missing":
        return (
            "Create the durable chunk ledger from jobs.json; do not start a worker "
            "without it.",
            False,
        )
    if ledger != "ready":
        return (
            "Repair the chunk ledger and its attested paths/hashes, then rerun this "
            "status check.",
            False,
        )
    summary = stages["chunk_ledger"].get("summary", {})
    if summary.get("failed", 0):
        return (
            "Inspect failed Luna chunks and retry only those chunks after preserving "
            "their error receipts.",
            False,
        )
    if summary.get("pending", 0) or summary.get("leased", 0):
        return (
            "Start or continue exactly three parallel Luna workers, one chunk per "
            "worker; ingest responses into the ledger.",
            False,
        )
    if summary.get("completed", 0) == summary.get("jobs", 0) and summary.get("jobs", 0):
        return (
            "Run the Persian structured-transcript validation and stop at that "
            "boundary; do not run English, IDS, or publication stages.",
            True,
        )
    return (
        "Reconcile the ledger summary with its job records, then rerun this status check.",
        False,
    )


def inspect(args: argparse.Namespace) -> Json:
    repo = args.repo_root.resolve()
    state_path = args.state or repo / ".cadgpt/inbr/pipeline-state.json"
    if args.state is None and not state_path.is_file():
        # Support a checked-in state contract as well as the coordinator's private receipt.
        checked_in_state = repo / "docs" / "inbr-pipeline-state.json"
        if checked_in_state.is_file():
            state_path = checked_in_state
    acquisition_receipt = (
        args.acquisition_receipt
        or repo / ".cadgpt/inbr/acquisition/revision-2026-09-06/acquisition.json"
    )
    transcription_root = (
        args.transcription_root
        or repo / ".cadgpt/inbr/transcription/revision-2026-09-09-paddle"
    )
    extraction_root = (
        args.extraction_root or repo / ".cadgpt/inbr/extraction/revision-2026-09-09-paddle"
    )
    acquisition = _check_acquisition(acquisition_receipt)
    expected_pages = (
        acquisition.get("summary", {}).get("pdf_pages")
        if isinstance(acquisition.get("summary"), dict)
        else None
    )
    probe = _check_probe(
        transcription_root, acquisition.get("receipt_sha256"), expected_pages
    )
    transcription = _check_transcription(
        transcription_root, probe if probe.get("state") == "ready" else None, expected_pages
    )
    queue = _check_queue(extraction_root, transcription_root)
    queue_obj: Json | None = None
    queue_path = extraction_root / "jobs.json"
    if queue_path.is_file() and not queue_path.is_symlink():
        try:
            queue_obj = _load(queue_path)
        except (OSError, ValueError):
            queue_obj = None
    ledger = _check_ledger(extraction_root, queue_obj)
    worker_outputs = _check_worker_outputs(extraction_root)
    processes = _processes(transcription_root) + _processes(extraction_root)
    stages = {
        "acquisition": acquisition,
        "page_probe": probe,
        "transcription": transcription,
        "queue": queue,
        "chunk_ledger": ledger,
        "worker_outputs": worker_outputs,
    }
    action, safe = _next_action(stages, processes)
    state_document: Json | None = None
    if state_path.is_file() and not state_path.is_symlink():
        try:
            state_document = _load(state_path)
        except (OSError, ValueError):
            state_document = None
    return {
        "schema_version": "1.0.0",
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "state_document": str(state_path),
        "state_document_present": state_document is not None,
        "roots": {
            "repo": str(repo),
            "acquisition_receipt": str(acquisition_receipt),
            "transcription": str(transcription_root),
            "extraction": str(extraction_root),
        },
        "stages": stages,
        "processes": processes,
        "next_safe_action": action,
        "safe_to_advance": safe,
        "boundary": "persian_structured_transcript",
        "forbidden_downstream": ["english_rules", "ids", "publication"],
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repo-root", type=Path, default=Path(__file__).resolve().parents[1]
    )
    parser.add_argument("--state", type=Path)
    parser.add_argument("--acquisition-receipt", type=Path)
    parser.add_argument("--transcription-root", type=Path)
    parser.add_argument("--extraction-root", type=Path)
    parser.add_argument(
        "--json", action="store_true", dest="as_json", help="emit machine-readable JSON"
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    result = inspect(args)
    if result["safe_to_advance"] or all(
        stage["state"] == "ready" for stage in result["stages"].values()
    ):
        exit_code = 0
    else:
        exit_code = 1
    if args.as_json:
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(f"INBR pipeline boundary: {result['boundary']}")
        for name, stage in result["stages"].items():
            print(f"{name}: {stage['state']}")
            for error in stage.get("errors", []):
                print(f"  - {error}")
        print(f"next safe action: {result['next_safe_action']}")
        print(f"safe to advance: {'yes' if result['safe_to_advance'] else 'no'}")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
