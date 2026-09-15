"""Source-bound Persian transcript jobs and a resumable parallel ledger.

The regulations package owns job construction and response validation, while the
host supplies the actual model transport. This keeps model SDKs out of the corpus
core and still guarantees that every Luna pass receives the same PDF evidence.
"""

from __future__ import annotations

import copy
import fcntl
import hashlib
import os
import tempfile
from contextlib import contextmanager, suppress
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from cadgpt_regulations.errors import ManifestError, RegulationsError
from cadgpt_regulations.jsonio import (
    JsonObject,
    canonical_bytes,
    loads_object,
    sha256_json,
    validate_schema,
)
from cadgpt_regulations.resources import load_packaged_json
from cadgpt_regulations.storage import (
    InstallStatus,
    ensure_private_tree,
    fsync_directory,
    install_immutable_bytes,
    read_attested_bytes,
    safe_path,
    validate_output_root,
)

LUNA_MODEL = "gpt-5.6-luna"
TRANSCRIPT_PASSES = ("structured_transcript",)
PROMPT_VERSION = "persian-structured-transcript-1.0.0"
_CHUNK_PROMPT_INSTRUCTION = (
    "Inspect the original PDF, page renders, native extraction when present, and "
    "raw PaddleOCR evidence together. Correct only disagreements supported by this "
    "evidence, preserve every Persian character, digit, punctuation mark, table "
    "cell, formula, and clause identifier, and mark unreadable content instead of "
    "guessing. Return strict JSON for one Persian structured transcript anchored to "
    "the supplied page and span IDs. Do not translate, produce English rules, "
    "generate IDS, or return prose outside the JSON response."
)
_QUEUE_SCHEMA = load_packaged_json(
    "cadgpt_regulations.schemas", "luna-transcript-queue.schema.json"
)
_JOB_SCHEMA = load_packaged_json(
    "cadgpt_regulations.schemas", "luna-transcript-job.schema.json"
)
_TRANSCRIPT_SCHEMA = load_packaged_json(
    "cadgpt_regulations.schemas", "structured-transcript.schema.json"
)
_LEDGER_SCHEMA = load_packaged_json(
    "cadgpt_regulations.schemas", "luna-transcript-ledger.schema.json"
)
TRANSCRIPT_SCHEMA_SHA256 = sha256_json(_TRANSCRIPT_SCHEMA)
PROMPT_SHA256 = sha256_json(
    {
        "version": PROMPT_VERSION,
        "passes": list(TRANSCRIPT_PASSES),
        "instruction": _CHUNK_PROMPT_INSTRUCTION,
    }
)


class LunaTranscriptError(RegulationsError):
    """A master job or Luna response violates its source contract."""


@dataclass(frozen=True)
class LunaChunkClaim:
    """One deterministic lease returned to a Luna worker."""

    job_id: str
    chunk_order: int
    worker_id: str
    attempts: int
    lease_token: str
    job: JsonObject | None = None


@dataclass(frozen=True)
class LunaClaimResult:
    """Updated ledger plus the leases selected for one worker."""

    ledger: JsonObject
    claims: tuple[LunaChunkClaim, ...]


@dataclass(frozen=True)
class LunaLedgerResult:
    """Updated ledger and durable artifact paths from a completion/failure."""

    ledger: JsonObject
    response_path: Path | None = None
    structured_transcript_path: Path | None = None


