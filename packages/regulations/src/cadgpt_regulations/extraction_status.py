"""Reconstruct resumable semantic extraction state from immutable receipts."""

from __future__ import annotations

from pathlib import Path
from typing import cast

from cadgpt_regulations.errors import RegulationsError
from cadgpt_regulations.extraction_ingest import load_ingested_receipt
from cadgpt_regulations.extraction_jobs import validate_extraction_jobs
from cadgpt_regulations.jsonio import JsonObject, sha256_json
from cadgpt_regulations.storage import (
    StorageError,
    read_attested_bytes,
    safe_path,
    validate_output_root,
)


class ExtractionStatusError(RegulationsError):
    """Raised when stored extraction state is incomplete or contradictory."""


def build_extraction_status(jobs: JsonObject, *, output_root: Path) -> JsonObject:
    """Account for every queued pass and bundle from immutable ingest receipts."""
    validate_extraction_jobs(jobs)
    validate_output_root(output_root, description="extraction output root")
    raw_jobs = jobs.get("jobs")
    assert isinstance(raw_jobs, list)
    queue = [cast(JsonObject, value) for value in raw_jobs]

    job_records: list[JsonObject] = []
    receipt_by_job: dict[str, JsonObject] = {}
    for job in queue:
        job_id = _required_string(job, "job_id")
        receipt = _optional_receipt(
            output_root, f"receipts/{_sha256_token(job_id)}", description=job_id
        )
        if receipt is None:
            job_records.append(_job_status(job, state="pending", receipt=None))
            continue
        _validate_job_receipt(receipt, job=job, output_root=output_root)
        receipt_by_job[job_id] = receipt
        job_records.append(
            _job_status(job, state=_required_string(receipt, "state"), receipt=receipt)
        )

    bundle_records: list[JsonObject] = []
    by_bundle: dict[str, dict[str, JsonObject]] = {}
    for job in queue:
        by_bundle.setdefault(_required_string(job, "bundle_id"), {})[
            _required_string(job, "pass")
        ] = job
    for bundle_id, pass_jobs in by_bundle.items():
        bundle_records.append(
            _bundle_status(
                bundle_id,
                pass_jobs=pass_jobs,
                receipt_by_job=receipt_by_job,
                output_root=output_root,
            )
        )

    return {
        "schema_version": "1.0.0",
        "jobs_sha256": sha256_json(jobs),
        "jobs": job_records,
        "bundles": bundle_records,
        "summary": {
            "documents": len({_required_string(job, "catalog_key") for job in queue}),
            "jobs": len(job_records),
            "jobs_pending": sum(record["state"] == "pending" for record in job_records),
            "jobs_ingested": sum(record["state"] != "pending" for record in job_records),
            "bundles": len(bundle_records),
            "bundles_pending": sum(
                record["state"] == "pending" for record in bundle_records
            ),
            "bundles_needs_validation": sum(
                record["state"] == "needs_validation" for record in bundle_records
            ),
            "bundles_accepted": sum(
                record["state"] == "accepted_candidate" for record in bundle_records
            ),
            "bundles_needs_review": sum(
                record["state"] == "needs_review" for record in bundle_records
            ),
        },
    }


def _bundle_status(
    bundle_id: str,
    *,
    pass_jobs: dict[str, JsonObject],
    receipt_by_job: dict[str, JsonObject],
    output_root: Path,
) -> JsonObject:
    pass_a_job = pass_jobs["A"]
    pass_b_job = pass_jobs["B"]
    pass_a_id = _required_string(pass_a_job, "job_id")
    pass_b_id = _required_string(pass_b_job, "job_id")
    pass_a_receipt = receipt_by_job.get(pass_a_id)
    pass_b_receipt = receipt_by_job.get(pass_b_id)
    base: JsonObject = {
        "bundle_id": bundle_id,
        "catalog_key": _required_string(pass_a_job, "catalog_key"),
        "bundle_sequence": pass_a_job["bundle_sequence"],
        "start_pdf_page": pass_a_job["start_pdf_page"],
        "end_pdf_page": pass_a_job["end_pdf_page"],
        "pass_a_job_id": pass_a_id,
        "pass_b_job_id": pass_b_id,
    }
    if pass_a_receipt is None or pass_b_receipt is None:
        return {**base, "state": "pending", "validation": None}

    pass_a_sha256 = _receipt_response_sha256(pass_a_receipt)
    pass_b_sha256 = _receipt_response_sha256(pass_b_receipt)
    validation_token = sha256_json(
        {
            "bundle_sha256": _required_string(pass_a_job, "bundle_sha256"),
            "pass_a_sha256": pass_a_sha256,
            "pass_b_sha256": pass_b_sha256,
        }
    )
    validation = _optional_receipt(
        output_root,
        f"validator-receipts/{validation_token}",
        description=bundle_id,
    )
    if validation is None:
        return {**base, "state": "needs_validation", "validation": None}
    _validate_validator_receipt(
        validation,
        bundle_id=bundle_id,
        pass_a_sha256=pass_a_sha256,
        pass_b_sha256=pass_b_sha256,
        output_root=output_root,
    )
    return {
        **base,
        "state": _required_string(validation, "state"),
        "validation": {
            "validation_id": _required_string(validation, "validation_id"),
            "response_sha256": _receipt_response_sha256(validation),
            "counts": validation["counts"],
        },
    }


