"""Check an IFC model against an IDS rule set and report three-valued results.

`ifctester` does the evaluation. This module does the two things it does not.

**It separates "violates the rule" from "lacks the data the rule needs."** `ifctester`
reports both as a failure. Telling an architect they have 113 code violations when they
have 12 violations and 101 unknowns is the difference this module exists to make.

**It refuses to pass a rule that checked nothing.** A specification whose applicability
matched zero elements has established no compliance, and `ifctester` reports it as a pass.
Whether a specification applies is a separate three-valued question from whether it passed,
and it is answered from the matched-subject count and the IDS cardinality — never from
`ifctester`'s own status alone.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any

import ifcopenshell
import ifctester.ids


class Status(StrEnum):
    """A result is never two-valued. INDETERMINATE never becomes PASS."""

    PASS = "PASS"
    FAIL = "FAIL"
    INDETERMINATE = "INDETERMINATE"


class Applicability(StrEnum):
    """Whether the rule had anything to say about this model at all."""

    APPLIES = "APPLIES"
    DOES_NOT_APPLY = "DOES_NOT_APPLY"
    UNDETERMINED = "UNDETERMINED_APPLICABILITY"


# ifctester discards its structured `reason` dict at ids.py:312, keeping only the rendered
# string, so the datum-present question has to be asked of that string. These patterns cover
# every reason ifctester 0.8.5 can emit; test_check.py asserts that exhaustively, so an
# upgrade that adds or reworks a reason breaks the suite instead of silently misreporting.

_NOT_EVALUABLE: tuple[re.Pattern[str], ...] = tuple(
    re.compile(p)
    for p in (
        r"^The required attribute did not exist$",
        r"^The attribute value .* is empty$",
        r"^An invalid attribute name was specified in the IDS$",
        r"^The entity has no classification$",
        r"^The entity has no relationship$",
        r"^The required property set does not exist$",
        r"^The property set does not contain the required property$",
        r"does not match the required data type of",
        r"^The entity has no material$",
    )
)

_VIOLATION: tuple[re.Pattern[str], ...] = tuple(
    re.compile(p)
    for p in (
        r"^The entity class .* does not meet the required IFC class$",
        r"^The predefined type .* does not meet the required type$",
        r"^The attribute value .* does not match the requirement$",
        r"^The attribute value should not have met the requirement$",
        r"^The references .* do not match the requirements$",
        r"^The systems .* do not match the requirements$",
        r"^The classification should not have met the requirement$",
        r"^The entity has a relationship with incorrect entities",
        r"^The entity has a relationship with incorrect predefined type",
        r"^The relationship should not have met the requirement$",
        r"^The property values? .* do(es)? not match the requirements?$",
        r"^The property should not have met the requirement$",
        r"^The material names and categories of .* does not match the requirement$",
        r"^The material should not have met the requirement$",
    )
)


def classify(reason: str) -> Status:
    """Map one ifctester failure reason to FAIL or INDETERMINATE.

    A reason we do not recognise is INDETERMINATE, never FAIL: we do not assert a
    violation we cannot justify. The raw reason travels with the outcome either way,
    so nothing is hidden from the reader.
    """
    for pattern in _NOT_EVALUABLE:
        if pattern.search(reason):
            return Status.INDETERMINATE
    for pattern in _VIOLATION:
        if pattern.search(reason):
            return Status.FAIL
    return Status.INDETERMINATE


def is_recognised(reason: str) -> bool:
    """Whether `reason` matches a known ifctester reason. Used by the coverage test."""
    return any(p.search(reason) for p in (*_NOT_EVALUABLE, *_VIOLATION))


@dataclass(frozen=True)
class EntityOutcome:
    """One element that did not pass, and why."""

    global_id: str | None
    ifc_class: str
    status: Status
    reason: str


@dataclass(frozen=True)
class RequirementOutcome:
    description: str
    status: Status
    passed: int
    failed: int
    indeterminate: int
    entities: tuple[EntityOutcome, ...]


@dataclass(frozen=True)
class SpecificationOutcome:
    name: str
    description: str
    applicability: Applicability
    status: Status
    cardinality: str
    matched: int
    reason: str
    passed: int
    failed: int
    indeterminate: int
    requirements: tuple[RequirementOutcome, ...]


@dataclass(frozen=True)
class Report:
    ifc_filename: str
    ids_title: str
    status: Status
    specifications_passed: int
    specifications_failed: int
    specifications_indeterminate: int
    passed: int
    failed: int
    indeterminate: int
    specifications: tuple[SpecificationOutcome, ...]


def _aggregate(failed: int, indeterminate: int) -> Status:
    """A known violation decides FAIL; otherwise an unknown prevents PASS."""
    if failed:
        return Status.FAIL
    if indeterminate:
        return Status.INDETERMINATE
    return Status.PASS


def _outcome(element: Any, reason: str) -> EntityOutcome:
    return EntityOutcome(
        global_id=getattr(element, "GlobalId", None),
        ifc_class=element.is_a(),
        status=classify(reason),
        reason=reason,
    )


def _requirement(facet: Any) -> RequirementOutcome:
    entities = tuple(_outcome(f["element"], f["reason"]) for f in facet.failures)
    failed = sum(1 for e in entities if e.status is Status.FAIL)
    indeterminate = sum(1 for e in entities if e.status is Status.INDETERMINATE)
    return RequirementOutcome(
        description=str(facet),
        status=_aggregate(failed, indeterminate),
        passed=len(facet.passed_entities),
        failed=failed,
        indeterminate=indeterminate,
        entities=entities,
    )


def _judge(
    cardinality: str, matched: int, schema_matches: bool, failed: int, indeterminate: int
) -> tuple[Applicability, Status, str]:
    """Decide applicability and status from subjects and cardinality, not evidence alone.

    The zero-subject cases are the ones `ifctester` gets wrong for our purposes: it reports
    a specification that matched nothing as a pass.
    """
    if not schema_matches:
        return (
            Applicability.UNDETERMINED,
            Status.INDETERMINATE,
            "The rule is written for a different IFC schema than this model uses, "
            "so whether it applies could not be established.",
        )

    if matched == 0:
        if cardinality == "required":
            return (
                Applicability.APPLIES,
                Status.FAIL,
                "The rule requires matching elements and the model contains none.",
            )
        if cardinality == "prohibited":
            return (
                Applicability.APPLIES,
                Status.PASS,
                "The rule prohibits such elements and the model contains none.",
            )
        return (
            Applicability.DOES_NOT_APPLY,
            Status.INDETERMINATE,
            "No element matched this rule, so nothing was checked. The model may contain "
            "none, or may not describe them the way the rule expects.",
        )

    if cardinality == "prohibited":
        return (
            Applicability.APPLIES,
            Status.FAIL,
            f"The rule prohibits these elements and the model contains {matched}.",
        )

    return Applicability.APPLIES, _aggregate(failed, indeterminate), ""


def _specification(spec: Any) -> SpecificationOutcome:
    requirements = tuple(_requirement(f) for f in spec.requirements)
    failed = sum(r.failed for r in requirements)
    indeterminate = sum(r.indeterminate for r in requirements)
    matched = len(spec.applicable_entities)

    # is_ifc_version is None when no version filter applies, False on a real mismatch.
    schema_matches = spec.is_ifc_version is not False
    cardinality = str(spec.get_usage())
    applicability, status, reason = _judge(
        cardinality, matched, schema_matches, failed, indeterminate
    )

    return SpecificationOutcome(
        name=spec.name or "",
        description=spec.description or "",
        applicability=applicability,
        status=status,
        cardinality=cardinality,
        matched=matched,
        reason=reason,
        passed=sum(r.passed for r in requirements),
        failed=failed,
        indeterminate=indeterminate,
        requirements=requirements,
    )


def run_check(ifc_path: Path, ids_path: Path) -> Report:
    """Evaluate `ifc_path` against `ids_path` and return a three-valued report.

    Both files are read from disk by the inherited libraries. Nothing is fetched.
    """
    specs = ifctester.ids.open(str(ids_path), validate=True)
    model = ifcopenshell.open(str(ifc_path))
    specs.validate(model)

    specifications = tuple(_specification(s) for s in specs.specifications)
    by_status = [s.status for s in specifications]
    specs_failed = by_status.count(Status.FAIL)
    specs_indeterminate = by_status.count(Status.INDETERMINATE)

    return Report(
        ifc_filename=Path(ifc_path).name,
        ids_title=str(specs.info.get("title", "")),
        status=_aggregate(specs_failed, specs_indeterminate),
        specifications_passed=by_status.count(Status.PASS),
        specifications_failed=specs_failed,
        specifications_indeterminate=specs_indeterminate,
        passed=sum(s.passed for s in specifications),
        failed=sum(s.failed for s in specifications),
        indeterminate=sum(s.indeterminate for s in specifications),
        specifications=specifications,
    )