def build_luna_transcript_jobs(
    transcription: JsonObject,
    *,
    transcription_root: Path,
    acquisition_root: Path,
    model: str = LUNA_MODEL,
) -> JsonObject:
    """Build one source-bound structured-transcript job for each bundle.

    Bundles are sorted by catalog order, source page range, and bundle ID before
    assigning ``chunk_order``. This makes worker assignment reproducible even when
    the upstream transcription manifest was produced by concurrent workers.
    """
    documents = cast(list[JsonObject], transcription["documents"])
    jobs: list[JsonObject] = []
    candidates: list[tuple[JsonObject, JsonObject, JsonObject, list[JsonObject], str]] = []
    for document in documents:
        source_sha256 = cast(str, document["source_sha256"])
        source_path = cast(str, document["artifact_path"])
        source_bytes = cast(int, document["source_bytes"])
        source = safe_path(acquisition_root, source_path)
        read_attested_bytes(
            source,
            expected_sha256=source_sha256,
            expected_bytes=source_bytes,
        )
        for reference in cast(list[JsonObject], document["bundles"]):
            bundle_path = safe_path(transcription_root, cast(str, reference["path"]))
            payload, snapshot = read_attested_bytes(
                bundle_path,
                expected_sha256=cast(str, reference["sha256"]),
            )
            bundle = loads_object(
                payload.decode("utf-8"), description="transcription bundle"
            )
            pages = [
                _page_input(transcription_root, page)
                for page in cast(list[JsonObject], bundle["pages"])
            ]
            if not pages:
                continue
            candidates.append((document, reference, snapshot, pages, source_path))
    candidates.sort(
        key=lambda item: (
            int(item[0]["catalog_order"]),
            int(item[1]["start_pdf_page"]),
            int(item[1]["end_pdf_page"]),
            str(item[1]["bundle_id"]),
        )
    )
    previous_end: dict[str, int] = {}
    for chunk_order, (document, reference, snapshot, pages, source_path) in enumerate(
        candidates, start=1
    ):
        source_sha256 = cast(str, document["source_sha256"])
        source_bytes = cast(int, document["source_bytes"])
        last_page = previous_end.get(source_sha256, 0)
        overlap_page_ids = [
            page["page_id"] for page in pages if cast(int, page["pdf_page"]) <= last_page
        ]
        previous_end[source_sha256] = cast(int, reference["end_pdf_page"])
        identity: JsonObject = {
            "source_sha256": source_sha256,
            "bundle_id": reference["bundle_id"],
            "bundle_sha256": snapshot.sha256,
            "start_pdf_page": reference["start_pdf_page"],
            "end_pdf_page": reference["end_pdf_page"],
            "model": model,
            "passes": list(TRANSCRIPT_PASSES),
            "prompt_sha256": PROMPT_SHA256,
            "response_schema_sha256": TRANSCRIPT_SCHEMA_SHA256,
        }
        jobs.append(
            {
                "job_id": f"sha256:{sha256_json(identity)}",
                "state": "pending",
                "chunk_order": chunk_order,
                "overlap_page_ids": overlap_page_ids,
                "model": model,
                "passes": list(TRANSCRIPT_PASSES),
                "prompt_version": PROMPT_VERSION,
                "prompt_sha256": PROMPT_SHA256,
                "response_schema_sha256": TRANSCRIPT_SCHEMA_SHA256,
                "catalog_key": document["catalog_key"],
                "catalog_order": document["catalog_order"],
                "source_sha256": source_sha256,
                "source_bytes": source_bytes,
                "original_pdf": {
                    "path": source_path,
                    "sha256": source_sha256,
                    "bytes": source_bytes,
                },
                "bundle_id": reference["bundle_id"],
                "bundle_path": reference["path"],
                "bundle_sha256": snapshot.sha256,
                "start_pdf_page": reference["start_pdf_page"],
                "end_pdf_page": reference["end_pdf_page"],
                "pages": pages,
            }
        )
    manifest: JsonObject = {
        "schema_version": "1.0.0",
        "model": model,
        "passes": list(TRANSCRIPT_PASSES),
        "prompt_version": PROMPT_VERSION,
        "prompt_sha256": PROMPT_SHA256,
        "response_schema_sha256": TRANSCRIPT_SCHEMA_SHA256,
        "transcription_sha256": hashlib.sha256(canonical_bytes(transcription)).hexdigest(),
        "jobs": jobs,
        "summary": {"jobs": len(jobs), "pending": len(jobs), "completed": 0},
    }
    validate_luna_jobs(manifest)
    return manifest


def _page_input(root: Path, page: JsonObject) -> JsonObject:
    normalized_path = cast(str, page["normalized_text_path"])
    package = Path(normalized_path).parent
    evidence_path = package / "evidence.json"
    evidence_payload, evidence_snapshot = read_attested_bytes(
        safe_path(root, evidence_path.as_posix())
    )
    evidence = loads_object(evidence_payload.decode("utf-8"), description="page evidence")
    artifacts = {
        cast(str, item["role"]): item
        for item in cast(list[JsonObject], evidence["artifacts"])
    }
    probe = cast(JsonObject, evidence["probe"])
    probe_package = Path(cast(str, probe["package_path"]))
    native_layout_path = probe_package / "native.json"
    _, native_snapshot = read_attested_bytes(safe_path(root, native_layout_path.as_posix()))
    render_path = probe_package / "render.png"
    render_snapshot = None
    if safe_path(root, render_path.as_posix()).exists():
        _, render_snapshot = read_attested_bytes(safe_path(root, render_path.as_posix()))
    native_text = artifacts["raw_native_text"]
    native_text_payload, _ = read_attested_bytes(
        safe_path(root, cast(str, native_text["path"])),
        expected_sha256=cast(str, native_text["sha256"]),
    )
    normalized_text = artifacts["normalized_search_text"]
    paddle = artifacts.get("ocr_layout")
    native_present = bool(native_text_payload.decode("utf-8").strip())
    native_text_path: str | None = (
        cast(str, native_text["path"]) if native_present else None
    )
    native_text_sha256: str | None = (
        cast(str, native_text["sha256"]) if native_present else None
    )
    return {
        "page_id": page["page_id"],
        "pdf_page": page["pdf_page"],
        "state": page["state"],
        "classification": probe["classification"],
        "route": probe["route"],
        "evidence_path": evidence_path.as_posix(),
        "evidence_sha256": evidence_snapshot.sha256,
        "native_layout_path": native_layout_path.as_posix(),
        "native_layout_sha256": native_snapshot.sha256,
        "native_text_path": native_text_path,
        "native_text_sha256": native_text_sha256,
        "paddle_result_path": None if paddle is None else paddle["path"],
        "paddle_result_sha256": None if paddle is None else paddle["sha256"],
        "page_render_path": None if render_snapshot is None else render_path.as_posix(),
        "page_render_sha256": None if render_snapshot is None else render_snapshot.sha256,
        "normalized_text_path": normalized_path,
        "normalized_text_sha256": normalized_text["sha256"],
    }


