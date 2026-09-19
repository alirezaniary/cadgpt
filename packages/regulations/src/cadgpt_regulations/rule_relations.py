"""Deterministic occurrence-to-assertion relationships for rule releases."""

from __future__ import annotations

import hashlib
from collections.abc import Iterable, Mapping
from typing import Any, cast

from cadgpt_regulations.jsonio import JsonObject, canonical_bytes
from cadgpt_regulations.rule_ir import validate_rule_ir


def build_occurrence_assertions(
    rules: Iterable[Mapping[str, Any]],
) -> JsonObject:
    """Group equivalent rule occurrences without discarding their citations.

    Semantic identity intentionally excludes rule keys and source citation.  A
    source occurrence remains independently addressable and retains its complete
    verified citation, even when it supports an existing assertion.
    """
    assertions_by_id: dict[str, JsonObject] = {}
    occurrences: list[JsonObject] = []
    for raw_rule in rules:
        rule = validate_rule_ir(raw_rule)
        citation = cast(JsonObject, rule["source_citation"])
        semantic = _semantic_identity(rule)
        assertion_id = hashlib.sha256(canonical_bytes(semantic)).hexdigest()
        occurrence_identity = {
            "assertion_id": assertion_id,
            "rule_key": rule["rule_key"],
            "citation": citation,
        }
        occurrence_id = hashlib.sha256(canonical_bytes(occurrence_identity)).hexdigest()
        occurrence: JsonObject = {
            "schema_version": "rule-occurrence-1.0.0",
            "occurrence_id": occurrence_id,
            "assertion_id": assertion_id,
            "rule_key": rule["rule_key"],
            "source_citation": citation,
        }
        occurrences.append(occurrence)
        assertion = assertions_by_id.get(assertion_id)
        if assertion is None:
            assertion = {
                "schema_version": "rule-assertion-1.0.0",
                "assertion_id": assertion_id,
                "semantic": semantic,
                "occurrence_ids": [],
            }
            assertions_by_id[assertion_id] = assertion
        cast(list[str], assertion["occurrence_ids"]).append(occurrence_id)
    assertions = sorted(
        assertions_by_id.values(), key=lambda item: cast(str, item["assertion_id"])
    )
    return {
        "schema_version": "rule-relations-1.0.0",
        "assertions": assertions,
        "occurrences": occurrences,
        "summary": {
            "input_occurrences": len(occurrences),
            "assertions": len(assertions),
            "duplicates_collapsed": len(occurrences) - len(assertions),
        },
    }


def _semantic_identity(rule: JsonObject) -> JsonObject:
    """Return the fields that decide whether two occurrences are the same assertion.

    Two requirement kinds exist (T-0105): the original flat ``attribute`` shape, kept
    byte-for-byte as before so existing assertion IDs do not move, and the newer
    ``property``/``bounds`` shape, which has no ``attribute``/``comparator``/``value``
    keys at all and needs its own identity fields instead.
    """
    if rule.get("requirement_kind", "attribute") == "property":
        return {
            "requirement_kind": "property",
            "entity": str(rule["entity"]).upper(),
            "property_set": rule["property_set"],
            "property_name": rule["property_name"],
            "datatype": rule["datatype"],
            "bounds": rule["bounds"],
            "unit": rule.get("unit"),
            "ifc_versions": sorted(cast(list[str], rule["ifc_versions"])),
        }
    return {
        "entity": str(rule["entity"]).upper(),
        "attribute": rule["attribute"],
        "comparator": rule["comparator"],
        "value": rule["value"],
        "unit": rule.get("unit"),
        "ifc_versions": sorted(cast(list[str], rule["ifc_versions"])),
    }
