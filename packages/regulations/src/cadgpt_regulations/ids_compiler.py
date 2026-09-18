"""Deterministic compilation of source-cited native IDS rules.

This module deliberately accepts a small, canonical rule shape.  It is a publication
boundary: missing citation evidence or ambiguous requirement values fail closed before
an IDS artifact is emitted.  A finalized Luna transcript is valid evidence by document
identity, PDF page, transcript revision, and exact transcript text; structural spans are
optional metadata for that evidence kind.
"""

from __future__ import annotations

import hashlib
import html
import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from cadgpt_regulations.jsonio import canonical_bytes
from cadgpt_regulations.source_citation import citation_evidence_kind

IDS_NS = "http://standards.buildingsmart.org/IDS"
XS_NS = "http://www.w3.org/2001/XMLSchema"
XSI_NS = "http://www.w3.org/2001/XMLSchema-instance"
COMPILER_VERSION = "native-ids-citation-v1"
_HASH_RE = re.compile(r"^[0-9a-f]{64}$")


class CompilerError(ValueError):
    """Raised when a rule cannot safely cross the IDS publication boundary."""


@dataclass(frozen=True)
class CompiledRule:
    """Byte-stable IDS and its complete, content-addressed sidecar."""

    rule_id: str
    ids_xml: bytes
    sidecar: Mapping[str, Any]

    @property
    def ids_sha256(self) -> str:
        return hashlib.sha256(self.ids_xml).hexdigest()


def _text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise CompilerError(f"{field} must be a non-empty string")
    return value.strip()