def _job_status(job: JsonObject, *, state: str, receipt: JsonObject | None) -> JsonObject:
    return {
        "job_id": _required_string(job, "job_id"),
        "bundle_id": _required_string(job, "bundle_id"),
        "pass": _required_string(job, "pass"),
        "state": state,
        "response_sha256": (
            _receipt_response_sha256(receipt) if receipt is not None else None
        ),
    }


def _optional_receipt(
    output_root: Path, relative_directory: str, *, description: str
) -> JsonObject | None:
    directory = safe_path(output_root, relative_directory)
    try:
        entries = sorted(directory.iterdir(), key=lambda path: path.name)
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise ExtractionStatusError(f"cannot inspect receipt for {description}") from exc
    if len(entries) != 1:
        raise ExtractionStatusError(
            f"receipt cardinality is not one for {description}: {len(entries)}"
        )
    return load_ingested_receipt(entries[0])


def _validate_job_receipt(
    receipt: JsonObject, *, job: JsonObject, output_root: Path
) -> None:
    expected = {
        "job_id": _required_string(job, "job_id"),
        "bundle_id": _required_string(job, "bundle_id"),
        "bundle_sha256": _required_string(job, "bundle_sha256"),
        "pass": _required_string(job, "pass"),
        "model": _required_string(job, "model"),
    }
    for field, value in expected.items():
        if receipt.get(field) != value:
            raise ExtractionStatusError(f"job receipt differs at {field}: {value}")
    _validate_response_reference(receipt, output_root=output_root)


def _validate_validator_receipt(
    receipt: JsonObject,
    *,
    bundle_id: str,
    pass_a_sha256: str,
    pass_b_sha256: str,
    output_root: Path,
) -> None:
    expected = {
        "bundle_id": bundle_id,
        "pass_a_response_sha256": pass_a_sha256,
        "pass_b_response_sha256": pass_b_sha256,
    }
    for field, value in expected.items():
        if receipt.get(field) != value:
            raise ExtractionStatusError(f"validator receipt differs at {field}: {value}")
    if receipt.get("state") not in {"accepted_candidate", "needs_review"}:
        raise ExtractionStatusError(f"validator receipt has invalid state: {bundle_id}")
    _validate_response_reference(receipt, output_root=output_root)


def _validate_response_reference(receipt: JsonObject, *, output_root: Path) -> None:
    response = receipt.get("response")
    if not isinstance(response, dict):
        raise ExtractionStatusError("receipt has no response reference")
    reference = cast(JsonObject, response)
    try:
        read_attested_bytes(
            safe_path(output_root, _required_string(reference, "path")),
            expected_sha256=_required_string(reference, "sha256"),
            expected_bytes=_required_int(reference, "bytes"),
        )
    except StorageError as exc:
        raise ExtractionStatusError(str(exc)) from exc


def _receipt_response_sha256(receipt: JsonObject) -> str:
    response = receipt.get("response")
    if not isinstance(response, dict):
        raise ExtractionStatusError("receipt has no response reference")
    return _required_string(cast(JsonObject, response), "sha256")


def _sha256_token(value: str) -> str:
    if not value.startswith("sha256:"):
        raise ExtractionStatusError(f"invalid SHA-256 identity: {value}")
    token = value.removeprefix("sha256:")
    if len(token) != 64 or any(character not in "0123456789abcdef" for character in token):
        raise ExtractionStatusError(f"invalid SHA-256 identity: {value}")
    return token


def _required_string(value: JsonObject, field: str) -> str:
    result = value.get(field)
    if not isinstance(result, str) or not result:
        raise ExtractionStatusError(f"invalid or missing {field}")
    return result


def _required_int(value: JsonObject, field: str) -> int:
    result = value.get(field)
    if not isinstance(result, int) or result < 0:
        raise ExtractionStatusError(f"invalid or missing {field}")
    return result
