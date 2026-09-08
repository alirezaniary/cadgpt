"""Deterministic blind-pass job accounting for semantic extraction."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import cast

from cadgpt_regulations.errors import RegulationsError, StructureError
from cadgpt_regulations.jsonio import JsonObject, loads_object, sha256_json
from cadgpt_regulations.storage import StorageError, read_attested_bytes, safe_path
from cadgpt_regulations.structure import validate_structure

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
    b"uncertainty_codes,source_node_ids,formula_ids,table_ids,source_span_ids,"
    b"qualifier_span_ids,input_structural_bundle_sha256,unit_ids,abbreviation_ids"
).hexdigest()


class ExtractionJobError(RegulationsError):
    """Raised when a semantic extraction queue cannot be proven complete."""


def build_extraction_jobs(
    transcription: JsonObject,
    *,
    root: Path,
    model: str = DEFAULT_MODEL,
    structure: JsonObject | None = None,
    structure_root: Path | None = None,
) -> JsonObject:
    """Bind every evidence bundle to two blind jobs.

    When a validated T-0027 structure manifest is supplied, each job also carries
    the exact graph, node, formula, table, and page identities that define the
    semantic input.  The transcription bundle remains the immutable byte input.
    """
    if not model:
        raise ExtractionJobError("model identifier cannot be empty")
    raw_documents = transcription.get("documents")
    if not isinstance(raw_documents, list):
        raise ExtractionJobError("transcription has no document collection")
    structure_by_key: dict[str, JsonObject] = {}
    structure_sha256: str | None = None
    if structure is not None:
        if structure_root is None:
            raise ExtractionJobError("structure_root is required with structure")
        structure_sha256 = sha256_json(structure)
        try:
            validate_structure(
                structure,
                root=structure_root,
                transcription=transcription,
                transcription_root=root,
            )
        except (StructureError, KeyError, TypeError, ValueError) as exc:
            raise ExtractionJobError(f"structure validation failed: {exc}") from exc
        if structure.get("transcription_sha256") != sha256_json(transcription):
            raise ExtractionJobError("structure references a different transcription")
        raw_structure_documents = structure.get("documents")
        if not isinstance(raw_structure_documents, list):
            raise ExtractionJobError("structure has no document collection")
        for raw_reference in raw_structure_documents:
            if not isinstance(raw_reference, dict):
                raise ExtractionJobError("structure document reference is invalid")
            reference = cast(JsonObject, raw_reference)
            key = _required_string(reference, "catalog_key")
            if key in structure_by_key:
                raise ExtractionJobError(f"duplicate structure document: {key}")
            graph_path = _required_string(reference, "path")
            graph_sha = _required_sha256(reference, "sha256")
            try:
                graph_payload, _ = read_attested_bytes(
                    safe_path(structure_root, graph_path),
                    expected_sha256=graph_sha,
                    expected_bytes=_required_int(reference, "bytes"),
                )
            except StorageError as exc:
                raise ExtractionJobError(str(exc)) from exc
            graph = loads_object(graph_payload.decode("utf-8"), description="source graph")
            if graph.get("source_sha256") != reference.get("source_sha256"):
                raise ExtractionJobError(f"structure graph source differs: {key}")
            structure_by_key[key] = {
                "reference": reference,
                "graph": graph,
            }

    jobs: list[JsonObject] = []
    seen_bundles: set[str] = set()
    documents = [cast(JsonObject, document) for document in raw_documents]
    if structure is not None and set(structure_by_key) != {
        _required_string(document, "catalog_key") for document in documents
    }:
        raise ExtractionJobError("structure and transcription document sets differ")
    for document in documents:
        catalog_key = _required_string(document, "catalog_key")
        catalog_order = _required_int(document, "catalog_order")
        source_sha256 = _required_sha256(document, "source_sha256")
        structure_binding = _structure_binding(
            structure_by_key.get(catalog_key),
            source_sha256=source_sha256,
            structure_sha256=structure_sha256,
        )
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
            binding = _bundle_structure_binding(
                structure_binding,
                start_pdf_page=_required_int(reference, "start_pdf_page"),
                end_pdf_page=_required_int(reference, "end_pdf_page"),
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
                if binding is not None:
                    identity["structure_graph_sha256"] = binding["structure_graph_sha256"]
                    identity["structure_sha256"] = binding["structure_sha256"]
                    identity["structural_bundle_sha256"] = binding[
                        "structural_bundle_sha256"
                    ]
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
                        **(
                            {
                                "semantic_bundle_path": binding["structural_bundle_path"],
                                "semantic_bundle_sha256": binding[
                                    "structural_bundle_sha256"
                                ],
                            }
                            if binding is not None
                            else {}
                        ),
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
                        **({"structure": binding} if binding is not None else {}),
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
        "structure_sha256": structure_sha256,
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


def build_structured_extraction_jobs(
    transcription: JsonObject,
    *,
    root: Path,
    structure: JsonObject,
    structure_root: Path,
    model: str = DEFAULT_MODEL,
) -> JsonObject:
    """Build jobs with the canonical source structure as a mandatory gate."""
    return build_extraction_jobs(
        transcription,
        root=root,
        model=model,
        structure=structure,
        structure_root=structure_root,
    )


def validate_extraction_jobs(manifest: JsonObject) -> None:
    """Reject missing, duplicated, reordered, or identity-drifted blind jobs."""
    passes = manifest.get("blind_passes")
    if passes != list(BLIND_PASSES):
        raise ExtractionJobError("extraction queue must contain blind passes A and B")
    raw_jobs = manifest.get("jobs")
    if not isinstance(raw_jobs, list):
        raise ExtractionJobError("extraction queue has no jobs")
    jobs = [cast(JsonObject, job) for job in raw_jobs]
    if not jobs:
        raise ExtractionJobError("extraction queue has no jobs")
    for field in (
        "model",
        "prompt_version",
        "prompt_sha256",
        "response_schema_sha256",
    ):
        expected = jobs[0].get(field)
        if manifest.get(field) != expected:
            raise ExtractionJobError(
                f"extraction queue top-level {field} is false; identity drift"
            )
    structure_hashes = {
        cast(JsonObject, job["structure"]).get("structure_sha256")
        for job in jobs
        if isinstance(job.get("structure"), dict)
    }
    if structure_hashes and (
        len(structure_hashes) != 1
        or manifest.get("structure_sha256") not in structure_hashes
    ):
        raise ExtractionJobError("extraction queue structure hash is false")
    if not structure_hashes and manifest.get("structure_sha256") is not None:
        raise ExtractionJobError("extraction queue has an unexpected structure hash")
    identities: set[tuple[str, str]] = set()
    job_ids: set[str] = set()
    order: list[tuple[int, int, str]] = []
    bundle_ids: set[str] = set()
    bound_structure_hashes: set[str] = set()
    for job in jobs:
        if job.get("state") != "pending":
            raise ExtractionJobError("extraction job has an invalid state")
        for field in (
            "model",
            "prompt_version",
            "prompt_sha256",
            "response_schema_sha256",
        ):
            if job.get(field) != manifest.get(field):
                raise ExtractionJobError(
                    f"extraction job {field} differs from queue identity"
                )
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
        structure_binding = job.get("structure")
        if structure_binding is not None:
            if not isinstance(structure_binding, dict):
                raise ExtractionJobError("job structure binding is invalid")
            graph_sha256 = _required_sha256(
                cast(JsonObject, structure_binding), "structure_graph_sha256"
            )
            expected_identity["structure_graph_sha256"] = graph_sha256
            expected_identity["structure_sha256"] = _required_sha256(
                cast(JsonObject, structure_binding), "structure_sha256"
            )
            bound_structure_hashes.add(cast(str, expected_identity["structure_sha256"]))
            expected_identity["structural_bundle_sha256"] = _required_sha256(
                cast(JsonObject, structure_binding), "structural_bundle_sha256"
            )
            semantic_hash = _required_sha256(job, "semantic_bundle_sha256")
            if expected_identity["structural_bundle_sha256"] != semantic_hash:
                raise ExtractionJobError(
                    "semantic bundle hash differs from structure binding"
                )
            if _required_string(job, "semantic_bundle_path") != _required_string(
                cast(JsonObject, structure_binding), "structural_bundle_path"
            ):
                raise ExtractionJobError(
                    "semantic bundle path differs from structure binding"
                )
        if job_id != f"sha256:{sha256_json(expected_identity)}":
            raise ExtractionJobError(f"job identity drift: {job_id}")
        order.append(
            (
                _required_int(job, "catalog_order"),
                _required_int(job, "bundle_sequence"),
                pass_label,
            )
        )
    manifest_structure_sha256 = manifest.get("structure_sha256")
    if manifest_structure_sha256 is not None and (
        not isinstance(manifest_structure_sha256, str)
        or len(manifest_structure_sha256) != 64
        or any(
            character not in "0123456789abcdef" for character in manifest_structure_sha256
        )
    ):
        raise ExtractionJobError("extraction queue structure hash is invalid")
    if bound_structure_hashes:
        if manifest_structure_sha256 not in bound_structure_hashes:
            raise ExtractionJobError("extraction queue structure hash differs from jobs")
    elif manifest_structure_sha256 is not None:
        raise ExtractionJobError(
            "extraction queue declares structure without structured jobs"
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


def _structure_binding(
    value: JsonObject | None,
    *,
    source_sha256: str,
    structure_sha256: str | None,
) -> JsonObject | None:
    if value is None:
        if structure_sha256 is not None:
            raise ExtractionJobError("structure lacks a transcription document")
        return None
    reference = cast(JsonObject, value["reference"])
    graph = cast(JsonObject, value["graph"])
    if (
        reference.get("source_sha256") != source_sha256
        or graph.get("source_sha256") != source_sha256
    ):
        raise ExtractionJobError("structure source differs from transcription")
    pages = graph.get("pages")
    nodes = graph.get("nodes")
    if not isinstance(pages, list) or not isinstance(nodes, list):
        raise ExtractionJobError("structure graph has invalid pages or nodes")
    return {
        "structure_sha256": structure_sha256,
        "structure_graph_path": _required_string(reference, "path"),
        "structure_graph_sha256": _required_sha256(reference, "sha256"),
        "pages": pages,
        "nodes": nodes,
        "formulas": graph.get("formulas", []),
        "tables": graph.get("tables", []),
        "units": graph.get("units", []),
        "abbreviations": graph.get("abbreviations", []),
        "bundles": reference.get("bundles", []),
    }


def _bundle_structure_binding(
    value: JsonObject | None, *, start_pdf_page: int, end_pdf_page: int
) -> JsonObject | None:
    if value is None:
        return None
    pages = [
        page
        for page in cast(list[JsonObject], value["pages"])
        if start_pdf_page <= _required_int(page, "pdf_page") <= end_pdf_page
    ]
    page_numbers = {_required_int(page, "pdf_page") for page in pages}
    nodes = [
        node
        for node in cast(list[JsonObject], value["nodes"])
        if _required_int(node, "pdf_page") in page_numbers
    ]
    formulas = [
        item
        for item in cast(list[JsonObject], value["formulas"])
        if _required_int(item, "pdf_page") in page_numbers
    ]
    tables = [
        item
        for item in cast(list[JsonObject], value["tables"])
        if _required_int(item, "pdf_page") in page_numbers
    ]
    units = [
        item
        for item in cast(list[JsonObject], value["units"])
        if _required_int(item, "pdf_page") in page_numbers
    ]
    abbreviations = [
        item
        for item in cast(list[JsonObject], value["abbreviations"])
        if _required_int(item, "pdf_page") in page_numbers
    ]
    if not pages or sorted(page_numbers) != list(range(start_pdf_page, end_pdf_page + 1)):
        raise ExtractionJobError("structure does not cover every bundle page")
    structural_bundles = [
        item
        for item in cast(list[JsonObject], value.get("bundles", []))
        if item.get("start_pdf_page", 0) <= start_pdf_page
        and item.get("end_pdf_page", 0) >= end_pdf_page
    ]
    if not structural_bundles:
        raise ExtractionJobError(
            "structure has no canonical bundle for transcription bundle"
        )
    structural_bundle = structural_bundles[0]
    return {
        "structure_sha256": value["structure_sha256"],
        "structure_graph_path": value["structure_graph_path"],
        "structure_graph_sha256": value["structure_graph_sha256"],
        "page_ids": [_required_string(page, "page_id") for page in pages],
        "node_ids": [_required_string(node, "node_id") for node in nodes],
        "formula_ids": [_required_string(item, "formula_id") for item in formulas],
        "table_ids": [_required_string(item, "table_id") for item in tables],
        "unit_ids": [_required_string(item, "unit_id") for item in units],
        "abbreviation_ids": [
            _required_string(item, "abbreviation_id") for item in abbreviations
        ],
        "structural_bundle_path": _required_string(structural_bundle, "path"),
        "structural_bundle_sha256": _required_sha256(structural_bundle, "sha256"),
    }


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
    start = _required_int(reference, "start_pdf_page")
    end = _required_int(reference, "end_pdf_page")
    page_count = _required_int(reference, "page_count")
    if start < 1 or end < start or page_count != len(pages):
        raise ExtractionJobError("bundle page range or count is false")
    page_numbers: list[int] = []
    for page in pages:
        if not isinstance(page, dict) or not isinstance(page.get("span_ids"), list):
            raise ExtractionJobError("bundle page span IDs are invalid")
        if not all(isinstance(value, str) for value in page["span_ids"]):
            raise ExtractionJobError("bundle page contains a non-string span ID")
        page_number = page.get("pdf_page")
        if not isinstance(page_number, int) or page_number < 1:
            raise ExtractionJobError("bundle page has an invalid PDF page")
        page_numbers.append(page_number)
    if page_numbers != list(range(start, end + 1)):
        raise ExtractionJobError("bundle pages are not ordered and contiguous")


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
