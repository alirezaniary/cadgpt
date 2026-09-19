"""Canonical, source-cited rule intermediate representation."""

from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Any, cast

from cadgpt_regulations.citation import validate_source_citation
from cadgpt_regulations.errors import RegulationsError
from cadgpt_regulations.jsonio import JsonObject, validate_schema
from cadgpt_regulations.resources import load_packaged_json

_NUMERIC_DATATYPES = frozenset({"double", "decimal", "integer"})
_BOUNDS_FACETS = ("minInclusive", "minExclusive", "maxInclusive", "maxExclusive")


class RuleIRError(RegulationsError):
    """Raised when a rule is not safe to hand to a deterministic compiler."""


def validate_rule_ir(rule: Mapping[str, Any]) -> JsonObject:
    """Validate and return a JSON-compatible canonical rule mapping.

    Schema validation handles shape and unknown fields; citation validation then
    re-attests the exact Persian quotation and its source anchors. The schema is a
    union of two requirement kinds: a flat ``attribute`` rule (the original shape,
    kept byte-for-byte compatible) and a ``property`` rule carrying a property set,
    base name, datatype and a bounds object with one or more XSD facets.
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
    if value.get("requirement_kind", "attribute") == "property":
        _validate_property_bounds(value)
    else:
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


def _validate_property_bounds(value: JsonObject) -> None:
    datatype = value["datatype"]
    bounds = cast(JsonObject, value["bounds"])
    is_numeric = datatype in _NUMERIC_DATATYPES
    for facet in _BOUNDS_FACETS:
        if facet not in bounds:
            continue
        _validate_bound_value(bounds[facet], datatype=datatype, is_numeric=is_numeric)
    if "enumeration" in bounds:
        for item in cast(list[Any], bounds["enumeration"]):
            _validate_bound_value(item, datatype=datatype, is_numeric=is_numeric)


def _validate_bound_value(item: Any, *, datatype: str, is_numeric: bool) -> None:
    if is_numeric:
        if isinstance(item, bool) or not isinstance(item, (int, float)):
            raise RuleIRError(
                f"rule IR bounds value must be numeric for datatype {datatype}"
            )
        if not math.isfinite(float(item)):
            raise RuleIRError("rule IR bounds value must be finite")
        if datatype == "integer" and float(item) != int(item):
            raise RuleIRError("rule IR bounds value must be an integer for datatype")
    elif not isinstance(item, str) or not item:
        raise RuleIRError(
            f"rule IR bounds value must be a non-empty string for datatype {datatype}"
        )