def validate_luna_jobs(manifest: JsonObject) -> None:
    """Reject reordered passes, duplicate jobs, or false source identities."""
    try:
        validate_schema(manifest, _QUEUE_SCHEMA, description="Luna transcript queue")
    except ManifestError as exc:
        raise LunaTranscriptError(str(exc)) from exc
    if manifest["passes"] != list(TRANSCRIPT_PASSES):
        raise LunaTranscriptError("Luna transcript queue must contain one structured pass")
    jobs = cast(list[JsonObject], manifest["jobs"])
    summary = cast(JsonObject, manifest["summary"])
    if summary != {"jobs": len(jobs), "pending": len(jobs), "completed": 0}:
        raise LunaTranscriptError("Luna transcript queue summary differs from its jobs")
    seen: set[str] = set()
    previous_end: dict[str, int] = {}
    for job in jobs:
        validate_luna_job(job)
        if "overlap_page_ids" in job:
            source = cast(str, job["source_sha256"])
            last_page = previous_end.get(source, 0)
            start = cast(int, job["start_pdf_page"])
            if start not in ({1} if last_page == 0 else {last_page, last_page + 1}):
                raise LunaTranscriptError("Luna chunks have a gap or excessive overlap")
            expected_overlap = [
                page["page_id"]
                for page in cast(list[JsonObject], job["pages"])
                if cast(int, page["pdf_page"]) <= last_page
            ]
            if job["overlap_page_ids"] != expected_overlap:
                raise LunaTranscriptError("Luna chunk overlap declaration differs")
            previous_end[source] = cast(int, job["end_pdf_page"])
        job_id = cast(str, job["job_id"])
        if job_id in seen:
            raise LunaTranscriptError("duplicate Luna transcript job ID")
        seen.add(job_id)
        for field in (
            "model",
            "passes",
            "prompt_version",
            "prompt_sha256",
            "response_schema_sha256",
        ):
            if field in job and field in manifest and job[field] != manifest[field]:
                raise LunaTranscriptError(f"Luna job differs from queue at {field}")
    if manifest["passes"] == list(TRANSCRIPT_PASSES):
        orders = [int(job.get("chunk_order", 0)) for job in jobs]
        if orders != list(range(1, len(jobs) + 1)):
            raise LunaTranscriptError("Luna transcript chunk order is not contiguous")


def validate_luna_job(job: JsonObject) -> None:
    try:
        validate_schema(job, _JOB_SCHEMA, description="Luna transcript job")
    except ManifestError as exc:
        raise LunaTranscriptError(str(exc)) from exc
    identity: JsonObject = {
        "source_sha256": job["source_sha256"],
        "bundle_id": job["bundle_id"],
        "bundle_sha256": job["bundle_sha256"],
        "start_pdf_page": job["start_pdf_page"],
        "end_pdf_page": job["end_pdf_page"],
        "model": job["model"],
        "passes": job["passes"],
        "prompt_sha256": job["prompt_sha256"],
        "response_schema_sha256": job["response_schema_sha256"],
    }
    if job["job_id"] != f"sha256:{sha256_json(identity)}":
        raise LunaTranscriptError("Luna transcript job identity drift")
    if job["passes"] != list(TRANSCRIPT_PASSES):
        raise LunaTranscriptError("Luna transcript job must contain one structured pass")
    pages = cast(list[JsonObject], job["pages"])
    if [page["pdf_page"] for page in pages] != list(
        range(cast(int, job["start_pdf_page"]), cast(int, job["end_pdf_page"]) + 1)
    ):
        raise LunaTranscriptError("Luna transcript chunk has missing or reordered pages")


def _ledger_summary(records: list[JsonObject]) -> JsonObject:
    counts = {state: 0 for state in ("pending", "leased", "completed", "failed")}
    for record in records:
        counts[cast(str, record["status"])] += 1
    return {
        "jobs": len(records),
        "pending": counts["pending"],
        "leased": counts["leased"],
        "completed": counts["completed"],
        "failed": counts["failed"],
    }


