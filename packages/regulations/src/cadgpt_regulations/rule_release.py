"""Hash-pinned manifests for immutable, source-cited rule releases."""

from __future__ import annotations

import hashlib
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any, cast

from cadgpt_regulations.citation import (
    citation_evidence_kind,
    citation_hash,
    validate_source_citation,
)
from cadgpt_regulations.errors import RegulationsError
from cadgpt_regulations.jsonio import JsonObject, canonical_bytes, sha256_json
from cadgpt_regulations.storage import (
    ensure_private_tree,
    install_immutable_bytes,
    validate_output_root,
)


class RuleReleaseError(RegulationsError):
    """Raised when a rule release cannot be made deterministic and complete."""


def build_rule_release_manifest(
    compiled_rules: Iterable[Mapping[str, Any]],
    *,
    deferred_records: Iterable[Mapping[str, Any]] = (),
    assertion_count: int = 0,
) -> JsonObject:
    """Build a deterministic coverage manifest from compiled rule artifacts."""
    entries: list[JsonObject] = []
    seen_ids: set[str] = set()
    for compiled in compiled_rules:
        rule_id, ids_xml, sidecar = _compiled_parts(compiled)
        if Path(rule_id).name != rule_id or rule_id in {".", ".."}:
            raise RuleReleaseError("rule_id must be a path-safe filename")
        if rule_id in seen_ids:
            raise RuleReleaseError(f"duplicate compiled rule: {rule_id}")
        seen_ids.add(rule_id)
        if not isinstance(ids_xml, (bytes, bytearray)) or not isinstance(sidecar, Mapping):
            raise RuleReleaseError(f"compiled rule {rule_id} has invalid artifacts")
        sidecar_object = cast(JsonObject, dict(sidecar))
        declared_rule_id = sidecar_object.get("rule_id")
        if declared_rule_id is not None and declared_rule_id != rule_id:
            raise RuleReleaseError(f"compiled rule {rule_id} sidecar ID differs")
        citation = sidecar_object.get("source_citation")
        if not isinstance(citation, dict):
            raise RuleReleaseError(f"compiled rule {rule_id} has no source citation")
        try:
            validate_source_citation(cast(JsonObject, citation))
        except RegulationsError as exc:
            raise RuleReleaseError(str(exc)) from exc
        attestation = sidecar_object.get("source_attestation")
        if not isinstance(attestation, Mapping):
            raise RuleReleaseError(
                f"compiled rule {rule_id} has no source attestation; "
                "citation status alone cannot authorize release"
            )
        if attestation.get("document_sha256") != citation.get("document_sha256"):
            raise RuleReleaseError(f"compiled rule {rule_id} attestation document differs")
        decision = attestation.get("decision")
        if decision not in {"anchored", "already_anchored", "transcript"}:
            raise RuleReleaseError(
                f"compiled rule {rule_id} source attestation is not anchored"
            )
        if decision == "transcript":
            if (
                citation_evidence_kind(citation) != "transcript"
                or attestation.get("transcript_revision_id")
                != citation.get("transcript_revision_id")
                or attestation.get("transcript_sha256") != citation.get("transcript_sha256")
            ):
                raise RuleReleaseError(
                    f"compiled rule {rule_id} transcript attestation differs"
                )
        else:
            report_sha256 = attestation.get("report_sha256")
            if not isinstance(report_sha256, str) or len(report_sha256) != 64:
                raise RuleReleaseError(
                    f"compiled rule {rule_id} source attestation lacks report hash"
                )
        ids_hash = hashlib.sha256(bytes(ids_xml)).hexdigest()
        sidecar_hash = hashlib.sha256(canonical_bytes(sidecar_object)).hexdigest()
        declared_ids_hash = sidecar_object.get("ids_sha256")
        if declared_ids_hash is not None and declared_ids_hash != ids_hash:
            raise RuleReleaseError(f"compiled rule {rule_id} IDS hash differs")
        entries.append(
            {
                "rule_id": rule_id,
                "ids_sha256": ids_hash,
                "sidecar_sha256": sidecar_hash,
                "source_citation_sha256": citation_hash(cast(JsonObject, citation)),
                "document_key": citation["document_key"],
                "document_sha256": citation["document_sha256"],
                "pdf_page": citation["pdf_page"],
                "source_node_ids": list(
                    cast(list[str], citation.get("source_node_ids", []))
                ),
                "source_span_ids": list(
                    cast(list[str], citation.get("source_span_ids", []))
                ),
            }
        )
    entries.sort(key=lambda item: cast(str, item["rule_id"]))
    deferred = [dict(record) for record in deferred_records]
    deferred_ids: list[str] = []
    for index, record in enumerate(deferred):
        record_id = record.get("record_id", f"deferred-{index}")
        if not isinstance(record_id, str) or not record_id:
            raise RuleReleaseError("deferred record_id must be a non-empty string")
        # Materialize generated IDs in the persisted record so SQL projection
        # can rebuild rows without relying on positional fallbacks.
        record["record_id"] = record_id
        deferred_ids.append(record_id)
    if len(set(deferred_ids)) != len(deferred_ids):
        raise RuleReleaseError("deferred record IDs must be unique")
    body: JsonObject = {
        "schema_version": "rule-release-1.0.0",
        "rules": entries,
        "deferred": {
            "count": len(deferred),
            "record_ids": deferred_ids,
            "records": deferred,
        },
        "coverage": {
            "rules": len(entries),
            "verified_citations": len(entries),
            "documents": len({entry["document_key"] for entry in entries}),
            "source_spans": len(
                {
                    span
                    for entry in entries
                    for span in cast(list[str], entry["source_span_ids"])
                }
            ),
            "assertions": assertion_count,
            "deferred": len(deferred),
        },
    }
    release_id = sha256_json(body)
    return {**body, "release_id": release_id}


