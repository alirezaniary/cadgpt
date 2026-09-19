"""Deterministic compilation of a small, citation-bearing native IDS subset.

One compiler, two requirement kinds. ``compile_native_attribute_rule`` is the sole
entry point: a rule IR with a flat ``attribute`` field compiles through the original
attribute path (kept byte-for-byte identical to preserve downstream ``rule_id``
hashes); a rule IR with ``requirement_kind: "property"`` compiles through the
property path, which supports a property set, a base name, four IDS datatypes, and a
bounds object carrying one or more XSD facets (``minInclusive``, ``maxInclusive``,
``enumeration``, ...). This module used to have a second, unwired duplicate compiler
module with the richer property/bounds capability; that capability is ported in here
and the duplicate is retired (T-0105).
"""

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

_SCALAR_COMPARATORS = frozenset({"eq", "equals", "gt", "gte", "lt", "lte"})
_XS_BASE_BY_DATATYPE = {
    "double": "xs:double",
    "decimal": "xs:decimal",
    "integer": "xs:integer",
    "string": "xs:string",
}
_BOUNDS_FACET_ORDER = (
    "minInclusive",
    "minExclusive",
    "maxInclusive",
    "maxExclusive",
    "enumeration",
)


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
    """Compile one reviewed, source-cited native IDS rule.

    Two deterministic requirement kinds are supported: an IFC entity's attribute
    constrained by a scalar comparator (``requirement_kind`` absent or "attribute"),
    and an IFC property in a named property set constrained by a bounds object
    (``requirement_kind: "property"``). Unsupported shapes must be added as separate
    compiler classes rather than silently approximated.
    """
    requirement_kind = rule.get("requirement_kind", "attribute")
    if requirement_kind == "attribute":
        return _compile_attribute_rule(rule, compiler_version=compiler_version)
    if requirement_kind == "property":
        return _compile_property_rule(rule, compiler_version=compiler_version)
    raise RuleCompileError(f"unsupported requirement_kind: {requirement_kind!r}")


def _compile_attribute_rule(
    rule: Mapping[str, Any], *, compiler_version: str
) -> CompiledRule:
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
    citation_obj = _validated_citation(rule)
    raw_comparator = rule.get("comparator")
    if isinstance(raw_comparator, str) and raw_comparator not in _SCALAR_COMPARATORS:
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
    if comparator not in _SCALAR_COMPARATORS:
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
    root, specification = _ids_root_and_specification(
        rule, citation_obj=citation_obj, rule_id=rule_id
    )
    applicability = ET.SubElement(
        specification, f"{{{IDS}}}applicability", {"maxOccurs": "unbounded"}
    )
    _append_entity(applicability, entity)
    requirements = ET.SubElement(specification, f"{{{IDS}}}requirements")
    attribute_node = ET.SubElement(
        requirements, f"{{{IDS}}}attribute", {"cardinality": "required"}
    )
    ET.SubElement(
        ET.SubElement(attribute_node, f"{{{IDS}}}name"), f"{{{IDS}}}simpleValue"
    ).text = attribute
    value_node = ET.SubElement(attribute_node, f"{{{IDS}}}value")
    restriction = ET.SubElement(value_node, f"{{{XS}}}restriction", {"base": "xs:double"})
    facet, facet_value = _scalar_facet(comparator, value)
    ET.SubElement(restriction, f"{{{XS}}}{facet}", {"value": facet_value})
    ids_xml = ET.tostring(root, encoding="utf-8", xml_declaration=True)
    return CompiledRule(
        rule_id=rule_id,
        ids_xml=ids_xml,
        sidecar=_build_sidecar(
            rule_id=rule_id,
            ids_xml=ids_xml,
            compiler_version=compiler_version,
            canonical_rule=canonical_rule,
            citation_obj=citation_obj,
        ),
    )