def build_luna_chunk_ledger(queue: JsonObject) -> JsonObject:
    """Create the durable, resumable state for a transcript queue."""
    validate_luna_jobs(queue)
    jobs = sorted(
        cast(list[JsonObject], queue["jobs"]),
        key=lambda item: int(item.get("chunk_order", 0)),
    )
    records: list[JsonObject] = []
    for order, job in enumerate(jobs, start=1):
        chunk_order = int(job.get("chunk_order", order))
        records.append(
            {
                "job_id": job["job_id"],
                "bundle_id": job["bundle_id"],
                "chunk_order": chunk_order,
                "status": "pending",
                "worker_id": None,
                "attempts": 0,
                "lease_token": None,
                "response_path": None,
                "response_sha256": None,
                "structured_transcript_path": None,
                "structured_transcript_sha256": None,
                "last_error": None,
            }
        )
    ledger: JsonObject = {
        "schema_version": "1.0.0",
        "queue_sha256": sha256_json(queue),
        "jobs": records,
        "summary": _ledger_summary(records),
    }
    validate_luna_ledger(ledger, queue=queue)
    return ledger


def install_luna_ledger(
    ledger: JsonObject, *, output_root: Path
) -> tuple[Path, InstallStatus]:
    """Install one content-addressed ledger snapshot under an output root."""
    validate_luna_ledger(ledger)
    validate_output_root(output_root, description="Luna transcript output root")
    directory = ensure_private_tree(output_root, "ledger")
    digest = sha256_json(ledger)
    path = directory / f"{digest}.json"
    result = install_immutable_bytes(path, canonical_bytes(ledger), expected_sha256=digest)
    return path, result.status


def load_luna_ledger(queue: JsonObject, *, output_root: Path) -> JsonObject:
    """Load the mutable ledger, creating its initial snapshot when absent."""
    validate_luna_jobs(queue)
    validate_output_root(output_root, description="Luna transcript output root")
    path = output_root / "ledger.json"
    if not path.exists():
        ledger = build_luna_chunk_ledger(queue)
        save_luna_ledger(ledger, output_root=output_root)
        return ledger
    try:
        payload, _ = read_attested_bytes(path)
        ledger = loads_object(payload.decode("utf-8"), description="Luna transcript ledger")
    except (ManifestError, UnicodeDecodeError) as exc:
        raise LunaTranscriptError(str(exc)) from exc
    validate_luna_ledger(ledger, queue=queue)
    return ledger


def save_luna_ledger(ledger: JsonObject, *, output_root: Path) -> Path:
    """Atomically update the mutable ledger and retain an immutable snapshot."""
    validate_luna_ledger(ledger)
    validate_output_root(output_root, description="Luna transcript output root")
    payload = canonical_bytes(ledger)
    destination = output_root / "ledger.json"
    if destination.is_symlink():
        raise LunaTranscriptError("Luna ledger pointer must not be a symlink")
    install_luna_ledger(ledger, output_root=output_root)
    fd, temporary_name = tempfile.mkstemp(prefix=".ledger.", suffix=".tmp", dir=output_root)
    temporary = Path(temporary_name)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "wb") as stream:
            fd = -1
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        temporary.replace(destination)
        fsync_directory(output_root)
    except OSError as exc:
        raise LunaTranscriptError(f"cannot update Luna ledger: {exc}") from exc
    finally:
        if fd >= 0:
            os.close(fd)
        with suppress(FileNotFoundError):
            temporary.unlink()
    return destination


@contextmanager
def luna_ledger_lock(output_root: Path):
    """Serialize lease and completion updates from concurrent workers."""
    validate_output_root(output_root, description="Luna transcript output root")
    path = output_root / "ledger.lock"
    try:
        descriptor = os.open(
            path,
            os.O_CREAT | os.O_RDWR | getattr(os, "O_NOFOLLOW", 0),
            0o600,
        )
        os.fchmod(descriptor, 0o600)
    except OSError as exc:
        raise LunaTranscriptError(f"cannot open Luna ledger lock: {exc}") from exc
    try:
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        yield
    finally:
        fcntl.flock(descriptor, fcntl.LOCK_UN)
        os.close(descriptor)


def lease_luna_chunks(
    queue: JsonObject,
    *,
    output_root: Path,
    worker_id: str,
    max_workers: int,
) -> LunaClaimResult:
    """Load, claim, and durably save up to ``max_workers`` pending chunks."""
    with luna_ledger_lock(output_root):
        ledger = load_luna_ledger(queue, output_root=output_root)
        result = claim_luna_chunks(
            ledger, worker_id=worker_id, max_workers=max_workers, queue=queue
        )
        save_luna_ledger(result.ledger, output_root=output_root)
        return result