def _citation(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise CompilerError("source_citation must be an object")
    required = (
        "document_key",
        "book_title_fa",
        "edition_fa",
        "document_sha256",
        "pdf_page",
        "exact_text_fa",
        "exact_text_sha256",
        "citation_status",
    )
    missing = [key for key in required if key not in value]
    if missing:
        raise CompilerError(f"source_citation missing: {', '.join(missing)}")
    result = dict(value)
    if result["citation_status"] != "verified":
        raise CompilerError("source_citation.citation_status must be 'verified'")
    evidence_kind = citation_evidence_kind(result)
    if evidence_kind not in {"source_graph", "transcript"}:
        raise CompilerError("source_citation.evidence_kind is unsupported")
    for key in ("document_sha256", "exact_text_sha256"):
        if not isinstance(result[key], str) or not _HASH_RE.fullmatch(result[key]):
            raise CompilerError(f"source_citation.{key} must be a lowercase SHA-256")
    if not isinstance(result["pdf_page"], int) or result["pdf_page"] < 1:
        raise CompilerError("source_citation.pdf_page must be a positive integer")
    for key in ("source_node_ids", "source_span_ids"):
        values = result.get(key, [])
        if not isinstance(values, Sequence) or isinstance(values, (str, bytes)):
            raise CompilerError(f"source_citation.{key} must be a list")
        if evidence_kind == "source_graph" and not values:
            raise CompilerError(f"source_citation.{key} must be a non-empty list")
        result[key] = [_text(item, f"source_citation.{key}[]") for item in values]
    if evidence_kind == "transcript":
        revision_id = result.get("transcript_revision_id")
        transcript_hash = result.get("transcript_sha256")
        if not isinstance(revision_id, str) or not revision_id.strip():
            raise CompilerError(
                "source_citation.transcript_revision_id is required for transcript evidence"
            )
        if not isinstance(transcript_hash, str) or not _HASH_RE.fullmatch(transcript_hash):
            raise CompilerError(
                "source_citation.transcript_sha256 is required for transcript evidence"
            )
    result["evidence_kind"] = evidence_kind
    result["exact_text_fa"] = _text(
        result["exact_text_fa"], "source_citation.exact_text_fa"
    )
    expected = hashlib.sha256(result["exact_text_fa"].encode("utf-8")).hexdigest()
    if result["exact_text_sha256"] != expected:
        raise CompilerError(
            "source_citation.exact_text_sha256 does not match exact_text_fa"
        )
    for key in ("document_key", "book_title_fa", "edition_fa"):
        result[key] = _text(result[key], f"source_citation.{key}")
    page_id = result.get("page_id")
    if page_id is not None:
        result["page_id"] = _text(page_id, "source_citation.page_id")
    else:
        result["page_id"] = f"pdf-page:{result['pdf_page']}"
    return result


def _xml(value: Any) -> str:
    return html.escape(str(value), quote=True)


def _simple(value: Any) -> str:
    return f"<ids:simpleValue>{_xml(value)}</ids:simpleValue>"


def _value_restriction(requirement: Mapping[str, Any]) -> str:
    datatype = str(requirement.get("datatype", "double"))
    base = {
        "double": "xs:double",
        "decimal": "xs:decimal",
        "integer": "xs:integer",
        "string": "xs:string",
    }.get(datatype)
    if base is None:
        raise CompilerError(f"unsupported requirement datatype: {datatype}")
    facets: list[str] = []
    bounds = requirement.get("bounds")
    if bounds is not None:
        if not isinstance(bounds, Mapping):
            raise CompilerError("requirement.bounds must be an object")
        for facet in (
            "minInclusive",
            "minExclusive",
            "maxInclusive",
            "maxExclusive",
            "enumeration",
        ):
            if facet in bounds:
                val = bounds[facet]
                values = (
                    val
                    if facet == "enumeration"
                    and isinstance(val, Sequence)
                    and not isinstance(val, (str, bytes))
                    else [val]
                )
                for item in values:
                    facets.append(f'<xs:{facet} value="{_xml(item)}"/>')
    else:
        comparator = requirement.get("comparator")
        value = requirement.get("value")
        if comparator not in {
            "minInclusive",
            "minExclusive",
            "maxInclusive",
            "maxExclusive",
            "enumeration",
            "exact",
        }:
            raise CompilerError(
                "requirement.comparator must be a supported range comparator"
            )
        if value is None:
            raise CompilerError("requirement.value is required")
        facet = "enumeration" if comparator in {"enumeration", "exact"} else comparator
        facets.append(f'<xs:{facet} value="{_xml(value)}"/>')
    if not facets:
        raise CompilerError("requirement needs a value or at least one bound")
    return f'<xs:restriction base="{base}">' + "".join(facets) + "</xs:restriction>"


def _citation_text(citation: Mapping[str, Any]) -> tuple[str, str]:
    if citation_evidence_kind(citation) == "transcript":
        evidence = (
            f"transcript_revision_id={citation['transcript_revision_id']}; "
            f"transcript_sha256={citation['transcript_sha256']}"
        )
    else:
        evidence = f"source_span_ids={','.join(citation.get('source_span_ids', []))}"
    compact = (
        f"منبع فارسی: {citation['book_title_fa']}; ویرایش {citation['edition_fa']}; "
        f"صفحه PDF {citation['pdf_page']}; page_id={citation['page_id']}; "
        f"{evidence}; source_sha256={citation['document_sha256']}"
    )
    instructions = f"متن دقیق فارسی: «{citation['exact_text_fa']}»"
    return compact, instructions


def compile_native_rule(
    rule: Mapping[str, Any], *, compiler_version: str = COMPILER_VERSION
) -> CompiledRule:
    """Compile one canonical native IDS rule with a verified Persian citation.

    The accepted requirement is an IFC attribute or property with a scalar comparator
    or inclusive/exclusive bounds.  The function has no clock or filesystem dependency.
    """
    if not isinstance(rule, Mapping):
        raise CompilerError("rule must be an object")
    citation = _citation(rule.get("source_citation"))
    requirement = rule.get("requirement")
    if not isinstance(requirement, Mapping):
        raise CompilerError("requirement must be an object")
    kind = requirement.get("kind", "attribute")
    if kind not in {"attribute", "property"}:
        raise CompilerError("only attribute and property requirements are supported")
    entity = _text(
        rule.get(
            "entity",
            rule.get("applicability", {}).get("entity")
            if isinstance(rule.get("applicability"), Mapping)
            else None,
        ),
        "entity",
    )
    target_name = _text(requirement.get("name"), "requirement.name")
    title = _text(rule.get("title", rule.get("rule_key")), "title")
    rule_key = _text(rule.get("rule_key", title), "rule_key")
    ifc_version = rule.get("ifc_version", rule.get("ifc_versions", "IFC4"))
    if isinstance(ifc_version, str):
        ifc_version = [ifc_version]
    if (
        not isinstance(ifc_version, Sequence)
        or isinstance(ifc_version, (str, bytes))
        or not ifc_version
    ):
        raise CompilerError("ifc_version must be a non-empty string or list")
    ifc_version = [_text(item, "ifc_version[]") for item in ifc_version]
    description, instructions = _citation_text(citation)
    req_xml: str
    if kind == "attribute":
        req_xml = (
            '<ids:attribute cardinality="required"><ids:name>'
            + _simple(target_name)
            + "</ids:name><ids:value>"
            + _value_restriction(requirement)
            + "</ids:value></ids:attribute>"
        )
    else:
        property_set = _text(requirement.get("property_set"), "requirement.property_set")
        req_xml = (
            '<ids:property cardinality="required"><ids:propertySet>'
            + _simple(property_set)
            + "</ids:propertySet><ids:baseName>"
            + _simple(target_name)
            + "</ids:baseName><ids:value>"
            + _value_restriction(requirement)
            + "</ids:value></ids:property>"
        )
    versions = _xml(" ".join(ifc_version))
    specification_name = (
        f"{_xml(rule_key)} - {_xml(citation['book_title_fa'])} p. {citation['pdf_page']}"
    )
    xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
        f'<ids:ids xmlns:ids="{IDS_NS}" xmlns:xs="{XS_NS}" xmlns:xsi="{XSI_NS}" '
        f'xsi:schemaLocation="{IDS_NS} {IDS_NS}/1.0/ids.xsd">\n'
        "\t<ids:info>\n"
        f"\t\t<ids:title>{_xml(title)}</ids:title>\n"
        f"\t\t<ids:description>{_xml(description)}</ids:description>\n"
        "\t</ids:info>\n"
        "\t<ids:specifications>\n"
        f'\t\t<ids:specification ifcVersion="{versions}" name="{specification_name}">\n'
        '\t\t\t<ids:applicability maxOccurs="unbounded"><ids:entity><ids:name>'
        + _simple(entity)
        + "</ids:name></ids:entity></ids:applicability>\n"
        "\t\t\t<ids:requirements>" + req_xml + "</ids:requirements>\n"
        f"\t\t\t<ids:instructions>{_xml(instructions)}</ids:instructions>\n"
        "\t\t</ids:specification>\n\t</ids:specifications>\n</ids:ids>\n"
    ).encode("utf-8")
    canonical_rule = json.loads(
        json.dumps(dict(rule), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    )
    identity = hashlib.sha256(canonical_bytes(canonical_rule)).hexdigest()
    rule_id = f"rule-{identity}"
    sidecar = {
        "compiler_version": compiler_version,
        "rule_id": rule_id,
        "ids_sha256": hashlib.sha256(xml).hexdigest(),
        "rule": canonical_rule,
        "source_citation": citation,
    }
    if citation.get("evidence_kind") == "transcript":
        sidecar["source_attestation"] = {
            "decision": "transcript",
            "document_sha256": citation["document_sha256"],
            "transcript_revision_id": citation["transcript_revision_id"],
            "transcript_sha256": citation["transcript_sha256"],
        }
    return CompiledRule(rule_id=rule_id, ids_xml=xml, sidecar=sidecar)
