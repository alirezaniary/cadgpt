"""Canonical, source-cited rule intermediate representation."""

from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Any, cast

from cadgpt_regulations.citation import validate_source_citation
from cadgpt_regulations.errors import RegulationsError
from cadgpt_regulations.jsonio import JsonObject, validate_schema
from cadgpt_regulations.resources import load_packaged_json


class RuleIRError(RegulationsError):
    """Raised when a rule is not safe to hand to a deterministic compiler."""


def validate_rule_ir(rule: Mapping[str, Any]) -> JsonObject:
    """Validate and return a JSON-compatible canonical rule mapping.

    Schema validation handles shape and unknown fields; citation validation then
    re-attests the exact Persian quotation and its source anchors.
    """
    value = dict(rule)
    if not all(isinstance(key, str) for key in value):
        raise RuleIRError("rule IR keys must be strings")
    try:
        validate_schema(
            cast(JsonObject, value),
            load_packaged_json("cadgpt_regulations.schemas", "rule-ir.schema.json"),
            description="rule IR",
        )
    except RegulationsError as exc:
        raise RuleIRError(str(exc)) from exc
    numeric = value["value"]
    if isinstance(numeric, bool) or not isinstance(numeric, (int, float)):
        raise RuleIRError("rule IR value must be numeric")
    if not math.isfinite(float(numeric)):
        raise RuleIRError("rule IR value must be finite")
    citation = value["source_citation"]
    if not isinstance(citation, dict):
        raise RuleIRError("rule IR source_citation must be an object")
    try:
        validate_source_citation(cast(JsonObject, citation))
    except RegulationsError as exc:
        raise RuleIRError(str(exc)) from exc
    return cast(JsonObject, value)
