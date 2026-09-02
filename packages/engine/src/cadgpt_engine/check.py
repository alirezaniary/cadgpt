"""Evaluate an IFC model against an IDS rule set and report three-valued results.

`ifctester` does the evaluation. This module does the two things it does not.

**It separates "violates the rule" from "lacks the data the rule needs."** `ifctester`
reports both as a failure. Telling an architect they have 113 code violations when they
have 12 violations and 101 unknowns is the difference this module exists to make.

**It refuses to pass a rule that checked nothing.** A specification whose applicability
matched zero elements has established no compliance, and `ifctester` reports it as a pass.
Whether a specification applies is a separate three-valued question from whether it
passed, and it is answered from the matched-subject count and the IDS cardinality -- never
from `ifctester`'s own status alone.

Nothing here reaches the network, a web framework, or an inference client. That is an
import contract in the repository root, checked by `make verify`, not a convention.
"""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any, Final

import ifcopenshell
import ifctester.ids

from cadgpt_engine.errors import InvalidIdsError, InvalidIfcError
from cadgpt_engine.reasons import classify
from cadgpt_engine.report import (
    EntityOutcome,
    Report,
    RequirementOutcome,
    SpecificationOutcome,
)
from cadgpt_engine.status import Applicability, ReasonCode, Status

#: How many non-passing entities one requirement itemises before the rest are counted but
#: not listed. Counts stay exact either way; see `report.RequirementOutcome`.
DEFAULT_ENTITY_LIMIT: Final = 500


def engine_version() -> str:
    """The installed version of this package, recorded on every report."""
    try:
        return version("cadgpt-engine")
    except PackageNotFoundError:  # running from a source tree that was never installed
        return "0+unknown"


def _aggregate(failed: int, indeterminate: int) -> Status:
    """A known violation decides FAIL; otherwise an unknown prevents PASS."""
    if failed:
        return Status.FAIL
    if indeterminate:
        return Status.INDETERMINATE
    return Status.PASS


def _outcome(element: Any, reason: str) -> EntityOutcome:
    status, code = classify(reason)
    return EntityOutcome(
        global_id=getattr(element, "GlobalId", None),
        ifc_class=element.is_a(),
        status=status,
        reason_code=code,
        detail=reason,
    )


def _requirement(facet: Any, specification: Any, entity_limit: int) -> RequirementOutcome:
    outcomes = tuple(_outcome(f["element"], f["reason"]) for f in facet.failures)
    failed = sum(1 for e in outcomes if e.status is Status.FAIL)
    indeterminate = sum(1 for e in outcomes if e.status is Status.INDETERMINATE)

    # `Facet.to_string("requirement", spec, ...)` short-circuits to the literal "The
    # requirement is not applicable" whenever `spec.maxOccurs == 0` -- true regardless of
    # this facet's own cardinality -- which would sit a not-applicable sentence directly
    # under a FAIL verdict for a prohibited specification (I5/I7: a requirement line must
    # never contradict the verdict beside it). `to_string`'s own "applicability" branch
    # makes the same `maxOccurs == 0` check but substitutes its `prohibited_templates`
    # instead, rendering what was actually prohibited. Same upstream method, the clause
    # type it was written to answer this case with.
    clause_type = "applicability" if specification.maxOccurs == 0 else "requirement"

    return RequirementOutcome(
        description=facet.to_string(clause_type, specification, facet),
        status=_aggregate(failed, indeterminate),
        passed=len(facet.passed_entities),
        failed=failed,
        indeterminate=indeterminate,
        entities=outcomes[:entity_limit],
        entities_omitted=max(0, len(outcomes) - entity_limit),
    )


