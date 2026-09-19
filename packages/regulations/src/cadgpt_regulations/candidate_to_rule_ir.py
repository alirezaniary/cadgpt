"""Join a provisional candidate to its verified citation and its IFC target.

This is the missing link named in T-0107: every stage from a Persian transcript to a
compiled, source-cited IDS file already existed, but nothing called
``transcript_citation.make_transcript_citation`` outside a test, and no candidate
carried an IFC target at all. This module does exactly two things per candidate,
deterministically and without a model in the loop:

1. Re-derive the candidate's citation from its pinned transcript revision and
   require it to come back ``verified``. A candidate whose transcript revision no
   longer re-attests (document identity, source hash, exact text, or page) is
   **rejected outright** -- this module raises rather than emitting a soft
   "unmapped" record, because that failure means the evidence changed underneath
   the candidate, not that nobody has authored a mapping for it yet.
2. Look up the candidate's ``(document_key, rule_key)`` in the committed IFC
   mapping. A hit produces a ``rule-ir-1.0.0`` document ready for
   ``compile_native_attribute_rule``. A miss is not an error and is never guessed
   at: it is emitted as an unmapped record carrying a reason code, so a candidate
   we cannot yet express stays visibly unexpressed rather than silently dropped.

I1 holds by construction here: nothing in this module calls an inference client,
and the mapping is committed data read the same way on every run. Compiling a
prose statement into an IFC target is authoring work a human does once, ahead of
time, in the mapping file -- never something this module infers from
``statement_fa``.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, cast

from cadgpt_regulations.errors import RegulationsError
from cadgpt_regulations.jsonio import JsonObject, validate_schema
from cadgpt_regulations.provisional_rule import (
    validate_provisional_rule,
    validate_transcript_revision,
)
from cadgpt_regulations.resources import load_packaged_json
from cadgpt_regulations.rule_ir import RuleIRError, validate_rule_ir
from cadgpt_regulations.transcript_citation import (
    TranscriptCitationError,
    make_transcript_citation,
)

_ATTRIBUTE_ONLY_FIELDS = ("attribute", "comparator", "value")
_PROPERTY_ONLY_FIELDS = ("property_set", "property_name", "datatype", "bounds")


class CandidateToRuleIRError(RegulationsError):
    """Raised when a candidate cannot be safely joined to a compiled rule IR."""


def validate_ifc_mapping(mapping: Mapping[str, Any]) -> JsonObject:
    """Validate the committed candidate-to-IFC-target mapping file.

    The mapping is keyed by ``(document_key, rule_key)`` because two documents may
    reuse the same rule-key slug. Each entry gives exactly the target the surviving
    compiler (T-0105) can express: an entity, an attribute/comparator/value triple
    or a property/bounds requirement, an optional unit, and the IFC versions it
    applies to. Nothing here is inferred; this only checks shape and uniqueness.
    """
    value: JsonObject = dict(mapping)
    try:
        validate_schema(
            value,
            load_packaged_json(
                "cadgpt_regulations.schemas", "ifc-target-mapping.schema.json"
            ),
            description="IFC target mapping",
        )
    except RegulationsError as exc:
        raise CandidateToRuleIRError(str(exc)) from exc
    seen: set[tuple[str, str]] = set()
    for entry in cast(list[JsonObject], value["entries"]):
        key = (cast(str, entry["document_key"]), cast(str, entry["rule_key"]))
        if key in seen:
            raise CandidateToRuleIRError(
                f"duplicate IFC mapping entry for document_key/rule_key: {key[0]}/{key[1]}"
            )
        seen.add(key)
    return value


def _mapping_index(mapping: Mapping[str, Any]) -> dict[tuple[str, str], JsonObject]:
    return {
        (cast(str, entry["document_key"]), cast(str, entry["rule_key"])): entry
        for entry in cast(list[JsonObject], mapping["entries"])
    }


def _index_transcript_revisions(
    revisions: Sequence[Mapping[str, Any]],
) -> dict[str, JsonObject]:
    indexed: dict[str, JsonObject] = {}
    for revision in revisions:
        validate_transcript_revision(revision)
        revision_id = cast(str, revision["revision_id"])
        indexed[revision_id] = cast(JsonObject, dict(revision))
    return indexed


def _verified_citation(
    candidate: Mapping[str, Any], revisions_by_id: Mapping[str, JsonObject]
) -> JsonObject:
    candidate_id = cast(str, candidate.get("candidate_id", "<unknown>"))
    revision_id = candidate.get("transcript_revision_id")
    if not isinstance(revision_id, str) or revision_id not in revisions_by_id:
        raise CandidateToRuleIRError(
            f"candidate {candidate_id} has no matching transcript revision "
            f"({revision_id!r})"
        )
    revision = revisions_by_id[revision_id]
    rule = candidate.get("rule")
    existing_citation = rule.get("source_citation") if isinstance(rule, Mapping) else None
    if not isinstance(existing_citation, Mapping):
        raise CandidateToRuleIRError(
            f"candidate {candidate_id} carries no candidate citation to re-derive from"
        )
    book_title_fa = existing_citation.get("book_title_fa")
    edition_fa = existing_citation.get("edition_fa")
    if not isinstance(book_title_fa, str) or not isinstance(edition_fa, str):
        raise CandidateToRuleIRError(
            f"candidate {candidate_id} citation is missing book_title_fa/edition_fa"
        )
    try:
        return make_transcript_citation(
            revision, book_title_fa=book_title_fa, edition_fa=edition_fa
        )
    except TranscriptCitationError as exc:
        raise CandidateToRuleIRError(
            f"candidate {candidate_id} rejected outright: transcript revision "
            f"failed re-attestation: {exc}"
        ) from exc


def _build_rule_ir(
    rule: Mapping[str, Any], mapping_entry: Mapping[str, Any], citation: JsonObject
) -> JsonObject:
    rule_key = rule.get("rule_key")
    title_fa = rule.get("title_fa")
    if not isinstance(rule_key, str) or not rule_key:
        raise CandidateToRuleIRError("candidate rule has no rule_key to compile")
    if not isinstance(title_fa, str) or not title_fa:
        raise CandidateToRuleIRError(
            f"candidate rule {rule_key} has no title_fa to compile"
        )
    requirement_kind = mapping_entry.get("requirement_kind", "attribute")
    rule_ir: JsonObject = {
        "schema_version": "rule-ir-1.0.0",
        "rule_key": rule_key,
        "title_fa": title_fa,
        "ifc_versions": list(cast(list[str], mapping_entry["ifc_versions"])),
        "entity": mapping_entry["entity"],
        "source_citation": citation,
    }
    if requirement_kind == "attribute":
        for field in _ATTRIBUTE_ONLY_FIELDS:
            rule_ir[field] = mapping_entry[field]
        rule_ir["unit"] = mapping_entry.get("unit")
    elif requirement_kind == "property":
        rule_ir["requirement_kind"] = "property"
        for field in _PROPERTY_ONLY_FIELDS:
            rule_ir[field] = mapping_entry[field]
        rule_ir["unit"] = mapping_entry.get("unit")
    else:  # pragma: no cover - the mapping schema already forbids this
        raise CandidateToRuleIRError(
            f"unsupported requirement_kind in mapping entry: {requirement_kind!r}"
        )
    try:
        return validate_rule_ir(rule_ir)
    except RuleIRError as exc:
        raise CandidateToRuleIRError(
            f"mapped rule {rule_key} does not compile to a valid rule IR: {exc}"
        ) from exc


def _unmapped_record(candidate: Mapping[str, Any], *, reason_code: str) -> JsonObject:
    rule = cast(Mapping[str, Any], candidate.get("rule", {}))
    return {
        "candidate_id": candidate.get("candidate_id"),
        "document_key": candidate.get("document_key"),
        "rule_key": rule.get("rule_key"),
        "implementation_type": rule.get("implementation_type"),
        "reason_code": reason_code,
    }


def build_candidate_to_rule_ir_batch(
    candidates: Sequence[Mapping[str, Any]],
    transcript_revisions: Sequence[Mapping[str, Any]],
    mapping: Mapping[str, Any],
) -> JsonObject:
    """Join every candidate to a verified citation and, where mapped, a rule IR.

    Every candidate produces exactly one outcome: a compiled ``rule-ir-1.0.0``
    document (mapped), or an unmapped record with a reason code (unmapped). A
    candidate whose transcript revision fails re-attestation raises immediately --
    it is rejected outright, never silently downgraded to "unmapped".
    """
    validated_mapping = validate_ifc_mapping(mapping)
    index = _mapping_index(validated_mapping)
    revisions_by_id = _index_transcript_revisions(transcript_revisions)

    mapped: list[JsonObject] = []
    unmapped: list[JsonObject] = []
    for candidate in candidates:
        validate_provisional_rule(candidate)
        citation = _verified_citation(candidate, revisions_by_id)
        rule = cast(Mapping[str, Any], candidate["rule"])
        rule_key = rule.get("rule_key")
        document_key = cast(str, candidate["document_key"])
        if not isinstance(rule_key, str) or not rule_key:
            raise CandidateToRuleIRError(
                f"candidate {candidate['candidate_id']} rule has no rule_key"
            )
        entry = index.get((document_key, rule_key))
        if entry is None:
            unmapped.append(_unmapped_record(candidate, reason_code="no_mapping_entry"))
            continue
        mapped.append(_build_rule_ir(rule, entry, citation))

    mapped.sort(
        key=lambda item: (
            cast(str, item["source_citation"]["document_key"]),
            cast(str, item["rule_key"]),
        )
    )
    unmapped.sort(
        key=lambda item: (
            cast(str, item["document_key"] or ""),
            cast(str, item["rule_key"] or ""),
        )
    )
    return {
        "schema_version": "candidate-to-rule-ir-1.0.0",
        "mapped": mapped,
        "unmapped": unmapped,
        "summary": {
            "candidates": len(candidates),
            "mapped": len(mapped),
            "unmapped": len(unmapped),
        },
    }


__all__ = [
    "CandidateToRuleIRError",
    "build_candidate_to_rule_ir_batch",
    "validate_ifc_mapping",
]
