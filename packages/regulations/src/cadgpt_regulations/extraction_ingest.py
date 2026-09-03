"""Durably ingest source-anchored blind Luna responses."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import cast

from cadgpt_regulations.errors import RegulationsError
from cadgpt_regulations.extraction_jobs import validate_extraction_jobs
from cadgpt_regulations.jsonio import (
    JsonObject,
    canonical_bytes,
    loads_object,
    sha256_json,
)
from cadgpt_regulations.semantic_check import (
    SemanticCheckError,
    SemanticCheckResult,
    check_semantic_artifact,
)
from cadgpt_regulations.semantic_reconcile import (
    SemanticReconciliationError,
    reconcile_validator,
)
from cadgpt_regulations.storage import (
    InstallStatus,
    StorageError,
    ensure_private_tree,
    install_immutable_bytes,
    read_attested_bytes,
    read_regular_snapshot,
    safe_path,
    validate_output_root,
)


class ExtractionIngestError(RegulationsError):
    """Raised when a worker response cannot be bound to one queued job."""


@dataclass(frozen=True)
class ExtractionIngestResult:
    job_id: str
    state: str
    response_path: Path
    response_sha256: str
    receipt_path: Path
    response_status: InstallStatus
    receipt_status: InstallStatus
    semantic: SemanticCheckResult


@dataclass(frozen=True)
class ValidatorIngestResult:
    validation_id: str
    state: str
    accepted_candidates: int
    deferred_candidates: int
    response_path: Path
    response_sha256: str
    receipt_path: Path
    response_status: InstallStatus
    receipt_status: InstallStatus
    semantic: SemanticCheckResult


def ingest_extraction_response(
    jobs: JsonObject,
    *,
    job_id: str,
    response_path: Path,
    transcription_root: Path,
    output_root: Path,
) -> ExtractionIngestResult:
    """Validate and immutably store one blind response without editing the queue."""
    validate_extraction_jobs(jobs)
    validate_output_root(output_root, description="extraction output root")
    job = _find_job(jobs, job_id)

    try:
        response_bytes, response_snapshot = read_attested_bytes(response_path)
        response = loads_object(
            response_bytes.decode("utf-8"), description="extraction response"
        )
    except (StorageError, UnicodeDecodeError) as exc:
        raise ExtractionIngestError(str(exc)) from exc

    _validate_response_identity(response, job)
    bundle_path = safe_path(transcription_root, _required_string(job, "bundle_path"))
    try:
        semantic = check_semantic_artifact(
            bundle_path, response_path, root=transcription_root
        )
    except (SemanticCheckError, StorageError) as exc:
        raise ExtractionIngestError(str(exc)) from exc

    job_token = _job_token(job_id)
    response_directory = ensure_private_tree(output_root, f"responses/{job_token}")
    existing = sorted(response_directory.iterdir(), key=lambda path: path.name)
    expected_name = f"{response_snapshot.sha256}.json"
    unexpected = [path.name for path in existing if path.name != expected_name]
    if unexpected:
        raise ExtractionIngestError(
            f"job already has a different response: {job_id}: {unexpected[0]}"
        )

    stored_response = response_directory / expected_name
    response_install = install_immutable_bytes(
        stored_response,
        response_bytes,
        expected_sha256=response_snapshot.sha256,
    )

    receipt: JsonObject = {
        "schema_version": "1.0.0",
        "job_id": job_id,
        "state": "needs_validation",
        "model": _required_string(job, "model"),
        "pass": _required_string(job, "pass"),
        "catalog_key": _required_string(job, "catalog_key"),
        "bundle_id": _required_string(job, "bundle_id"),
        "bundle_sha256": _required_string(job, "bundle_sha256"),
        "response": {
            "path": stored_response.relative_to(output_root).as_posix(),
            "sha256": response_snapshot.sha256,
            "bytes": response_snapshot.bytes,
        },
        "semantic_check": {
            "candidates": semantic.candidates,
            "source_span_references": semantic.source_span_references,
            "qualifier_span_references": semantic.qualifier_span_references,
            "unique_span_references": semantic.unique_span_references,
            "allowed_span_ids": semantic.allowed_span_ids,
            "files_checked": semantic.files_checked,
        },
    }
    receipt_payload = canonical_bytes(receipt)
    receipt_directory = ensure_private_tree(output_root, f"receipts/{job_token}")
    receipt_path = receipt_directory / f"{response_snapshot.sha256}.json"
    receipt_install = install_immutable_bytes(receipt_path, receipt_payload)
    return ExtractionIngestResult(
        job_id=job_id,
        state="needs_validation",
        response_path=stored_response,
        response_sha256=response_snapshot.sha256,
        receipt_path=receipt_path,
        response_status=response_install.status,
        receipt_status=receipt_install.status,
        semantic=semantic,
    )


def ingest_validator_response(
    jobs: JsonObject,
    *,
    bundle_id: str,
    response_path: Path,
    transcription_root: Path,
    output_root: Path,
) -> ValidatorIngestResult:
    """Bind one independent validator decision to both stored blind responses."""
    validate_extraction_jobs(jobs)
    validate_output_root(output_root, description="extraction output root")
    pass_jobs = _jobs_for_bundle(jobs, bundle_id)
    pass_receipts = {
        label: _only_ingested_receipt(output_root, _required_string(job, "job_id"))
        for label, job in pass_jobs.items()
    }
    pass_response_sha256 = {
        label: _receipt_response_sha256(receipt) for label, receipt in pass_receipts.items()
    }
    pass_responses = {
        label: _load_stored_response(receipt, output_root=output_root)
        for label, receipt in pass_receipts.items()
    }

    try:
        response_bytes, response_snapshot = read_attested_bytes(response_path)
        response = loads_object(
            response_bytes.decode("utf-8"), description="validator response"
        )
    except (StorageError, UnicodeDecodeError) as exc:
        raise ExtractionIngestError(str(exc)) from exc

    bundle_job = pass_jobs["A"]
    _validate_validator_identity(
        response,
        bundle_job=bundle_job,
        pass_a_sha256=pass_response_sha256["A"],
        pass_b_sha256=pass_response_sha256["B"],
    )
    counts = _validator_counts(response)
    try:
        reconciliation = reconcile_validator(
            response,
            pass_a=pass_responses["A"],
            pass_b=pass_responses["B"],
        )
    except SemanticReconciliationError as exc:
        raise ExtractionIngestError(str(exc)) from exc
    bundle_path = safe_path(transcription_root, _required_string(bundle_job, "bundle_path"))
    try:
        semantic = check_semantic_artifact(
            bundle_path, response_path, root=transcription_root
        )
    except (SemanticCheckError, StorageError) as exc:
        raise ExtractionIngestError(str(exc)) from exc

    validation_identity: JsonObject = {
        "bundle_sha256": _required_string(bundle_job, "bundle_sha256"),
        "pass_a_sha256": pass_response_sha256["A"],
        "pass_b_sha256": pass_response_sha256["B"],
    }
    validation_token = sha256_json(validation_identity)
    validation_id = f"sha256:{validation_token}"
    response_directory = ensure_private_tree(
        output_root, f"validator-responses/{validation_token}"
    )
    expected_name = f"{response_snapshot.sha256}.json"
    unexpected = [
        path.name
        for path in sorted(response_directory.iterdir(), key=lambda path: path.name)
        if path.name != expected_name
    ]
    if unexpected:
        raise ExtractionIngestError(
            f"validation already has a different response: {validation_id}: {unexpected[0]}"
        )
    stored_response = response_directory / expected_name
    response_install = install_immutable_bytes(
        stored_response,
        response_bytes,
        expected_sha256=response_snapshot.sha256,
    )

    state = (
        "needs_review"
        if counts["deferred"] or reconciliation.unaccounted_candidate_ids
        else "accepted_candidate"
    )
    receipt: JsonObject = {
        "schema_version": "1.0.0",
        "validation_id": validation_id,
        "state": state,
        "bundle_id": bundle_id,
        "bundle_sha256": _required_string(bundle_job, "bundle_sha256"),
        "pass_a_job_id": _required_string(pass_jobs["A"], "job_id"),
        "pass_a_response_sha256": pass_response_sha256["A"],
        "pass_b_job_id": _required_string(pass_jobs["B"], "job_id"),
        "pass_b_response_sha256": pass_response_sha256["B"],
        "response": {
            "path": stored_response.relative_to(output_root).as_posix(),
            "sha256": response_snapshot.sha256,
            "bytes": response_snapshot.bytes,
        },
        "counts": counts,
        "reconciliation": reconciliation.as_json(),
        "semantic_check": {
            "candidates": semantic.candidates,
            "source_span_references": semantic.source_span_references,
            "qualifier_span_references": semantic.qualifier_span_references,
            "unique_span_references": semantic.unique_span_references,
            "allowed_span_ids": semantic.allowed_span_ids,
            "files_checked": semantic.files_checked,
        },
    }
    receipt_payload = canonical_bytes(receipt)
    receipt_directory = ensure_private_tree(
        output_root, f"validator-receipts/{validation_token}"
    )
    receipt_path = receipt_directory / f"{response_snapshot.sha256}.json"
    receipt_install = install_immutable_bytes(receipt_path, receipt_payload)
    return ValidatorIngestResult(
        validation_id=validation_id,
        state=state,
        accepted_candidates=counts["accepted"],
        deferred_candidates=counts["deferred"],
        response_path=stored_response,
        response_sha256=response_snapshot.sha256,
        receipt_path=receipt_path,
        response_status=response_install.status,
        receipt_status=receipt_install.status,
        semantic=semantic,
    )


def _find_job(jobs: JsonObject, job_id: str) -> JsonObject:
    raw_jobs = jobs.get("jobs")
    if not isinstance(raw_jobs, list):
        raise ExtractionIngestError("extraction queue has no jobs")
    matches = [
        cast(JsonObject, item)
        for item in raw_jobs
        if isinstance(item, dict) and item.get("job_id") == job_id
    ]
    if len(matches) != 1:
        raise ExtractionIngestError(f"job identity is not uniquely queued: {job_id}")
    return matches[0]


def _jobs_for_bundle(jobs: JsonObject, bundle_id: str) -> dict[str, JsonObject]:
    raw_jobs = jobs.get("jobs")
    if not isinstance(raw_jobs, list):
        raise ExtractionIngestError("extraction queue has no jobs")
    matches = [
        cast(JsonObject, item)
        for item in raw_jobs
        if isinstance(item, dict) and item.get("bundle_id") == bundle_id
    ]
    result = {
        _required_string(job, "pass"): job
        for job in matches
        if _required_string(job, "pass") in {"A", "B"}
    }
    if set(result) != {"A", "B"} or len(matches) != 2:
        raise ExtractionIngestError(
            f"bundle does not have exactly two queued passes: {bundle_id}"
        )
    return result


def _only_ingested_receipt(output_root: Path, job_id: str) -> JsonObject:
    directory = safe_path(output_root, f"receipts/{_job_token(job_id)}")
    try:
        entries = sorted(directory.iterdir(), key=lambda path: path.name)
    except OSError as exc:
        raise ExtractionIngestError(f"job has no ingested response: {job_id}") from exc
    if len(entries) != 1:
        raise ExtractionIngestError(
            f"job does not have exactly one ingested response: {job_id}"
        )
    receipt = load_ingested_receipt(entries[0])
    if receipt.get("job_id") != job_id:
        raise ExtractionIngestError(f"ingestion receipt job identity differs: {job_id}")
    return receipt


def _receipt_response_sha256(receipt: JsonObject) -> str:
    response = receipt.get("response")
    if not isinstance(response, dict):
        raise ExtractionIngestError("ingestion receipt has no response reference")
    return _required_string(cast(JsonObject, response), "sha256")


def _load_stored_response(receipt: JsonObject, *, output_root: Path) -> JsonObject:
    response = receipt.get("response")
    if not isinstance(response, dict):
        raise ExtractionIngestError("ingestion receipt has no response reference")
    reference = cast(JsonObject, response)
    try:
        payload, _ = read_attested_bytes(
            safe_path(output_root, _required_string(reference, "path")),
            expected_sha256=_required_string(reference, "sha256"),
            expected_bytes=cast(int, reference["bytes"]),
        )
        return loads_object(payload.decode("utf-8"), description="stored blind response")
    except (StorageError, UnicodeDecodeError, KeyError, TypeError) as exc:
        raise ExtractionIngestError("cannot load stored blind response") from exc


def _validate_response_identity(response: JsonObject, job: JsonObject) -> None:
    if _canonical_pass(response.get("pass")) != _required_string(job, "pass"):
        raise ExtractionIngestError("response differs from queued pass")
    if response.get("input_bundle_sha256") != _required_string(job, "bundle_sha256"):
        raise ExtractionIngestError("response differs from queued input_bundle_sha256")

    optional = {
        "bundle_id": _required_string(job, "bundle_id"),
        "catalog_key": _required_string(job, "catalog_key"),
        "source_sha256": _required_string(job, "source_sha256"),
        "model": _required_string(job, "model"),
    }
    for field, value in optional.items():
        if field in response and response[field] != value:
            raise ExtractionIngestError(f"response differs from queued {field}")

    schema_version = response.get("schema_version")
    if not isinstance(schema_version, str) or not schema_version:
        raise ExtractionIngestError("response has no schema_version")


def _job_token(job_id: str) -> str:
    prefix = "sha256:"
    if not job_id.startswith(prefix):
        raise ExtractionIngestError(f"invalid job identity: {job_id}")
    token = job_id.removeprefix(prefix)
    if len(token) != 64 or any(character not in "0123456789abcdef" for character in token):
        raise ExtractionIngestError(f"invalid job identity: {job_id}")
    return token


def _canonical_pass(value: object) -> str | None:
    aliases = {
        "A": "A",
        "B": "B",
        "luna-volume1-semantic-extraction-pass-a": "A",
        "luna-volume1-semantic-extraction-pass-b": "B",
    }
    return aliases.get(value) if isinstance(value, str) else None


def _validate_validator_identity(
    response: JsonObject,
    *,
    bundle_job: JsonObject,
    pass_a_sha256: str,
    pass_b_sha256: str,
) -> None:
    bundle_sha256 = _required_string(bundle_job, "bundle_sha256")
    if response.get("input_bundle_sha256") != bundle_sha256:
        raise ExtractionIngestError("validator differs from queued bundle SHA-256")
    provenance = response.get("provenance")
    if not isinstance(provenance, dict):
        raise ExtractionIngestError("validator has no provenance")
    expected = {
        "bundle_id": _required_string(bundle_job, "bundle_id"),
        "bundle_sha256": bundle_sha256,
        "pass_a_sha256": pass_a_sha256,
        "pass_b_sha256": pass_b_sha256,
    }
    for field, value in expected.items():
        if provenance.get(field) != value:
            raise ExtractionIngestError(f"validator provenance differs at {field}")


def _validator_counts(response: JsonObject) -> dict[str, int]:
    fields = {
        "accepted": "accepted_candidates",
        "merged": "merged_candidates",
        "rejected": "rejected_candidates",
        "deferred": "deferred_candidates",
    }
    counts: dict[str, int] = {}
    for label, field in fields.items():
        records = response.get(field)
        if not isinstance(records, list):
            raise ExtractionIngestError(f"validator has invalid {field}")
        counts[label] = len(records)
    if response.get("counts") != counts:
        raise ExtractionIngestError("validator counts are false")
    return counts


def _required_string(value: JsonObject, field: str) -> str:
    result = value.get(field)
    if not isinstance(result, str) or not result:
        raise ExtractionIngestError(f"invalid or missing {field}")
    return result


def load_ingested_receipt(path: Path) -> JsonObject:
    """Load a stored receipt after stable-file attestation."""
    try:
        snapshot = read_regular_snapshot(path)
        payload, _ = read_attested_bytes(
            path, expected_sha256=snapshot.sha256, expected_bytes=snapshot.bytes
        )
        return loads_object(payload.decode("utf-8"), description="ingestion receipt")
    except (StorageError, UnicodeDecodeError) as exc:
        raise ExtractionIngestError(str(exc)) from exc
