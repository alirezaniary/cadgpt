"""Deterministic compilation of a small, citation-bearing native IDS subset."""

from __future__ import annotations

import hashlib
import math
import xml.etree.ElementTree as ET
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, cast

from cadgpt_regulations.citation import (
    citation_description,
    citation_hash,
    citation_instructions,
    validate_source_citation,
)
from cadgpt_regulations.errors import RegulationsError
from cadgpt_regulations.jsonio import JsonObject, canonical_bytes
from cadgpt_regulations.rule_ir import RuleIRError, validate_rule_ir
from cadgpt_regulations.source_citation import citation_evidence_kind

IDS = "http://standards.buildingsmart.org/IDS"
XS = "http://www.w3.org/2001/XMLSchema"
ET.register_namespace("ids", IDS)
ET.register_namespace("xs", XS)
ET.register_namespace("xsi", "http://www.w3.org/2001/XMLSchema-instance")


class RuleCompileError(RegulationsError):
    """Raised when a canonical rule cannot be compiled safely."""


@dataclass(frozen=True, slots=True)
class CompiledRule:
    rule_id: str
    ids_xml: bytes
    sidecar: JsonObject

    @property
    def ids_sha256(self) -> str:
        return hashlib.sha256(self.ids_xml).hexdigest()


def compile_native_attribute_rule(
    rule: Mapping[str, Any], *, compiler_version: str = "native-ids-1.0.0"
) -> CompiledRule:
    """Compile one reviewed attribute-range rule and inject its source citation.

    This first vertical slice deliberately supports one deterministic target only:
    an IFC entity's attribute constrained by a scalar comparator. Unsupported shapes
    must be added as separate compiler classes rather than silently approximated.
    """
    required = (
        "rule_key",
        "title_fa",
        "ifc_versions",
        "entity",
        "attribute",
        "comparator",
        "value",
        "source_citation",
    )
    missing = [field for field in required if field not in rule]
    if missing:
        raise RuleCompileError(f"rule is missing required fields: {', '.join(missing)}")
    citation = rule["source_citation"]
    if not isinstance(citation, dict):
        raise RuleCompileError("rule source_citation must be an object")
    citation_obj = cast(JsonObject, citation)
    validate_source_citation(citation_obj)
    if (
        citation_evidence_kind(citation_obj) == "transcript"
        and "evidence_kind" not in citation_obj
    ):
        citation_obj = {**citation_obj, "evidence_kind": "transcript"}
    raw_comparator = rule.get("comparator")
    if isinstance(raw_comparator, str) and raw_comparator not in {
        "eq",
        "equals",
        "gt",
        "gte",
        "lt",
        "lte",
    }:
        raise RuleCompileError(f"unsupported attribute comparator: {raw_comparator}")
    try:
        validate_rule_ir(rule)
    except RuleIRError as exc:
        raise RuleCompileError(str(exc)) from exc
    if not isinstance(rule["ifc_versions"], list) or not rule["ifc_versions"]:
        raise RuleCompileError("ifc_versions must be a non-empty list")
    if not all(isinstance(version, str) and version for version in rule["ifc_versions"]):
        raise RuleCompileError("ifc_versions must contain non-empty strings")
    entity = _required_string(rule, "entity").upper()
    attribute = _required_string(rule, "attribute")
    comparator = _required_string(rule, "comparator")
    value = rule["value"]
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
    ):
        raise RuleCompileError("value must be a finite number")
    if comparator not in {"eq", "equals", "gt", "gte", "lt", "lte"}:
        raise RuleCompileError(f"unsupported attribute comparator: {comparator}")

    canonical_rule: JsonObject = {
        "schema_version": "rule-ir-1.0.0",
        "rule_key": rule["rule_key"],
        "title_fa": rule["title_fa"],
        "ifc_versions": list(rule["ifc_versions"]),
        "entity": entity,
        "attribute": attribute,
        "comparator": comparator,
        "value": value,
        "unit": rule.get("unit"),
        "source_citation": citation_obj,
    }
    rule_id = hashlib.sha256(canonical_bytes(canonical_rule)).hexdigest()
    root = ET.Element(
        f"{{{IDS}}}ids",
        {
            "{http://www.w3.org/2001/XMLSchema-instance}schemaLocation": (
                f"{IDS} {IDS}/1.0/ids.xsd"
            )
        },
    )
    info = ET.SubElement(root, f"{{{IDS}}}info")
    ET.SubElement(info, f"{{{IDS}}}title").text = str(rule["title_fa"])
    ET.SubElement(
        info, f"{{{IDS}}}description"
    ).text = f"Source-cited rule release; rule_id={rule_id}"
    specifications = ET.SubElement(root, f"{{{IDS}}}specifications")
    specification = ET.SubElement(
        specifications,
        f"{{{IDS}}}specification",
        {
            "ifcVersion": " ".join(cast(list[str], rule["ifc_versions"])),
            "name": f"{rule['rule_key']} - p.{citation_obj['pdf_page']}",
            "description": citation_description(citation_obj),
            "instructions": citation_instructions(citation_obj),
        },
    )
    applicability = ET.SubElement(
        specification, f"{{{IDS}}}applicability", {"maxOccurs": "unbounded"}
    )
    entity_node = ET.SubElement(applicability, f"{{{IDS}}}entity")
    ET.SubElement(
        ET.SubElement(entity_node, f"{{{IDS}}}name"), f"{{{IDS}}}simpleValue"
    ).text = entity
    requirements = ET.SubElement(specification, f"{{{IDS}}}requirements")
    attribute_node = ET.SubElement(
        requirements, f"{{{IDS}}}attribute", {"cardinality": "required"}
    )
    ET.SubElement(
        ET.SubElement(attribute_node, f"{{{IDS}}}name"), f"{{{IDS}}}simpleValue"
    ).text = attribute
    value_node = ET.SubElement(attribute_node, f"{{{IDS}}}value")
    restriction = ET.SubElement(value_node, f"{{{XS}}}restriction", {"base": "xs:double"})
    facet, facet_value = _facet(comparator, value)
    ET.SubElement(restriction, f"{{{XS}}}{facet}", {"value": facet_value})
    ids_xml = ET.tostring(root, encoding="utf-8", xml_declaration=True)
    sidecar: JsonObject = {
        "schema_version": "compiled-rule-1.0.0",
        "rule_id": rule_id,
        "compiler_version": compiler_version,
        "ids_sha256": hashlib.sha256(ids_xml).hexdigest(),
        "canonical_rule": canonical_rule,
        "source_citation": citation_obj,
        "source_citation_sha256": citation_hash(citation_obj),
    }
    if citation_evidence_kind(citation_obj) == "transcript":
        sidecar["source_attestation"] = {
            "decision": "transcript",
            "document_sha256": citation_obj["document_sha256"],
            "transcript_revision_id": citation_obj["transcript_revision_id"],
            "transcript_sha256": citation_obj["transcript_sha256"],
        }
    return CompiledRule(rule_id=rule_id, ids_xml=ids_xml, sidecar=sidecar)


def _facet(comparator: str, value: int | float) -> tuple[str, str]:
    rendered = str(value)
    return {
        "eq": ("enumeration", rendered),
        "equals": ("enumeration", rendered),
        "gt": ("minExclusive", rendered),
        "gte": ("minInclusive", rendered),
        "lt": ("maxExclusive", rendered),
        "lte": ("maxInclusive", rendered),
    }[comparator]


def _required_string(rule: Mapping[str, Any], field: str) -> str:
    value = rule.get(field)
    if not isinstance(value, str) or not value:
        raise RuleCompileError(f"rule {field} must be a non-empty string")
    return value