def get_next(
    queue: JsonObject, *, output_root: Path, max_workers: int = 1
) -> tuple[JsonObject, ...]:
    """Return the next pending chunks without changing the ledger."""
    if max_workers < 1:
        raise LunaTranscriptError("max_workers must be positive")
    validate_luna_jobs(queue)
    validate_output_root(output_root, description="Luna transcript output root")
    ledger_path = output_root / "ledger.json"
    if ledger_path.exists():
        ledger = load_luna_ledger(queue, output_root=output_root)
    else:
        ledger = build_luna_chunk_ledger(queue)
    jobs = {cast(str, job["job_id"]): job for job in cast(list[JsonObject], queue["jobs"])}
    pending: list[JsonObject] = []
    for record in cast(list[JsonObject], ledger["jobs"]):
        if record["status"] != "pending":
            continue
        chunk = copy.deepcopy(jobs[cast(str, record["job_id"])])
        chunk["status"] = record["status"]
        chunk["ledger"] = copy.deepcopy(record)
        pending.append(chunk)
        if len(pending) >= max_workers:
            break
    return tuple(pending)


def mark_started(
    queue: JsonObject,
    *,
    output_root: Path,
    worker_id: str,
    max_workers: int = 1,
) -> LunaClaimResult:
    """Atomically lease one or a bounded batch of pending chunks."""
    return lease_luna_chunks(
        queue,
        output_root=output_root,
        worker_id=worker_id,
        max_workers=max_workers,
    )


def ingest_luna_chunk(
    queue: JsonObject,
    *,
    output_root: Path,
    job_id: str,
    worker_id: str,
    lease_token: str,
    response_path: Path,
) -> LunaLedgerResult:
    """Validate, persist, and atomically account for one worker response."""
    try:
        payload, _ = read_attested_bytes(response_path)
        response = loads_object(payload.decode("utf-8"), description="Luna response")
    except (ManifestError, UnicodeDecodeError) as exc:
        raise LunaTranscriptError(str(exc)) from exc
    with luna_ledger_lock(output_root):
        ledger = load_luna_ledger(queue, output_root=output_root)
        result = complete_luna_chunk(
            ledger,
            queue,
            job_id=job_id,
            worker_id=worker_id,
            lease_token=lease_token,
            response=response,
            output_root=output_root,
        )
        save_luna_ledger(result.ledger, output_root=output_root)
        return result


def mark_finished(
    queue: JsonObject,
    *,
    output_root: Path,
    job_id: str,
    worker_id: str,
    lease_token: str,
    response: JsonObject | None = None,
    response_path: Path | None = None,
) -> LunaLedgerResult:
    """Atomically validate, persist, and complete one chunk response.

    Coordinator code can pass the decoded response object directly; the optional
    path form keeps the command-line transport backward compatible.
    """
    if response is not None and response_path is not None:
        raise LunaTranscriptError("provide response or response_path, not both")
    if response_path is not None:
        return ingest_luna_chunk(
            queue,
            output_root=output_root,
            job_id=job_id,
            worker_id=worker_id,
            lease_token=lease_token,
            response_path=response_path,
        )
    if response is None:
        raise LunaTranscriptError("a Luna response is required")
    with luna_ledger_lock(output_root):
        ledger = load_luna_ledger(queue, output_root=output_root)
        result = complete_luna_chunk(
            ledger,
            queue,
            job_id=job_id,
            worker_id=worker_id,
            lease_token=lease_token,
            response=response,
            output_root=output_root,
        )
        save_luna_ledger(result.ledger, output_root=output_root)
        return result


def record_luna_chunk_failure(
    queue: JsonObject,
    *,
    output_root: Path,
    job_id: str,
    worker_id: str,
    lease_token: str,
    error: str,
) -> JsonObject:
    """Atomically persist a worker failure in the ledger."""
    with luna_ledger_lock(output_root):
        ledger = load_luna_ledger(queue, output_root=output_root)
        updated = fail_luna_chunk(
            ledger,
            job_id=job_id,
            worker_id=worker_id,
            lease_token=lease_token,
            error=error,
            queue=queue,
        )
        save_luna_ledger(updated, output_root=output_root)
        return updated


def mark_failed(
    queue: JsonObject,
    *,
    output_root: Path,
    job_id: str,
    worker_id: str,
    lease_token: str,
    error: str,
) -> JsonObject:
    """Atomically record a failed worker attempt."""
    return record_luna_chunk_failure(
        queue,
        output_root=output_root,
        job_id=job_id,
        worker_id=worker_id,
        lease_token=lease_token,
        error=error,
    )


def requeue_failed_luna_chunk(
    queue: JsonObject, *, output_root: Path, job_id: str
) -> JsonObject:
    """Atomically make one failed chunk available for another attempt."""
    with luna_ledger_lock(output_root):
        ledger = load_luna_ledger(queue, output_root=output_root)
        updated = requeue_luna_chunk(ledger, job_id=job_id, queue=queue)
        save_luna_ledger(updated, output_root=output_root)
        return updated


