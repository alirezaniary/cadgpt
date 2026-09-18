"""Classify canonical rules before they reach a limited engine compiler."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from typing import Any, cast

from cadgpt_regulations.citation import citation_hash, validate_source_citation
from cadgpt_regulations.errors import RegulationsError
from cadgpt_regulations.jsonio import JsonObject, canonical_bytes, validate_schema
from cadgpt_regulations.resources import load_packaged_json
from cadgpt_regulations.rule_ir import RuleIRError, validate_rule_ir


class RuleCapabilityError(RegulationsError):
    """Raised when a rule cannot be classified without losing provenance."""


def classify_rule(rule: Mapping[str, Any]) -> JsonObject:
    """Return a native-supported or citation-preserving deferred artifact."""
    value = dict(rule)
    citation = value.get("source_citation")
    if not isinstance(citation, dict):
        raise RuleCapabilityError("rule source_citation must be an object")
    try:
        validate_source_citation(cast(JsonObject, citation))
    except RegulationsError as exc:
        raise RuleCapabilityError(str(exc)) from exc
    reason = _unsupported_reason(value)
    if reason is None:
        try:
            validated = validate_rule_ir(value)
        except RuleIRError:
            reason = "RULE_IR_INVALID"
        else:
            rule_id = hashlib.sha256(canonical_bytes(validated)).hexdigest()
            return {
                "schema_version": "rule-capability-1.0.0",
                "record_id": rule_id,
                "status": "native_supported",
                "rule_id": rule_id,
                "source_citation_sha256": citation_hash(cast(JsonObject, citation)),
                "source_citation": citation,
            }
    record_id = hashlib.sha256(
        canonical_bytes({"rule": value, "reason_code": reason})
    ).hexdigest()
    deferred: JsonObject = {
        "schema_version": "rule-capability-1.0.0",
        "record_id": record_id,
        "status": "deferred",
        "reason_code": reason,
        "source_citation_sha256": citation_hash(cast(JsonObject, citation)),
        "source_citation": citation,
        "original_rule": value,
    }
    try:
        validate_schema(
            deferred,
            load_packaged_json("cadgpt_regulations.schemas", "deferred-rule.schema.json"),
            description="deferred rule",
        )
    except RegulationsError as exc:
        raise RuleCapabilityError(str(exc)) from exc
    return deferred


def _unsupported_reason(rule: Mapping[str, Any]) -> str | None:
    if any(key in rule for key in ("formula", "formula_fa", "formula_ids")):
        return "FORMULA_REQUIRES_DERIVED_OBSERVATION"
    if any(key in rule for key in ("table", "table_fa", "table_ids")):
        return "TABLE_LOOKUP_REQUIRES_DEFERRED_EVALUATION"
    if any(key in rule for key in ("derived_observation", "observation")):
        return "DERIVED_OBSERVATION_NOT_NATIVE"
    comparator = rule.get("comparator")
    if comparator not in {"eq", "equals", "gt", "gte", "lt", "lte"}:
        return "UNSUPPORTED_COMPARATOR"
    return None