def _compile_property_rule(
    rule: Mapping[str, Any], *, compiler_version: str
) -> CompiledRule:
    required = (
        "rule_key",
        "title_fa",
        "ifc_versions",
        "entity",
        "property_set",
        "property_name",
        "datatype",
        "bounds",
        "source_citation",
    )
    missing = [field for field in required if field not in rule]
    if missing:
        raise RuleCompileError(f"rule is missing required fields: {', '.join(missing)}")
    citation_obj = _validated_citation(rule)
    raw_datatype = rule.get("datatype")
    if isinstance(raw_datatype, str) and raw_datatype not in _XS_BASE_BY_DATATYPE:
        raise RuleCompileError(f"unsupported requirement datatype: {raw_datatype}")
    try:
        validate_rule_ir(rule)
    except RuleIRError as exc:
        raise RuleCompileError(str(exc)) from exc
    if not isinstance(rule["ifc_versions"], list) or not rule["ifc_versions"]:
        raise RuleCompileError("ifc_versions must be a non-empty list")
    if not all(isinstance(version, str) and version for version in rule["ifc_versions"]):
        raise RuleCompileError("ifc_versions must contain non-empty strings")
    entity = _required_string(rule, "entity").upper()
    property_set = _required_string(rule, "property_set")
    property_name = _required_string(rule, "property_name")
    datatype = _required_string(rule, "datatype")
    if datatype not in _XS_BASE_BY_DATATYPE:
        raise RuleCompileError(f"unsupported requirement datatype: {datatype}")
    bounds = rule["bounds"]
    if not isinstance(bounds, Mapping) or not bounds:
        raise RuleCompileError("bounds must be a non-empty object")

    canonical_rule: JsonObject = {
        "schema_version": "rule-ir-1.0.0",
        "rule_key": rule["rule_key"],
        "title_fa": rule["title_fa"],
        "ifc_versions": list(rule["ifc_versions"]),
        "entity": entity,
        "requirement_kind": "property",
        "property_set": property_set,
        "property_name": property_name,
        "datatype": datatype,
        "bounds": _canonical_bounds(bounds),
        "unit": rule.get("unit"),
        "source_citation": citation_obj,
    }
    rule_id = hashlib.sha256(canonical_bytes(canonical_rule)).hexdigest()
    root, specification = _ids_root_and_specification(
        rule, citation_obj=citation_obj, rule_id=rule_id
    )
    applicability = ET.SubElement(
        specification, f"{{{IDS}}}applicability", {"maxOccurs": "unbounded"}
    )
    _append_entity(applicability, entity)
    requirements = ET.SubElement(specification, f"{{{IDS}}}requirements")
    property_node = ET.SubElement(
        requirements, f"{{{IDS}}}property", {"cardinality": "required"}
    )
    ET.SubElement(
        ET.SubElement(property_node, f"{{{IDS}}}propertySet"), f"{{{IDS}}}simpleValue"
    ).text = property_set
    ET.SubElement(
        ET.SubElement(property_node, f"{{{IDS}}}baseName"), f"{{{IDS}}}simpleValue"
    ).text = property_name
    value_node = ET.SubElement(property_node, f"{{{IDS}}}value")
    restriction = ET.SubElement(
        value_node, f"{{{XS}}}restriction", {"base": _XS_BASE_BY_DATATYPE[datatype]}
    )
    for facet, rendered in _bounds_facets(bounds):
        ET.SubElement(restriction, f"{{{XS}}}{facet}", {"value": rendered})
    ids_xml = ET.tostring(root, encoding="utf-8", xml_declaration=True)
    return CompiledRule(
        rule_id=rule_id,
        ids_xml=ids_xml,
        sidecar=_build_sidecar(
            rule_id=rule_id,
            ids_xml=ids_xml,
            compiler_version=compiler_version,
            canonical_rule=canonical_rule,
            citation_obj=citation_obj,
        ),
    )


def _validated_citation(rule: Mapping[str, Any]) -> JsonObject:
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
    return citation_obj


def _ids_root_and_specification(
    rule: Mapping[str, Any], *, citation_obj: JsonObject, rule_id: str
) -> tuple[ET.Element, ET.Element]:
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
    return root, specification


def _append_entity(applicability: ET.Element, entity: str) -> None:
    entity_node = ET.SubElement(applicability, f"{{{IDS}}}entity")
    ET.SubElement(
        ET.SubElement(entity_node, f"{{{IDS}}}name"), f"{{{IDS}}}simpleValue"
    ).text = entity


def _build_sidecar(
    *,
    rule_id: str,
    ids_xml: bytes,
    compiler_version: str,
    canonical_rule: JsonObject,
    citation_obj: JsonObject,
) -> JsonObject:
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
    return sidecar


def _canonical_bounds(bounds: Mapping[str, Any]) -> JsonObject:
    result: JsonObject = {}
    for facet in _BOUNDS_FACET_ORDER:
        if facet not in bounds:
            continue
        value = bounds[facet]
        result[facet] = list(value) if facet == "enumeration" else value
    return result


def _bounds_facets(bounds: Mapping[str, Any]) -> list[tuple[str, str]]:
    facets: list[tuple[str, str]] = []
    seen = set(bounds) - set(_BOUNDS_FACET_ORDER)
    if seen:
        raise RuleCompileError(f"unsupported bounds facet(s): {', '.join(sorted(seen))}")
    for facet in _BOUNDS_FACET_ORDER:
        if facet not in bounds:
            continue
        if facet == "enumeration":
            values = bounds[facet]
            if not isinstance(values, (list, tuple)) or not values:
                raise RuleCompileError("bounds.enumeration must be a non-empty list")
            for item in values:
                facets.append(("enumeration", str(item)))
        else:
            facets.append((facet, str(bounds[facet])))
    if not facets:
        raise RuleCompileError("bounds must declare at least one facet")
    return facets


def _scalar_facet(comparator: str, value: int | float) -> tuple[str, str]:
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