def reclaim_luna_chunk_from_ledger(
    queue: JsonObject, *, output_root: Path, job_id: str
) -> JsonObject:
    """Atomically reclaim a lease left by an interrupted worker."""
    with luna_ledger_lock(output_root):
        ledger = load_luna_ledger(queue, output_root=output_root)
        updated = reclaim_luna_chunk(ledger, job_id=job_id, queue=queue)
        save_luna_ledger(updated, output_root=output_root)
        return updated


def reclaim(queue: JsonObject, *, output_root: Path, job_id: str) -> JsonObject:
    """Atomically reclaim a lease left by an interrupted worker."""
    return reclaim_luna_chunk_from_ledger(queue, output_root=output_root, job_id=job_id)


def validate_luna_ledger(ledger: JsonObject, *, queue: JsonObject | None = None) -> None:
    """Validate ledger shape, stable ordering, and optional queue binding."""
    try:
        validate_schema(ledger, _LEDGER_SCHEMA, description="Luna transcript ledger")
    except ManifestError as exc:
        raise LunaTranscriptError(str(exc)) from exc
    records = cast(list[JsonObject], ledger["jobs"])
    orders = [int(record["chunk_order"]) for record in records]
    if orders != list(range(1, len(records) + 1)):
        raise LunaTranscriptError("Luna ledger chunk order is not contiguous")
    if len({record["job_id"] for record in records}) != len(records):
        raise LunaTranscriptError("duplicate Luna ledger job ID")
    for record in records:
        status = cast(str, record["status"])
        if status == "leased" and (not record["worker_id"] or not record["lease_token"]):
            raise LunaTranscriptError("leased Luna chunk lacks worker or lease token")
        if status == "completed" and (
            not record["response_path"]
            or not record["response_sha256"]
            or not record["structured_transcript_path"]
            or not record["structured_transcript_sha256"]
        ):
            raise LunaTranscriptError("completed Luna chunk lacks durable outputs")
        if status == "failed" and not record["last_error"]:
            raise LunaTranscriptError("failed Luna chunk lacks an error")
    if ledger["summary"] != _ledger_summary(records):
        raise LunaTranscriptError("Luna ledger summary differs from its jobs")
    if queue is not None:
        validate_luna_jobs(queue)
        if ledger["queue_sha256"] != sha256_json(queue):
            raise LunaTranscriptError("Luna ledger queue identity differs")
        jobs = {
            cast(str, job["job_id"]): job for job in cast(list[JsonObject], queue["jobs"])
        }
        for record in records:
            job = jobs.get(cast(str, record["job_id"]))
            if job is None or job["bundle_id"] != record["bundle_id"]:
                raise LunaTranscriptError("Luna ledger job is not present in its queue")


def claim_luna_chunks(
    ledger: JsonObject,
    *,
    worker_id: str,
    max_workers: int,
    queue: JsonObject | None = None,
) -> LunaClaimResult:
    """Lease the next pending chunks in deterministic order for one worker."""
    if not worker_id or max_workers < 1:
        raise LunaTranscriptError("worker_id and positive max_workers are required")
    validate_luna_ledger(ledger, queue=queue)
    updated = copy.deepcopy(ledger)
    records = cast(list[JsonObject], updated["jobs"])
    queue_jobs = (
        {cast(str, job["job_id"]): job for job in cast(list[JsonObject], queue["jobs"])}
        if queue is not None
        else {}
    )
    claims: list[LunaChunkClaim] = []
    for record in records:
        if len(claims) >= max_workers or record["status"] != "pending":
            continue
        attempts = int(record["attempts"]) + 1
        token_identity: JsonObject = {
            "queue_sha256": updated["queue_sha256"],
            "job_id": record["job_id"],
            "worker_id": worker_id,
            "attempts": attempts,
        }
        token = f"sha256:{sha256_json(token_identity)}"
        record.update(
            {
                "status": "leased",
                "worker_id": worker_id,
                "attempts": attempts,
                "lease_token": token,
                "last_error": None,
            }
        )
        claims.append(
            LunaChunkClaim(
                job_id=cast(str, record["job_id"]),
                chunk_order=int(record["chunk_order"]),
                worker_id=worker_id,
                attempts=attempts,
                lease_token=token,
                job=copy.deepcopy(queue_jobs.get(cast(str, record["job_id"]))),
            )
        )
    updated["summary"] = _ledger_summary(records)
    validate_luna_ledger(updated, queue=queue)
    return LunaClaimResult(ledger=updated, claims=tuple(claims))


