"""Publish validated semantic records without mixing uncertain data into engine rules."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from cadgpt_regulations.acquisition import validate_acquisition_receipt
from cadgpt_regulations.catalog import validate_catalog
from cadgpt_regulations.errors import AcquisitionError, RegulationsError
from cadgpt_regulations.extraction_ingest import load_ingested_receipt
from cadgpt_regulations.extraction_jobs import validate_extraction_jobs
from cadgpt_regulations.extraction_status import build_extraction_status
from cadgpt_regulations.jsonio import (
    JsonObject,
    canonical_bytes,
    loads_object,
    sha256_json,
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
    safe_path,
    validate_output_root,
)


class SemanticPublishError(RegulationsError):
    """Raised when validated records cannot be published without data loss."""


@dataclass(frozen=True)
class SemanticPublicationRun:
    manifest: JsonObject
    manifest_path: Path
    run_directory: Path
    files_installed: int
    files_reused: int


@dataclass(frozen=True)
class _Payload:
    name: str
    data: bytes
    records: int

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.data).hexdigest()


def build_semantic_publication(
    catalog: JsonObject,
    jobs: JsonObject,
    structure: JsonObject,
    *,
    acquisition: JsonObject | None = None,
    acquisition_root: Path | None = None,
    extraction_root: Path,
    structure_root: Path,
    output_root: Path,
) -> SemanticPublicationRun:
    """Create one immutable publication run from the currently validated bundles."""
    validate_catalog(catalog)
    validate_extraction_jobs(jobs)
    validate_output_root(extraction_root, description="extraction root")
    validate_output_root(structure_root, description="structure root")
    validate_output_root(output_root, description="publication output root")
    if (acquisition is None) != (acquisition_root is None):
        raise SemanticPublishError(
            "acquisition receipt and acquisition root must be supplied together"
        )
    if acquisition is not None and acquisition_root is not None:
        try:
            validate_acquisition_receipt(
                acquisition,
                catalog=catalog,
                root=acquisition_root,
            )
        except AcquisitionError as exc:
            raise SemanticPublishError(str(exc)) from exc

    status = build_extraction_status(jobs, output_root=extraction_root)
    artifacts = _catalog_artifacts(catalog)
    artifacts_by_key = {
        _required_string(artifact, "catalog_key"): artifact for artifact in artifacts
    }
    documents = _documents_payload(catalog, artifacts, acquisition=acquisition)

    rules: list[JsonObject] = []
    rejected: list[JsonObject] = []
    deferred: list[JsonObject] = []
    validated_bundles: list[JsonObject] = []
    bundle_records = cast(list[JsonObject], status["bundles"])
    for bundle in bundle_records:
        if bundle["state"] not in {"accepted_candidate", "needs_review"}:
            continue
        bundle_rules, bundle_rejected, bundle_deferred, validation_reference = (
            _publish_validated_bundle(
                bundle,
                extraction_root=extraction_root,
                artifacts_by_key=artifacts_by_key,
            )
        )
        rules.extend(bundle_rules)
        rejected.extend(bundle_rejected)
        deferred.extend(bundle_deferred)
        validated_bundles.append(validation_reference)

    formulas, tables, units, structural_deferred = _structure_records(
        structure,
        structure_root=structure_root,
        artifacts_by_key=artifacts_by_key,
    )
    deferred.extend(structural_deferred)

    payloads = [
        _Payload("formats.json", canonical_bytes(_formats_payload()), 1),
        _Payload("documents.json", canonical_bytes(documents), len(artifacts)),
        _Payload("queue.json", canonical_bytes(status), len(bundle_records)),
        _Payload("rules.jsonl", _jsonl_bytes(rules), len(rules)),
        _Payload("formulas.jsonl", _jsonl_bytes(formulas), len(formulas)),
        _Payload("tables.jsonl", _jsonl_bytes(tables), len(tables)),
        _Payload("units.jsonl", _jsonl_bytes(units), len(units)),
        _Payload("rejected.jsonl", _jsonl_bytes(rejected), len(rejected)),
        _Payload("deferred.jsonl", _jsonl_bytes(deferred), len(deferred)),
    ]
    status_summary = cast(JsonObject, status["summary"])
    complete = (
        status_summary["jobs_ingested"] == status_summary["jobs"]
        and status_summary["bundles_pending"] == 0
        and status_summary["bundles_needs_validation"] == 0
    )
    manifest: JsonObject = {
        "schema_version": "1.0.0",
        "complete": complete,
        "inputs": {
            "catalog_sha256": sha256_json(catalog),
            "acquisition_sha256": (
                None if acquisition is None else sha256_json(acquisition)
            ),
            "jobs_sha256": sha256_json(jobs),
            "structure_sha256": sha256_json(structure),
            "extraction_status_sha256": sha256_json(status),
        },
        "files": [
            {
                "path": payload.name,
                "sha256": payload.sha256,
                "bytes": len(payload.data),
                "records": payload.records,
            }
            for payload in payloads
        ],
        "validated_bundles": validated_bundles,
        "summary": {
            "documents": len(artifacts),
            "documents_internet_verified": sum(
                1
                for document in cast(list[JsonObject], documents["documents"])
                if cast(JsonObject, document["internet_verification"])["status"]
                == "transport_verified"
            ),
            "bundles_total": status_summary["bundles"],
            "bundles_validated": len(validated_bundles),
            "bundles_pending": status_summary["bundles_pending"],
            "bundles_needs_validation": status_summary["bundles_needs_validation"],
            "rules": len(rules),
            "formulas": len(formulas),
            "tables": len(tables),
            "units": len(units),
            "rejected": len(rejected),
            "deferred": len(deferred),
        },
    }
    run_token = sha256_json(manifest)
    run_directory = ensure_private_tree(output_root, f"publications/{run_token}")
    installed = 0
    reused = 0
    for payload in payloads:
        result = install_immutable_bytes(
            run_directory / payload.name,
            payload.data,
            expected_sha256=payload.sha256,
        )
        installed += result.status is InstallStatus.INSTALLED
        reused += result.status is InstallStatus.REUSED
    manifest_path = run_directory / "manifest.json"
    result = install_immutable_bytes(manifest_path, canonical_bytes(manifest))
    installed += result.status is InstallStatus.INSTALLED
    reused += result.status is InstallStatus.REUSED
    validate_semantic_publication(manifest, root=run_directory)
    return SemanticPublicationRun(
        manifest=manifest,
        manifest_path=manifest_path,
        run_directory=run_directory,
        files_installed=installed,
        files_reused=reused,
    )


def validate_semantic_publication(manifest: JsonObject, *, root: Path) -> None:
    """Re-attest every output and enforce the accepted/deferred boundary."""
    validate_output_root(root, description="publication root")
    if manifest.get("schema_version") != "1.0.0":
        raise SemanticPublishError("unsupported semantic publication schema")
    raw_files = manifest.get("files")
    if not isinstance(raw_files, list) or not raw_files:
        raise SemanticPublishError("semantic publication has no file inventory")
    files = [cast(JsonObject, item) for item in raw_files if isinstance(item, dict)]
    if len(files) != len(raw_files):
        raise SemanticPublishError("semantic publication has an invalid file inventory")
    names = [_required_string(item, "path") for item in files]
    if len(set(names)) != len(names):
        raise SemanticPublishError("semantic publication repeats an output path")
    expected_names = {
        "formats.json",
        "documents.json",
        "queue.json",
        "rules.jsonl",
        "formulas.jsonl",
        "tables.jsonl",
        "units.jsonl",
        "rejected.jsonl",
        "deferred.jsonl",
    }
    if set(names) != expected_names:
        raise SemanticPublishError("semantic publication file inventory is incomplete")
    for reference in files:
        path = safe_path(root, _required_string(reference, "path"))
        try:
            payload, _ = read_attested_bytes(
                path,
                expected_sha256=_required_sha256(reference, "sha256"),
                expected_bytes=_required_int(reference, "bytes"),
            )
        except StorageError as exc:
            raise SemanticPublishError(str(exc)) from exc
        expected_records = _required_int(reference, "records")
        if path.suffix == ".jsonl":
            records = _load_jsonl(payload, description=path.name)
            if len(records) != expected_records:
                raise SemanticPublishError(f"record count differs for {path.name}")
            record_ids = [_required_string(record, "record_id") for record in records]
            if len(set(record_ids)) != len(record_ids):
                raise SemanticPublishError(f"duplicate record identity in {path.name}")
            if path.name == "rules.jsonl":
                for record in records:
                    candidate = record.get("candidate")
                    if not isinstance(candidate, dict):
                        raise SemanticPublishError("published rule has no candidate")
                    uncertainty = candidate.get("uncertainty_codes")
                    if uncertainty != []:
                        raise SemanticPublishError("uncertain candidate leaked into rules")
                    if _candidate_quality_codes(cast(JsonObject, candidate)):
                        raise SemanticPublishError(
                            "low-quality candidate leaked into rules"
                        )
            if path.name == "deferred.jsonl" and any(
                not isinstance(record.get("reason_code"), str) for record in records
            ):
                raise SemanticPublishError("deferred record has no reason code")
        elif path.name in {"formats.json", "documents.json", "queue.json"}:
            decoded = loads_object(payload.decode("utf-8"), description=path.name)
            if path.name == "documents.json":
                _validate_documents_payload(decoded)
    summary = manifest.get("summary")
    if not isinstance(summary, dict):
        raise SemanticPublishError("semantic publication has no summary")
    summary_object = cast(JsonObject, summary)
    references_by_name = {
        _required_string(reference, "path"): reference for reference in files
    }
    count_fields = {
        "documents.json": "documents",
        "queue.json": "bundles_total",
        "rules.jsonl": "rules",
        "formulas.jsonl": "formulas",
        "tables.jsonl": "tables",
        "units.jsonl": "units",
        "rejected.jsonl": "rejected",
        "deferred.jsonl": "deferred",
    }
    for filename, field in count_fields.items():
        if references_by_name[filename]["records"] != summary_object.get(field):
            raise SemanticPublishError(f"summary differs at {field}")
    documents_reference = references_by_name["documents.json"]
    documents_payload, _ = read_attested_bytes(
        safe_path(root, _required_string(documents_reference, "path")),
        expected_sha256=_required_sha256(documents_reference, "sha256"),
        expected_bytes=_required_int(documents_reference, "bytes"),
    )
    decoded_documents = loads_object(
        documents_payload.decode("utf-8"), description="documents.json"
    )
    verified_documents = sum(
        1
        for document in _records(decoded_documents, "documents")
        if cast(JsonObject, document["internet_verification"])["status"]
        == "transport_verified"
    )
    if summary_object.get("documents_internet_verified") != verified_documents:
        raise SemanticPublishError("internet-verified document summary differs")
    raw_validated = manifest.get("validated_bundles")
    if not isinstance(raw_validated, list) or len(raw_validated) != summary_object.get(
        "bundles_validated"
    ):
        raise SemanticPublishError("validated bundle summary differs")
    if not isinstance(manifest.get("complete"), bool):
        raise SemanticPublishError("semantic publication complete flag is invalid")


def _documents_payload(
    catalog: JsonObject,
    artifacts: list[JsonObject],
    *,
    acquisition: JsonObject | None,
) -> JsonObject:
    relationships: list[JsonObject] = []
    for artifact in artifacts:
        source = _required_string(artifact, "catalog_key")
        for relation in cast(list[JsonObject], artifact["relationships"]):
            relationships.append({"source": source, **relation})
    acquisition_by_key = (
        {}
        if acquisition is None
        else {
            _required_string(result, "catalog_key"): result
            for result in _records(acquisition, "artifacts")
        }
    )
    documents = [
        {
            **artifact,
            "internet_verification": _internet_verification(
                artifact,
                acquisition_by_key.get(_required_string(artifact, "catalog_key")),
            ),
        }
        for artifact in artifacts
    ]
    return {
        "schema_version": "1.0.0",
        "catalog_id": catalog.get("catalog_id"),
        "documents": documents,
        "relationships": relationships,
    }


def _internet_verification(
    artifact: JsonObject, acquisition_result: JsonObject | None
) -> JsonObject:
    if acquisition_result is None:
        return {
            "status": "catalog_only",
            "official_urls": artifact["source_urls"],
            "official_source_sha256": artifact["expected_sha256"],
        }
    if acquisition_result.get("state") != "ready":
        return {
            "status": "unverified",
            "official_urls": artifact["source_urls"],
            "official_source_sha256": artifact["expected_sha256"],
            "error": acquisition_result.get("error"),
        }
    transport = acquisition_result.get("initial_transport")
    if not isinstance(transport, dict):
        raise SemanticPublishError(
            "ready acquisition result lacks initial transport evidence: "
            f"{artifact['catalog_key']}"
        )
    attestation = cast(JsonObject, transport)
    return {
        "status": "transport_verified",
        "official_urls": artifact["source_urls"],
        "requested_url": attestation["requested_url"],
        "resolved_url": attestation["resolved_url"],
        "redirect_chain": attestation["redirect_chain"],
        "http_status": attestation["http_status"],
        "attempts": attestation["attempts"],
        "sha256": attestation["sha256"],
        "bytes": attestation["bytes"],
        "detected_media_type": attestation["detected_media_type"],
        "pdf_page_count": attestation["pdf_page_count"],
    }


def _validate_documents_payload(payload: JsonObject) -> None:
    documents = _records(payload, "documents")
    catalog_keys: set[str] = set()
    for document in documents:
        catalog_key = _required_string(document, "catalog_key")
        if catalog_key in catalog_keys:
            raise SemanticPublishError(f"duplicate published document: {catalog_key}")
        catalog_keys.add(catalog_key)
        verification = document.get("internet_verification")
        if not isinstance(verification, dict):
            raise SemanticPublishError(
                f"published document lacks internet verification: {catalog_key}"
            )
        evidence = cast(JsonObject, verification)
        status = evidence.get("status")
        if status not in {"catalog_only", "transport_verified", "unverified"}:
            raise SemanticPublishError(
                f"published document has invalid internet verification: {catalog_key}"
            )
        if status == "transport_verified":
            http_status = evidence.get("http_status")
            if not isinstance(http_status, int) or not 200 <= http_status < 300:
                raise SemanticPublishError(
                    f"published document has invalid HTTP attestation: {catalog_key}"
                )
            if evidence.get("sha256") != document.get("expected_sha256"):
                raise SemanticPublishError(
                    f"published internet evidence differs from source hash: {catalog_key}"
                )
            if evidence.get("bytes") != document.get("expected_bytes"):
                raise SemanticPublishError(
                    f"published internet evidence differs from source size: {catalog_key}"
                )
            if evidence.get("pdf_page_count") != document.get("expected_pdf_pages"):
                raise SemanticPublishError(
                    f"published internet evidence differs from source pages: {catalog_key}"
                )


def _formats_payload() -> JsonObject:
    return {
        "schema_version": "1.0.0",
        "container": {
            "encoding": "UTF-8",
            "record_format": "JSON Lines",
            "canonical_key_order": "lexicographic",
        },
        "rules": {
            "semantic_model": "subject-predicate-modality with explicit qualifiers",
            "numeric_fields": ["comparator", "value", "printed_unit"],
            "provenance_fields": [
                "catalog_key",
                "bundle_id",
                "bundle_sha256",
                "validation_id",
                "validator_response_sha256",
                "pass_a_response_sha256",
                "pass_b_response_sha256",
            ],
            "source_anchor_fields": ["source_span_ids", "qualifier_span_ids"],
        },
        "formulas": {
            "preferred_semantic_format": "Content MathML",
            "preferred_display_format": "Presentation MathML",
            "exchange_format": "LaTeX",
            "text_fallback": "Unicode plus raw_transcription",
            "quality_fields": [
                "parse_status",
                "diagnostics",
                "unresolved_glyphs",
            ],
        },
        "units": {
            "normalized_standard": "UCUM",
            "normalized_field": "ucum_code",
            "source_field": "printed",
            "quality_field": "mapping_status",
        },
        "internet_verification": {
            "source": "validated INBR acquisition receipt",
            "transport": "successful official-origin HTTP response",
            "content_binding": "SHA-256, byte count, media type, and PDF page count",
            "document_field": "internet_verification",
        },
        "uncertain_data_policy": (
            "No record with uncertainty or a failed semantic quality gate is placed "
            "in rules.jsonl; it is retained in deferred.jsonl."
        ),
    }


def _publish_validated_bundle(
    bundle: JsonObject,
    *,
    extraction_root: Path,
    artifacts_by_key: dict[str, JsonObject],
) -> tuple[list[JsonObject], list[JsonObject], list[JsonObject], JsonObject]:
    validation = cast(JsonObject, bundle["validation"])
    validation_id = _required_string(validation, "validation_id")
    receipt = _single_receipt(
        extraction_root,
        f"validator-receipts/{_sha256_token(validation_id)}",
        description=validation_id,
    )
    response = _load_response(receipt, root=extraction_root)
    pass_a = _load_job_response(receipt, "pass_a_job_id", root=extraction_root)
    pass_b = _load_job_response(receipt, "pass_b_job_id", root=extraction_root)
    source_candidate_list = [
        candidate
        for source in (pass_a, pass_b)
        for candidate in _records(source, "candidates")
    ]
    source_candidates = {
        _required_string(candidate, "candidate_id"): candidate
        for candidate in source_candidate_list
    }
    catalog_key = _required_string(bundle, "catalog_key")
    artifact = artifacts_by_key.get(catalog_key)
    if artifact is None:
        raise SemanticPublishError(
            f"validated bundle has unknown catalog key: {catalog_key}"
        )
    provenance: JsonObject = {
        "catalog_key": catalog_key,
        "catalog_order": artifact["catalog_order"],
        "official_source_sha256": artifact["expected_sha256"],
        "bundle_id": bundle["bundle_id"],
        "bundle_sha256": receipt["bundle_sha256"],
        "bundle_sequence": bundle["bundle_sequence"],
        "start_pdf_page": bundle["start_pdf_page"],
        "end_pdf_page": bundle["end_pdf_page"],
        "validation_id": validation_id,
        "validator_response_sha256": validation["response_sha256"],
        "pass_a_response_sha256": receipt["pass_a_response_sha256"],
        "pass_b_response_sha256": receipt["pass_b_response_sha256"],
    }
    try:
        reconciliation = reconcile_validator(response, pass_a=pass_a, pass_b=pass_b)
    except SemanticReconciliationError as exc:
        decision: JsonObject = {
            "reconciliation_error": str(exc),
            "accepted_candidate_ids": _candidate_ids(response, "accepted_candidates"),
            "rejected_candidate_ids": _candidate_ids(response, "rejected_candidates"),
            "deferred_candidate_ids": _decision_source_ids(response, "deferred_candidates"),
        }
        failed_deferred = [
            _deferred_record(
                "VALIDATOR_RECONCILIATION_FAILED",
                provenance=provenance,
                decision=decision,
                source_candidates=source_candidate_list,
            )
        ]
        validation_reference = {
            **provenance,
            "state": "needs_review",
            "accepted_candidates": 0,
            "rejected_candidates": 0,
            "deferred_candidates": 1,
            "unaccounted_candidates": len(source_candidate_list),
        }
        return [], [], failed_deferred, validation_reference
    rules: list[JsonObject] = []
    deferred: list[JsonObject] = []
    merge_by_candidate = {
        _required_string(merge, "accepted_candidate_id"): merge
        for merge in _records(response, "merged_candidates")
    }
    for candidate in _records(response, "accepted_candidates"):
        uncertainty = candidate.get("uncertainty_codes")
        merge = merge_by_candidate[_required_string(candidate, "candidate_id")]
        quality_codes = _candidate_quality_codes(candidate)
        if uncertainty == [] and not quality_codes:
            rules.append(
                _candidate_record(
                    "rule", candidate, provenance=provenance, validation_decision=merge
                )
            )
        else:
            codes = (
                cast(list[str], uncertainty)
                if isinstance(uncertainty, list)
                and all(isinstance(code, str) and code for code in uncertainty)
                else ["INVALID_UNCERTAINTY_METADATA"]
            )
            reason_code = (
                "ACCEPTED_CANDIDATE_FAILED_QUALITY_GATE"
                if quality_codes
                else "ACCEPTED_CANDIDATE_HAS_UNCERTAINTY"
            )
            deferred.append(
                _deferred_record(
                    reason_code,
                    provenance=provenance,
                    decision=candidate,
                    source_candidates=[candidate],
                    detail={
                        "uncertainty_codes": codes,
                        "quality_codes": quality_codes,
                        "validation_decision": merge,
                    },
                )
            )

    rejected = [
        _audit_record(
            "rejected",
            decision,
            provenance=provenance,
            source_candidates=_source_candidates_for_decision(
                decision, source_candidates=source_candidates
            ),
        )
        for decision in _records(response, "rejected_candidates")
    ]
    for decision in _records(response, "deferred_candidates"):
        deferred.append(
            _deferred_record(
                "VALIDATOR_DEFERRED",
                provenance=provenance,
                decision=decision,
                source_candidates=_source_candidates_for_decision(
                    decision, source_candidates=source_candidates
                ),
            )
        )
    for candidate_id in reconciliation.unaccounted_candidate_ids:
        deferred.append(
            _deferred_record(
                "VALIDATOR_UNACCOUNTED_SOURCE_CANDIDATE",
                provenance=provenance,
                decision={"candidate_id": candidate_id},
                source_candidates=[source_candidates[candidate_id]],
            )
        )
    validation_reference = {
        **provenance,
        "state": bundle["state"],
        "accepted_candidates": reconciliation.accepted_candidates,
        "rejected_candidates": reconciliation.rejected_candidates,
        "deferred_candidates": reconciliation.deferred_candidates,
        "unaccounted_candidates": len(reconciliation.unaccounted_candidate_ids),
    }
    return rules, rejected, deferred, validation_reference


def _structure_records(
    structure: JsonObject,
    *,
    structure_root: Path,
    artifacts_by_key: dict[str, JsonObject],
) -> tuple[list[JsonObject], list[JsonObject], list[JsonObject], list[JsonObject]]:
    raw_documents = structure.get("documents")
    if not isinstance(raw_documents, list):
        raise SemanticPublishError("structure manifest has no documents")
    formulas: list[JsonObject] = []
    tables: list[JsonObject] = []
    units: list[JsonObject] = []
    deferred: list[JsonObject] = []
    for reference in raw_documents:
        if not isinstance(reference, dict):
            raise SemanticPublishError("structure document reference is invalid")
        document = cast(JsonObject, reference)
        catalog_key = _required_string(document, "catalog_key")
        artifact = artifacts_by_key.get(catalog_key)
        if artifact is None:
            raise SemanticPublishError(f"structure has unknown catalog key: {catalog_key}")
        if document.get("source_sha256") != artifact.get("expected_sha256"):
            raise SemanticPublishError(
                f"structure source differs from official catalog: {catalog_key}"
            )
        graph = _load_attested_json(
            structure_root,
            _required_string(document, "path"),
            expected_sha256=_required_sha256(document, "sha256"),
            expected_bytes=_required_int(document, "bytes"),
            description=f"structure graph {catalog_key}",
        )
        if graph.get("catalog_key") != catalog_key or graph.get(
            "source_sha256"
        ) != document.get("source_sha256"):
            raise SemanticPublishError(
                f"structure graph identity differs from manifest: {catalog_key}"
            )
        provenance: JsonObject = {
            "catalog_key": catalog_key,
            "catalog_order": artifact["catalog_order"],
            "official_source_sha256": artifact["expected_sha256"],
            "source_sha256": document["source_sha256"],
            "structure_graph_sha256": document["sha256"],
        }
        for formula in _records(graph, "formulas"):
            record = _structure_record("formula", formula, provenance=provenance)
            formulas.append(record)
            deferred.append(
                _structural_deferred(
                    "FORMULA_REQUIRES_REVIEW", formula, provenance=provenance
                )
            )
        for table in _records(graph, "tables"):
            record = _structure_record("table", table, provenance=provenance)
            tables.append(record)
            deferred.append(
                _structural_deferred("TABLE_REQUIRES_REVIEW", table, provenance=provenance)
            )
        for unit in _records(graph, "units"):
            units.append(_structure_record("unit", unit, provenance=provenance))
            if unit.get("mapping_status") != "mapped" or not unit.get("ucum_code"):
                deferred.append(
                    _structural_deferred(
                        "UNIT_MAPPING_REQUIRES_REVIEW", unit, provenance=provenance
                    )
                )
        for page in _records(graph, "pages"):
            if page.get("state") != "ready":
                deferred.append(
                    _structural_deferred(
                        "PAGE_TRANSCRIPTION_REQUIRES_REVIEW",
                        page,
                        provenance=provenance,
                    )
                )
    expected = cast(JsonObject, structure.get("summary", {}))
    if (
        expected.get("formulas") != len(formulas)
        or expected.get("tables") != len(tables)
        or expected.get("units") != len(units)
    ):
        raise SemanticPublishError("structure totals differ during publication")
    structural_expected = expected.get("needs_review")
    structural_actual = sum(
        item["reason_code"]
        in {
            "FORMULA_REQUIRES_REVIEW",
            "TABLE_REQUIRES_REVIEW",
            "PAGE_TRANSCRIPTION_REQUIRES_REVIEW",
        }
        for item in deferred
    )
    if structural_expected != structural_actual:
        raise SemanticPublishError("structural deferred-review total differs")
    return formulas, tables, units, deferred


def _candidate_record(
    kind: str,
    candidate: JsonObject,
    *,
    provenance: JsonObject,
    validation_decision: JsonObject,
) -> JsonObject:
    identity = {
        "kind": kind,
        "bundle_id": provenance["bundle_id"],
        "candidate_id": candidate["candidate_id"],
    }
    return {
        "schema_version": "1.0.0",
        "record_id": f"sha256:{sha256_json(identity)}",
        "provenance": provenance,
        "validation_decision": validation_decision,
        "candidate": candidate,
    }


def _audit_record(
    kind: str,
    decision: JsonObject,
    *,
    provenance: JsonObject,
    source_candidates: list[JsonObject],
) -> JsonObject:
    identity = {
        "kind": kind,
        "validation_id": provenance["validation_id"],
        "decision": decision,
    }
    return {
        "schema_version": "1.0.0",
        "record_id": f"sha256:{sha256_json(identity)}",
        "provenance": provenance,
        "decision": decision,
        "source_candidates": source_candidates,
    }


def _deferred_record(
    reason_code: str,
    *,
    provenance: JsonObject,
    decision: JsonObject,
    source_candidates: list[JsonObject],
    detail: JsonObject | None = None,
) -> JsonObject:
    record = _audit_record(
        "deferred", decision, provenance=provenance, source_candidates=source_candidates
    )
    record["reason_code"] = reason_code
    if detail is not None:
        record["detail"] = detail
    return record


def _structure_record(kind: str, item: JsonObject, *, provenance: JsonObject) -> JsonObject:
    item_id = _structure_item_id(kind, item)
    identity = {"kind": kind, "item_id": item_id}
    return {
        "schema_version": "1.0.0",
        "record_id": f"sha256:{sha256_json(identity)}",
        "provenance": provenance,
        "item": item,
    }


def _structural_deferred(
    reason_code: str, item: JsonObject, *, provenance: JsonObject
) -> JsonObject:
    kind = reason_code.split("_", maxsplit=1)[0].lower()
    item_id = _structure_item_id(kind, item)
    identity = {"reason_code": reason_code, "item_id": item_id}
    return {
        "schema_version": "1.0.0",
        "record_id": f"sha256:{sha256_json(identity)}",
        "reason_code": reason_code,
        "provenance": provenance,
        "item_kind": kind,
        "item_id": item_id,
        "pdf_page": item.get("pdf_page"),
        "source_span_ids": item.get("source_span_ids", []),
        "diagnostics": item.get("diagnostics", item.get("reason_codes", [])),
    }


def _structure_item_id(kind: str, item: JsonObject) -> str:
    field = {
        "formula": "formula_id",
        "table": "table_id",
        "unit": "unit_id",
        "page": "page_id",
    }[kind]
    return _required_string(item, field)


def _source_candidates_for_decision(
    decision: JsonObject, *, source_candidates: dict[str, JsonObject]
) -> list[JsonObject]:
    raw_ids = decision.get("source_candidate_ids")
    if raw_ids is None:
        raw_ids = [decision.get("candidate_id")]
    if not isinstance(raw_ids, list) or not all(
        isinstance(candidate_id, str) and candidate_id for candidate_id in raw_ids
    ):
        raise SemanticPublishError("validator decision has invalid source candidate IDs")
    result: list[JsonObject] = []
    for candidate_id in cast(list[str], raw_ids):
        candidate = source_candidates.get(candidate_id)
        if candidate is None:
            raise SemanticPublishError(
                f"validator decision source candidate is missing: {candidate_id}"
            )
        result.append(candidate)
    return result


def _candidate_quality_codes(candidate: JsonObject) -> list[str]:
    codes: list[str] = []
    for field in ("kind", "subject", "predicate", "modality", "english_gloss"):
        value = candidate.get(field)
        if not isinstance(value, str) or not value.strip():
            codes.append(f"MISSING_{field.upper()}")
    for field in (
        "conditions",
        "exceptions",
        "references",
        "formula_or_table_notes",
        "source_span_ids",
        "qualifier_span_ids",
    ):
        if not isinstance(candidate.get(field), list):
            codes.append(f"INVALID_{field.upper()}")
    predicate = str(candidate.get("predicate", "")).casefold()
    gloss = str(candidate.get("english_gloss", "")).casefold()
    generic_fragments = (
        "is governed by this source passage",
        "presents provisions concerning",
        "source-supported requirements and design provisions",
        "exact semantics require later validation",
        "exact numeric, formula, and table content remains unmodeled",
        "source-anchored building-regulations passage",
        "clause-level source extraction from page",
        "atomic source statement on pdf page",
        "states a technical provision",
        "requires, prohibits, permits, or directs an action",
    )
    if any(fragment in predicate or fragment in gloss for fragment in generic_fragments):
        codes.append("GENERIC_PAGE_SUMMARY")
    return codes


def _load_job_response(receipt: JsonObject, field: str, *, root: Path) -> JsonObject:
    job_id = _required_string(receipt, field)
    job_receipt = _single_receipt(
        root, f"receipts/{_sha256_token(job_id)}", description=job_id
    )
    return _load_response(job_receipt, root=root)


def _load_response(receipt: JsonObject, *, root: Path) -> JsonObject:
    raw_reference = receipt.get("response")
    if not isinstance(raw_reference, dict):
        raise SemanticPublishError("ingest receipt has no response reference")
    reference = cast(JsonObject, raw_reference)
    return _load_attested_json(
        root,
        _required_string(reference, "path"),
        expected_sha256=_required_sha256(reference, "sha256"),
        expected_bytes=_required_int(reference, "bytes"),
        description="stored semantic response",
    )


def _single_receipt(root: Path, relative: str, *, description: str) -> JsonObject:
    directory = safe_path(root, relative)
    try:
        entries = sorted(directory.iterdir(), key=lambda path: path.name)
    except OSError as exc:
        raise SemanticPublishError(f"cannot inspect receipt for {description}") from exc
    if len(entries) != 1:
        raise SemanticPublishError(
            f"receipt cardinality is not one for {description}: {len(entries)}"
        )
    return load_ingested_receipt(entries[0])


def _load_attested_json(
    root: Path,
    relative: str,
    *,
    expected_sha256: str,
    expected_bytes: int,
    description: str,
) -> JsonObject:
    try:
        payload, _ = read_attested_bytes(
            safe_path(root, relative),
            expected_sha256=expected_sha256,
            expected_bytes=expected_bytes,
        )
        return loads_object(payload.decode("utf-8"), description=description)
    except (StorageError, UnicodeDecodeError) as exc:
        raise SemanticPublishError(str(exc)) from exc


def _catalog_artifacts(catalog: JsonObject) -> list[JsonObject]:
    raw = catalog.get("artifacts")
    if not isinstance(raw, list) or not all(isinstance(item, dict) for item in raw):
        raise SemanticPublishError("catalog has no artifact list")
    return [cast(JsonObject, item) for item in raw]


def _records(value: JsonObject, field: str) -> list[JsonObject]:
    raw = value.get(field)
    if not isinstance(raw, list) or not all(isinstance(item, dict) for item in raw):
        raise SemanticPublishError(f"invalid {field}")
    return [cast(JsonObject, item) for item in raw]


def _candidate_ids(value: JsonObject, field: str) -> list[str]:
    return [_required_string(record, "candidate_id") for record in _records(value, field)]


def _decision_source_ids(value: JsonObject, field: str) -> list[str]:
    result: list[str] = []
    for decision in _records(value, field):
        raw_ids = decision.get("source_candidate_ids")
        if isinstance(raw_ids, list) and all(
            isinstance(candidate_id, str) and candidate_id for candidate_id in raw_ids
        ):
            result.extend(cast(list[str], raw_ids))
            continue
        candidate_id = decision.get("candidate_id")
        if isinstance(candidate_id, str) and candidate_id:
            result.append(candidate_id)
    return result


def _jsonl_bytes(records: list[JsonObject]) -> bytes:
    return b"".join(
        (
            json.dumps(
                record,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            + "\n"
        ).encode("utf-8")
        for record in records
    )


def _load_jsonl(payload: bytes, *, description: str) -> list[JsonObject]:
    records: list[JsonObject] = []
    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise SemanticPublishError(f"{description} is not UTF-8") from exc
    for line_number, line in enumerate(text.splitlines(), start=1):
        try:
            value: Any = json.loads(line)
        except json.JSONDecodeError as exc:
            raise SemanticPublishError(
                f"{description} line {line_number} is invalid JSON"
            ) from exc
        if not isinstance(value, dict):
            raise SemanticPublishError(f"{description} line {line_number} is not an object")
        records.append(cast(JsonObject, value))
    return records


def _sha256_token(value: str) -> str:
    if not value.startswith("sha256:"):
        raise SemanticPublishError(f"invalid SHA-256 identity: {value}")
    token = value.removeprefix("sha256:")
    if len(token) != 64 or any(character not in "0123456789abcdef" for character in token):
        raise SemanticPublishError(f"invalid SHA-256 identity: {value}")
    return token


def _required_string(value: JsonObject, field: str) -> str:
    result = value.get(field)
    if not isinstance(result, str) or not result:
        raise SemanticPublishError(f"invalid or missing {field}")
    return result


def _required_sha256(value: JsonObject, field: str) -> str:
    result = _required_string(value, field)
    if len(result) != 64 or any(
        character not in "0123456789abcdef" for character in result
    ):
        raise SemanticPublishError(f"invalid or missing {field}")
    return result


def _required_int(value: JsonObject, field: str) -> int:
    result = value.get(field)
    if not isinstance(result, int) or isinstance(result, bool) or result < 0:
        raise SemanticPublishError(f"invalid or missing {field}")
    return result