def write_rule_release(
    manifest: JsonObject,
    compiled_rules: Iterable[Mapping[str, Any]],
    *,
    output_root: Path,
) -> Path:
    """Install compiled rule bytes and the manifest under a content-addressed root."""
    validate_output_root(output_root, description="rule release output root")
    release_id = _required_string(manifest, "release_id")
    manifest_body = dict(manifest)
    manifest_body.pop("release_id", None)
    if sha256_json(cast(JsonObject, manifest_body)) != release_id:
        raise RuleReleaseError("release_id does not match canonical manifest body")
    compiled_list = list(compiled_rules)
    expected = {
        item["rule_id"]: item for item in cast(list[JsonObject], manifest.get("rules", []))
    }
    directory = ensure_private_tree(output_root, f"releases/{release_id}")
    ensure_private_tree(directory, "rules")
    seen: set[str] = set()
    for compiled in compiled_list:
        rule_id, ids_xml, sidecar = _compiled_parts(compiled)
        if Path(rule_id).name != rule_id or rule_id in {".", ".."}:
            raise RuleReleaseError("rule_id must be a path-safe filename")
        if not isinstance(ids_xml, (bytes, bytearray)) or not isinstance(sidecar, Mapping):
            raise RuleReleaseError(f"compiled rule {rule_id} has invalid artifacts")
        if rule_id in seen or rule_id not in expected:
            raise RuleReleaseError(f"compiled rule {rule_id} is not in manifest")
        seen.add(rule_id)
        if hashlib.sha256(bytes(ids_xml)).hexdigest() != expected[rule_id]["ids_sha256"]:
            raise RuleReleaseError(f"compiled rule {rule_id} differs from manifest")
        sidecar_hash = hashlib.sha256(
            canonical_bytes(cast(JsonObject, dict(sidecar)))
        ).hexdigest()
        if sidecar_hash != expected[rule_id]["sidecar_sha256"]:
            raise RuleReleaseError(f"compiled rule {rule_id} sidecar differs from manifest")
    if seen != set(expected):
        raise RuleReleaseError("manifest rules do not match compiled artifacts")
    for compiled in compiled_list:
        rule_id, ids_xml, sidecar = _compiled_parts(compiled)
        install_immutable_bytes(directory / "rules" / f"{rule_id}.ids", bytes(ids_xml))
        install_immutable_bytes(
            directory / "rules" / f"{rule_id}.json",
            canonical_bytes(cast(JsonObject, dict(sidecar))),
        )
    install_immutable_bytes(directory / "manifest.json", canonical_bytes(manifest))
    return directory


def _required_string(value: Mapping[str, Any], field: str) -> str:
    result = value.get(field)
    if not isinstance(result, str) or not result:
        raise RuleReleaseError(f"{field} must be a non-empty string")
    return result


def _compiled_parts(value: Any) -> tuple[str, Any, Any]:
    """Accept CompiledRule objects and mapping-shaped artifacts."""
    if isinstance(value, Mapping):
        rule_id = value.get("rule_id")
        ids_xml = value.get("ids_xml")
        sidecar = value.get("sidecar")
    else:
        rule_id = getattr(value, "rule_id", None)
        ids_xml = getattr(value, "ids_xml", None)
        sidecar = getattr(value, "sidecar", None)
    if not isinstance(rule_id, str) or not rule_id:
        raise RuleReleaseError("rule_id must be a non-empty string")
    if Path(rule_id).name != rule_id or rule_id in {".", ".."}:
        raise RuleReleaseError("rule_id must be a path-safe filename")
    return rule_id, ids_xml, sidecar