def complete_luna_chunk(
    ledger: JsonObject,
    queue: JsonObject,
    *,
    job_id: str,
    worker_id: str,
    lease_token: str,
    response: JsonObject,
    output_root: Path,
) -> LunaLedgerResult:
    """Persist one structured response and mark its lease completed idempotently."""
    validate_luna_ledger(ledger, queue=queue)
    jobs = {cast(str, job["job_id"]): job for job in cast(list[JsonObject], queue["jobs"])}
    job = jobs.get(job_id)
    if job is None:
        raise LunaTranscriptError("unknown Luna transcript job")
    _validate_response(response, job=job, pass_name=TRANSCRIPT_PASSES[0])
    structured = cast(JsonObject, response.get("structured_transcript"))
    validate_structured_transcript(structured, job=job)
    if "overlap_page_ids" in job:
        validate_response_pages(response, job=job)
    updated = copy.deepcopy(ledger)
    records = cast(list[JsonObject], updated["jobs"])
    record = next(item for item in records if item["job_id"] == job_id)
    if record["status"] == "completed":
        if (
            record["response_sha256"]
            != hashlib.sha256(canonical_bytes(response)).hexdigest()
        ):
            raise LunaTranscriptError("completed Luna chunk has a different response")
        return LunaLedgerResult(ledger=copy.deepcopy(ledger))
    if (
        record["status"] != "leased"
        or record["worker_id"] != worker_id
        or record["lease_token"] != lease_token
    ):
        raise LunaTranscriptError(
            "Luna chunk lease is missing or does not belong to worker"
        )
    validate_output_root(output_root, description="Luna transcript output root")
    token = hashlib.sha256(job_id.encode("utf-8")).hexdigest()
    response_dir = ensure_private_tree(
        output_root, f"responses/{token}/structured_transcript"
    )
    response_bytes = canonical_bytes(response)
    response_sha = hashlib.sha256(response_bytes).hexdigest()
    response_path = response_dir / f"{response_sha}.json"
    install_immutable_bytes(response_path, response_bytes, expected_sha256=response_sha)
    structured_dir = ensure_private_tree(output_root, f"structured/{token}")
    structured_bytes = canonical_bytes(structured)
    structured_sha = hashlib.sha256(structured_bytes).hexdigest()
    structured_path = structured_dir / f"{structured_sha}.json"
    install_immutable_bytes(
        structured_path, structured_bytes, expected_sha256=structured_sha
    )
    record.update(
        {
            "status": "completed",
            "response_path": response_path.relative_to(output_root).as_posix(),
            "response_sha256": response_sha,
            "structured_transcript_path": structured_path.relative_to(
                output_root
            ).as_posix(),
            "structured_transcript_sha256": structured_sha,
            "last_error": None,
        }
    )
    # Update only after both immutable payloads are installed.
    updated["summary"] = _ledger_summary(records)
    validate_luna_ledger(updated, queue=queue)
    return LunaLedgerResult(updated, response_path, structured_path)


def fail_luna_chunk(
    ledger: JsonObject,
    *,
    job_id: str,
    worker_id: str,
    lease_token: str,
    error: str,
    queue: JsonObject | None = None,
) -> JsonObject:
    """Record a failed lease without losing its attempt history."""
    if not error:
        raise LunaTranscriptError("failure reason is required")
    validate_luna_ledger(ledger, queue=queue)
    updated = copy.deepcopy(ledger)
    record = next(
        (
            item
            for item in cast(list[JsonObject], updated["jobs"])
            if item["job_id"] == job_id
        ),
        None,
    )
    if record is None:
        raise LunaTranscriptError("unknown Luna transcript job")
    if record["status"] == "failed" and record["last_error"] == error:
        return updated
    if (
        record["status"] != "leased"
        or record["worker_id"] != worker_id
        or record["lease_token"] != lease_token
    ):
        raise LunaTranscriptError(
            "Luna chunk lease is missing or does not belong to worker"
        )
    record.update({"status": "failed", "last_error": error})
    updated["summary"] = _ledger_summary(cast(list[JsonObject], updated["jobs"]))
    validate_luna_ledger(updated, queue=queue)
    return updated


def requeue_luna_chunk(
    ledger: JsonObject,
    *,
    job_id: str,
    queue: JsonObject | None = None,
) -> JsonObject:
    """Return a failed chunk to pending while retaining its attempt count."""
    validate_luna_ledger(ledger, queue=queue)
    updated = copy.deepcopy(ledger)
    record = next(
        (
            item
            for item in cast(list[JsonObject], updated["jobs"])
            if item["job_id"] == job_id
        ),
        None,
    )
    if record is None:
        raise LunaTranscriptError("unknown Luna transcript job")
    if record["status"] == "pending":
        return updated
    if record["status"] != "failed":
        raise LunaTranscriptError("only failed Luna chunks can be requeued")
    record.update({"status": "pending", "worker_id": None, "lease_token": None})
    updated["summary"] = _ledger_summary(cast(list[JsonObject], updated["jobs"]))
    validate_luna_ledger(updated, queue=queue)
    return updated