def judge(
    cardinality: str,
    matched: int,
    schema_matches: bool,
    failed: int,
    indeterminate: int,
) -> tuple[Applicability, Status, ReasonCode | None]:
    """Decide applicability and status from subjects and cardinality, not evidence alone.

    The zero-subject cases are the ones `ifctester` gets wrong for our purposes: it
    reports a specification that matched nothing as a pass. Two specifications in the
    Wooden Windows rule set matched nothing in the Duplex model and came back green;
    nothing had been checked.
    """
    if not schema_matches:
        return (
            Applicability.UNDETERMINED,
            Status.INDETERMINATE,
            ReasonCode.SCHEMA_MISMATCH,
        )

    if matched == 0:
        if cardinality == "required":
            return (
                Applicability.APPLIES,
                Status.FAIL,
                ReasonCode.NO_SUBJECTS_BUT_REQUIRED,
            )
        if cardinality == "prohibited":
            return (
                Applicability.APPLIES,
                Status.PASS,
                ReasonCode.NO_SUBJECTS_AND_PROHIBITED,
            )
        return (
            Applicability.DOES_NOT_APPLY,
            Status.INDETERMINATE,
            ReasonCode.NO_SUBJECTS_NOTHING_CHECKED,
        )

    if cardinality == "prohibited":
        return (
            Applicability.APPLIES,
            Status.FAIL,
            ReasonCode.PROHIBITED_SUBJECTS_PRESENT,
        )

    return Applicability.APPLIES, _aggregate(failed, indeterminate), None


def _specification(spec: Any, entity_limit: int) -> SpecificationOutcome:
    requirements = tuple(_requirement(f, spec, entity_limit) for f in spec.requirements)
    failed = sum(r.failed for r in requirements)
    indeterminate = sum(r.indeterminate for r in requirements)
    matched = len(spec.applicable_entities)

    # is_ifc_version is None when the specification declares no version filter, and False
    # only on a real mismatch. Treating None as a mismatch would make every unversioned
    # rule undeterminable.
    schema_matches = spec.is_ifc_version is not False
    cardinality = str(spec.get_usage())
    applicability, status, reason_code = judge(
        cardinality, matched, schema_matches, failed, indeterminate
    )

    return SpecificationOutcome(
        name=spec.name or "",
        description=spec.description or "",
        instructions=spec.instructions or "",
        applicability=applicability,
        status=status,
        cardinality=cardinality,
        matched=matched,
        reason_code=reason_code,
        passed=sum(r.passed for r in requirements),
        failed=failed,
        indeterminate=indeterminate,
        requirements=requirements,
    )


def run_check(
    ifc_path: Path,
    ids_path: Path,
    *,
    entity_limit: int = DEFAULT_ENTITY_LIMIT,
    ifc_name: str | None = None,
) -> Report:
    """Evaluate `ifc_path` against `ids_path` and return a three-valued report.

    Both files are read from disk by the inherited libraries. Nothing is fetched. The IDS
    is validated against the buildingSMART schema before anything runs: a malformed rule
    set that is partly parsed under-checks the model while looking complete.

    `ifc_name` is what the report calls the model. It defaults to the file name on disk,
    which is right for the command line and wrong for a server, where the file is stored
    under a generated key and the architect knows it by the name they uploaded. A report
    that names a UUID is a report they cannot match to their own work.
    """
    try:
        specs = ifctester.ids.open(str(ids_path), validate=True)
    except Exception as exc:
        raise InvalidIdsError(str(exc)) from exc

    try:
        model = ifcopenshell.open(str(ifc_path))
    except Exception as exc:
        raise InvalidIfcError(str(exc)) from exc

    specs.validate(model)

    specifications = tuple(_specification(s, entity_limit) for s in specs.specifications)
    by_status = [s.status for s in specifications]
    specs_failed = by_status.count(Status.FAIL)
    specs_indeterminate = by_status.count(Status.INDETERMINATE)

    return Report(
        ifc_filename=ifc_name or Path(ifc_path).name,
        ifc_schema=str(model.schema),
        ids_title=str(specs.info.get("title", "")),
        engine_version=engine_version(),
        status=_aggregate(specs_failed, specs_indeterminate),
        specifications_passed=by_status.count(Status.PASS),
        specifications_failed=specs_failed,
        specifications_indeterminate=specs_indeterminate,
        passed=sum(s.passed for s in specifications),
        failed=sum(s.failed for s in specifications),
        indeterminate=sum(s.indeterminate for s in specifications),
        specifications=specifications,
    )
