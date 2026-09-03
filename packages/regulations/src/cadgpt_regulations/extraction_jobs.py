"""Deterministic blind-pass job accounting for semantic extraction."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import cast

from cadgpt_regulations.errors import RegulationsError
from cadgpt_regulations.jsonio import JsonObject, loads_object, sha256_json
from cadgpt_regulations.storage import StorageError, read_attested_bytes, safe_path

DEFAULT_MODEL = "gpt-5.6-luna"
BLIND_PASSES = ("A", "B")
PROMPT_VERSION = "semantic-extraction-1.0.0"
PROMPT_SHA256 = hashlib.sha256(
    b"Extract only source-supported atomic semantics from the supplied bundle; "
    b"cite allowed source spans; preserve unknowns; never invent quotations, "
    b"formula tokens, table values, conditions, exceptions, or references."
).hexdigest()
RESPONSE_SCHEMA_SHA256 = hashlib.sha256(
    b"semantic-candidates-1.0.0:candidate_id,kind,structural_label_as_seen,"
    b"subject,predicate,modality,comparator,value,printed_unit,conditions,"
    b"exceptions,references,formula_or_table_notes,english_gloss,"
    b"uncertainty_codes,source_span_ids,qualifier_span_ids"
).hexdigest()


class ExtractionJobError(RegulationsError):
    """Raised when a semantic extraction queue cannot be proven complete."""


def build_extraction_jobs(
    transcription: JsonObject,
    *,
    root: Path,
    model: str = DEFAULT_MODEL,
) -> JsonObject:
    """Bind every transcription bundle to two independent model jobs."""
    if not model:
        raise ExtractionJobError("model identifier cannot be empty")
    raw_documents = transcription.get("documents")
    if not isinstance(raw_documents, list):
        raise ExtractionJobError("transcription has no document collection")

    jobs: list[JsonObject] = []
    seen_bundles: set[str] = set()
    documents = [cast(JsonObject, document) for document in raw_documents]
    for document in documents:
        catalog_key = _required_string(document, "catalog_key")
        catalog_order = _required_int(document, "catalog_order")
        source_sha256 = _required_sha256(document, "source_sha256")
        raw_bundles = document.get("bundles")
        if not isinstance(raw_bundles, list):
            raise ExtractionJobError(f"document {catalog_key} has no bundles")
        for raw_reference in raw_bundles:
            if not isinstance(raw_reference, dict):
                raise ExtractionJobError(f"document {catalog_key} has an invalid bundle")
            reference = cast(JsonObject, raw_reference)
            bundle_id = _required_string(reference, "bundle_id")
            if bundle_id in seen_bundles:
                raise ExtractionJobError(f"duplicate bundle identity: {bundle_id}")
            seen_bundles.add(bundle_id)
            bundle_sha256 = _required_sha256(reference, "sha256")
            bundle_path = _required_string(reference, "path")
            try:
                payload, _ = read_attested_bytes(
                    safe_path(root, bundle_path), expected_sha256=bundle_sha256
                )
            except StorageError as exc:
                raise ExtractionJobError(str(exc)) from exc
            bundle = loads_object(payload.decode("utf-8"), description="model bundle")
            _validate_bundle_reference(
                bundle,
                reference=reference,
                catalog_key=catalog_key,
                source_sha256=source_sha256,
            )
            allowed_span_count = 0
            for page in cast(list[JsonObject], bundle["pages"]):
                allowed_span_count += len(cast(list[str], page["span_ids"]))
            for pass_label in BLIND_PASSES:
                identity: JsonObject = {
                    "bundle_sha256": bundle_sha256,
                    "model": model,
                    "pass": pass_label,
                    "prompt_sha256": PROMPT_SHA256,
                    "response_schema_sha256": RESPONSE_SCHEMA_SHA256,
                }
                jobs.append(
                    {
                        "job_id": f"sha256:{sha256_json(identity)}",
                        "state": "pending",
                        "pass": pass_label,
                        "model": model,
                        "catalog_key": catalog_key,
                        "catalog_order": catalog_order,
                        "source_sha256": source_sha256,
                        "bundle_id": bundle_id,
                        "bundle_sequence": _required_int(reference, "sequence"),
                        "bundle_path": bundle_path,
                        "bundle_sha256": bundle_sha256,
                        "start_pdf_page": _required_int(reference, "start_pdf_page"),
                        "end_pdf_page": _required_int(reference, "end_pdf_page"),
                        "page_count": _required_int(reference, "page_count"),
                        "allowed_span_count": allowed_span_count,
                        "continuation_edge_count": len(
                            cast(list[JsonObject], bundle["continuation_edges"])
                        ),
                        "prompt_version": PROMPT_VERSION,
                        "prompt_sha256": PROMPT_SHA256,
                        "response_schema_sha256": RESPONSE_SCHEMA_SHA256,
                    }
                )

    manifest: JsonObject = {
        "schema_version": "1.0.0",
        "transcription_sha256": sha256_json(transcription),
        "model": model,
        "blind_passes": list(BLIND_PASSES),
        "prompt_version": PROMPT_VERSION,
        "prompt_sha256": PROMPT_SHA256,
        "response_schema_sha256": RESPONSE_SCHEMA_SHA256,
        "jobs": jobs,
        "summary": {
            "documents": len(documents),
            "bundles": len(seen_bundles),
            "jobs": len(jobs),
            "pending": len(jobs),
        },
    }
    validate_extraction_jobs(manifest)
    return manifest


def validate_extraction_jobs(manifest: JsonObject) -> None:
    """Reject missing, duplicated, reordered, or identity-drifted blind jobs."""
    passes = manifest.get("blind_passes")
    if passes != list(BLIND_PASSES):
        raise ExtractionJobError("extraction queue must contain blind passes A and B")
    raw_jobs = manifest.get("jobs")
    if not isinstance(raw_jobs, list):
        raise ExtractionJobError("extraction queue has no jobs")
    jobs = [cast(JsonObject, job) for job in raw_jobs]
    identities: set[tuple[str, str]] = set()
    job_ids: set[str] = set()
    order: list[tuple[int, int, str]] = []
    bundle_ids: set[str] = set()
    for job in jobs:
        bundle_id = _required_string(job, "bundle_id")
        pass_label = _required_string(job, "pass")
        if pass_label not in BLIND_PASSES:
            raise ExtractionJobError(f"unknown blind pass: {pass_label}")
        identity = (bundle_id, pass_label)
        if identity in identities:
            raise ExtractionJobError(f"duplicate extraction job: {identity}")
        identities.add(identity)
        bundle_ids.add(bundle_id)
        job_id = _required_string(job, "job_id")
        if job_id in job_ids:
            raise ExtractionJobError(f"duplicate extraction job ID: {job_id}")
        job_ids.add(job_id)
        expected_identity: JsonObject = {
            "bundle_sha256": _required_sha256(job, "bundle_sha256"),
            "model": _required_string(job, "model"),
            "pass": pass_label,
            "prompt_sha256": _required_sha256(job, "prompt_sha256"),
            "response_schema_sha256": _required_sha256(job, "response_schema_sha256"),
        }
        if job_id != f"sha256:{sha256_json(expected_identity)}":
            raise ExtractionJobError(f"job identity drift: {job_id}")
        order.append(
            (
                _required_int(job, "catalog_order"),
                _required_int(job, "bundle_sequence"),
                pass_label,
            )
        )
    if order != sorted(order):
        raise ExtractionJobError("extraction jobs are reordered")
    for bundle_id in bundle_ids:
        observed = {
            pass_label for candidate, pass_label in identities if candidate == bundle_id
        }
        if observed != set(BLIND_PASSES):
            raise ExtractionJobError(f"bundle lacks both blind passes: {bundle_id}")
    summary = manifest.get("summary")
    expected_summary = {
        "documents": len({_required_string(job, "catalog_key") for job in jobs}),
        "bundles": len(bundle_ids),
        "jobs": len(jobs),
        "pending": sum(job.get("state") == "pending" for job in jobs),
    }
    if summary != expected_summary:
        raise ExtractionJobError("extraction queue summary is false")


def _validate_bundle_reference(
    bundle: JsonObject,
    *,
    reference: JsonObject,
    catalog_key: str,
    source_sha256: str,
) -> None:
    copied = {
        "bundle_id": reference["bundle_id"],
        "catalog_key": catalog_key,
        "source_sha256": source_sha256,
        "sequence": reference["sequence"],
        "start_pdf_page": reference["start_pdf_page"],
        "end_pdf_page": reference["end_pdf_page"],
        "page_count": reference["page_count"],
        "input_bytes": reference["input_bytes"],
    }
    for field, expected in copied.items():
        if bundle.get(field) != expected:
            raise ExtractionJobError(f"bundle reference differs at {field}")
    pages = bundle.get("pages")
    edges = bundle.get("continuation_edges")
    if not isinstance(pages, list) or not isinstance(edges, list):
        raise ExtractionJobError("bundle pages or continuation edges are invalid")
    for page in pages:
        if not isinstance(page, dict) or not isinstance(page.get("span_ids"), list):
            raise ExtractionJobError("bundle page span IDs are invalid")
        if not all(isinstance(value, str) for value in page["span_ids"]):
            raise ExtractionJobError("bundle page contains a non-string span ID")


def _required_string(value: JsonObject, field: str) -> str:
    result = value.get(field)
    if not isinstance(result, str) or not result:
        raise ExtractionJobError(f"invalid or missing {field}")
    return result


def _required_int(value: JsonObject, field: str) -> int:
    result = value.get(field)
    if not isinstance(result, int) or result < 0:
        raise ExtractionJobError(f"invalid or missing {field}")
    return result


def _required_sha256(value: JsonObject, field: str) -> str:
    result = _required_string(value, field)
    if len(result) != 64 or any(
        character not in "0123456789abcdef" for character in result
    ):
        raise ExtractionJobError(f"invalid SHA-256 at {field}")
    return result