def reclaim_luna_chunk(
    ledger: JsonObject,
    *,
    job_id: str,
    queue: JsonObject | None = None,
) -> JsonObject:
    """Return an abandoned lease to pending after a worker interruption."""
    validate_luna_ledger(ledger, queue=queue)
    updated = copy.deepcopy(ledger)
    record = next(
        (
            item
            for item in cast(list[JsonObject], updated["jobs"])
            if item["job_id"] == job_id
        ),
        None,
    )
    if record is None:
        raise LunaTranscriptError("unknown Luna transcript job")
    if record["status"] == "pending":
        return updated
    if record["status"] != "leased":
        raise LunaTranscriptError("only leased Luna chunks can be reclaimed")
    record.update({"status": "pending", "worker_id": None, "lease_token": None})
    updated["summary"] = _ledger_summary(cast(list[JsonObject], updated["jobs"]))
    validate_luna_ledger(updated, queue=queue)
    return updated


def _validate_response(response: JsonObject, *, job: JsonObject, pass_name: str) -> None:
    if response.get("schema_version") != "1.0.0":
        raise LunaTranscriptError("Luna response has an unsupported schema version")
    if response.get("job_id") != job["job_id"]:
        raise LunaTranscriptError("Luna response is not bound to its job")
    if response.get("pass") != pass_name:
        raise LunaTranscriptError("Luna response pass differs from requested pass")
    if response.get("source_sha256") != job["source_sha256"]:
        raise LunaTranscriptError("Luna response source identity differs")
    if response.get("model") != job["model"]:
        raise LunaTranscriptError("Luna response model differs from job")
    if response.get("prompt_sha256") != job["prompt_sha256"]:
        raise LunaTranscriptError("Luna response prompt identity differs")
    if response.get("response_schema_sha256") != job["response_schema_sha256"]:
        raise LunaTranscriptError("Luna response schema identity differs")
    if not isinstance(response.get("transcript_fa"), str):
        raise LunaTranscriptError("Luna response must contain transcript_fa")
    if pass_name != TRANSCRIPT_PASSES[0] or not isinstance(
        response.get("structured_transcript"), dict
    ):
        raise LunaTranscriptError("Luna response lacks structured_transcript")


def validate_structured_transcript(
    value: JsonObject, *, job: JsonObject | None = None
) -> None:
    """Validate the final Persian-only structured transcript and source binding."""
    try:
        validate_schema(
            value,
            _TRANSCRIPT_SCHEMA,
            description="Persian structured transcript",
        )
    except ManifestError as exc:
        raise LunaTranscriptError(str(exc)) from exc
    if job is not None:
        source = cast(JsonObject, value["source"])
        if source["source_sha256"] != job["source_sha256"]:
            raise LunaTranscriptError("structured transcript source hash differs from job")
        if source["bundle_id"] != job["bundle_id"]:
            raise LunaTranscriptError("structured transcript bundle differs from job")


def validate_response_pages(response: JsonObject, *, job: JsonObject) -> None:
    """Require source-bound page coverage before a current chunk can be completed."""
    structured = cast(JsonObject, response["structured_transcript"])
    for field in ("catalog_key", "start_pdf_page", "end_pdf_page"):
        if structured["source"][field] != job[field]:
            raise LunaTranscriptError(f"structured transcript differs at {field}")
    for field in ("chunk_order", "catalog_order", "overlap_page_ids"):
        if response.get(field) != job.get(field):
            raise LunaTranscriptError(f"response differs at {field}")
    expected_ids = [page["page_id"] for page in job["pages"]]
    if response.get("ordered_page_ids") != expected_ids:
        raise LunaTranscriptError("response ordered page IDs differ from job")
    pages = response.get("page_transcripts")
    if not isinstance(pages, list) or len(pages) != len(expected_ids):
        raise LunaTranscriptError("response lacks the complete page transcript list")
    for source_page, page in zip(job["pages"], pages, strict=True):
        if not isinstance(page, dict) or any(
            page.get(field) != source_page[field] for field in ("page_id", "pdf_page")
        ):
            raise LunaTranscriptError("response pages are missing or reordered")
        if not isinstance(page.get("text_fa"), str):
            raise LunaTranscriptError("page transcript text must be a string")
        if page["text_fa"] and not any(
            section["source_page_ids"] == [page["page_id"]]
            and section["text_fa"] == page["text_fa"]
            for section in structured["sections"]
        ):
            raise LunaTranscriptError("page text differs from its structured section")
    if response["transcript_fa"] != structured["transcript_fa"]:
        raise LunaTranscriptError("response and structured transcript text differ")


def luna_chunk_prompt() -> str:
    """Return the single-pass prompt used by every parallel chunk worker."""
    return _CHUNK_PROMPT_INSTRUCTION + (
        f" Output JSON only and conform to the structured transcript response "
        f"schema hash {TRANSCRIPT_SCHEMA_SHA256}."
    )
