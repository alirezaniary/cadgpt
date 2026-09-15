"""Fail-closed contracts for derived observations used by deferred rules."""

from __future__ import annotations

import hashlib
import math
from collections.abc import Mapping, Sequence
from typing import Any, cast

from cadgpt_regulations.citation import citation_hash, validate_source_citation
from cadgpt_regulations.errors import RegulationsError
from cadgpt_regulations.jsonio import JsonObject, canonical_bytes, validate_schema
from cadgpt_regulations.resources import load_packaged_json


class ObservationContractError(RegulationsError):
    """Raised when an observation contract cannot be safely evaluated."""


def build_observation_contract(
    rule: Mapping[str, Any],
    required_observations: Sequence[Mapping[str, Any]],
) -> JsonObject:
    """Create a deterministic deferred contract retaining the source citation."""
    citation = rule.get("source_citation")
    if not isinstance(citation, dict):
        raise ObservationContractError("rule has no source citation")
    try:
        validate_source_citation(cast(JsonObject, citation))
    except RegulationsError as exc:
        raise ObservationContractError(str(exc)) from exc
    observations: list[JsonObject] = []
    seen: set[str] = set()
    for index, raw in enumerate(required_observations):
        key = raw.get("observation_key")
        kind = raw.get("kind")
        if not isinstance(key, str) or not key or key in seen:
            raise ObservationContractError(
                f"observation {index} has a duplicate or invalid observation_key"
            )
        if kind not in {"geometry", "formula", "table", "numeric", "text", "boolean"}:
            raise ObservationContractError(f"observation {key} has unsupported kind")
        seen.add(key)
        observations.append(
            {
                "observation_key": key,
                "kind": kind,
                "status": "PENDING",
                "unit": raw.get("unit"),
            }
        )
    if not observations:
        raise ObservationContractError("at least one required observation is needed")
    payload = {
        "rule": dict(rule),
        "source_citation": citation,
        "required_observations": observations,
    }
    record_id = hashlib.sha256(canonical_bytes(cast(JsonObject, payload))).hexdigest()
    contract: JsonObject = {
        "schema_version": "observation-contract-1.0.0",
        "record_id": record_id,
        "status": "DEFERRED",
        "reason_code": "REQUIRES_DERIVED_OBSERVATIONS",
        "source_citation_sha256": citation_hash(cast(JsonObject, citation)),
        **payload,
    }
    try:
        validate_schema(
            contract,
            load_packaged_json(
                "cadgpt_regulations.schemas", "observation-contract.schema.json"
            ),
            description="observation contract",
        )
    except RegulationsError as exc:
        raise ObservationContractError(str(exc)) from exc
    return contract


def resolve_observations(
    contract: JsonObject,
    values: Mapping[str, Any],
) -> JsonObject:
    """Resolve observations; missing or ambiguous inputs remain INDETERMINATE."""
    try:
        validate_schema(
            contract,
            load_packaged_json(
                "cadgpt_regulations.schemas", "observation-contract.schema.json"
            ),
            description="observation contract",
        )
        citation = cast(JsonObject, contract["source_citation"])
        validate_source_citation(citation)
        if contract["source_citation_sha256"] != citation_hash(citation):
            raise ObservationContractError("contract citation hash differs")
        payload = {
            key: contract[key]
            for key in ("rule", "source_citation", "required_observations")
        }
        if contract["record_id"] != hashlib.sha256(canonical_bytes(payload)).hexdigest():
            raise ObservationContractError("contract identity differs")
    except RegulationsError as exc:
        raise ObservationContractError(str(exc)) from exc
    required = contract.get("required_observations")
    if not isinstance(required, list):
        raise ObservationContractError("contract has no required observations")
    resolved: list[JsonObject] = []
    indeterminate = False
    for observation in required:
        if not isinstance(observation, dict):
            raise ObservationContractError("contract observation is invalid")
        key = observation.get("observation_key")
        value = values.get(key)
        if isinstance(value, (list, tuple)):
            value = value[0] if len(value) == 1 else None
        kind = observation.get("kind")
        valid = (
            (
                kind == "numeric"
                and isinstance(value, (int, float))
                and not isinstance(value, bool)
                and math.isfinite(value)
            )
            or (kind == "text" and isinstance(value, str) and bool(value.strip()))
            or (kind == "boolean" and isinstance(value, bool))
        )
        if not valid:
            status = "INDETERMINATE"
            indeterminate = True
            resolved_value = None
        else:
            status = "AVAILABLE"
            resolved_value = value
        resolved.append({"observation_key": key, "status": status, "value": resolved_value})
    return {
        "contract_id": contract["record_id"],
        "source_citation": contract["source_citation"],
        "source_citation_sha256": contract["source_citation_sha256"],
        "status": "INDETERMINATE" if indeterminate else "AVAILABLE",
        "observations": resolved,
    }
