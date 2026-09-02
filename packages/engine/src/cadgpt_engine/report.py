"""The shape of a result, and its canonical serialization.

These structures are the contract between the engine and everything downstream: the
database column a run is stored in, the HTTP response, and the TypeScript types the
frontend is generated from. They are frozen, so a report cannot be edited after the fact
by the layer displaying it, and they are serialized explicitly rather than by
`dataclasses.asdict`, because a persisted wire shape should change only on purpose.

Counts are always exact. The itemised entity list is capped -- a real rule set against a
real model produced 3,623 non-passing entities on one specification, and the report is
stored as one document. Capping the list while keeping the counts exact is the only
truncation permitted: `entities_omitted` states the size of what was dropped, so a reader
is never left believing they are looking at the whole list.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from cadgpt_engine.status import Applicability, ReasonCode, Status

#: Wire-format version of the documents produced here. Bump when a field changes meaning,
#: so a stored report from an older engine can still be read correctly.
#:
#: Bumped to 2 for `RequirementOutcome.basis`: `description` stops being the requirement's
#: citation and becomes its fallback -- the field's role changes even though its own text
#: does not -- so a document written before this version has no `basis` at all and must be
#: read through that fallback rather than assumed to carry one.
REPORT_SCHEMA_VERSION = 2


@dataclass(frozen=True, slots=True)
class EntityOutcome:
    """One element that did not pass, and why.

    `detail` is the raw text from ifctester and carries the measured value -- "800.0" in a
    door-width failure -- which is what makes a finding arguable with a plan reviewer.
    `reason_code` is what the presentation layer switches and translates on.
    """

    global_id: str | None
    ifc_class: str
    status: Status
    reason_code: ReasonCode
    detail: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "global_id": self.global_id,
            "ifc_class": self.ifc_class,
            "status": self.status.value,
            "reason_code": self.reason_code.value,
            "detail": self.detail,
        }


@dataclass(frozen=True, slots=True)
class Comparison:
    """One operator and the value it compares against.

    What a `Restriction` option is, without `Restriction.__str__`'s `str(self.options)` --
    the Python dict repr this task exists to stop putting in front of a reader. `operator`
    is an XSD facet name (`minInclusive`, `maxInclusive`, `enumeration`, ...) or the literal
    string `"literal"` when the requirement states a bare value with no restriction at all.
    `value` carries no unit: the engine measures what the IDS states and invents nothing
    the IDS did not say.
    """

    operator: str
    value: str

    def to_dict(self) -> dict[str, str]:
        return {"operator": self.operator, "value": self.value}


@dataclass(frozen=True, slots=True)
class RequirementBasis:
    """The requirement's own facet, as data a service can put into a sentence.

    The structured counterpart to `RequirementOutcome.description`: the same fact, named
    rather than rendered into English. `name` is the attribute or property name the facet
    reads (`None` for a facet type that names no such thing -- an entity-class or
    classification requirement, which the fixtures this task ships against do not exercise).
    `cardinality` is the requirement's effective cardinality -- `"prohibited"` when the
    specification itself is prohibited (`maxOccurs == 0`) even if the facet's own
    `cardinality` attribute says `"required"`, mirroring the same substitution
    `check.py`'s `clause_type` makes for `description` so the two can never contradict each
    other under I5/I7.
    """

    facet_type: str
    name: str | None
    cardinality: str
    comparisons: tuple[Comparison, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "facet_type": self.facet_type,
            "name": self.name,
            "cardinality": self.cardinality,
            "comparisons": [c.to_dict() for c in self.comparisons],
        }


@dataclass(frozen=True, slots=True)
class RequirementOutcome:
    """`description` is upstream's own sentence -- what the engine's CLI and tests print,
    and the fallback a service renders when `basis` cannot be turned into a sentence in the
    reader's language. `basis` is the primary citation: the service supplies the wording,
    the same shape `reason_code` / `reason_label` already established for a finding's cause.
    """

    description: str
    basis: RequirementBasis
    status: Status
    passed: int
    failed: int
    indeterminate: int
    entities: tuple[EntityOutcome, ...]
    entities_omitted: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "description": self.description,
            "basis": self.basis.to_dict(),
            "status": self.status.value,
            "passed": self.passed,
            "failed": self.failed,
            "indeterminate": self.indeterminate,
            "entities": [e.to_dict() for e in self.entities],
            "entities_omitted": self.entities_omitted,
        }


@dataclass(frozen=True, slots=True)
class SpecificationOutcome:
    """`description` is the IDS author's own `<ids:description>` text -- theirs, and never
    overwritten. `applicability_description` is a different fact: `ifctester`'s own
    rendering of what the applicability facets select (`to_string("applicability", ...)`,
    e.g. "All IFCDOOR data"), carried through so the report states what the rule applies to
    even when the author left `description` blank, as the shipped fixture does.
    """

    name: str
    description: str
    applicability_description: str
    instructions: str
    applicability: Applicability
    status: Status
    cardinality: str
    matched: int
    reason_code: ReasonCode | None
    passed: int
    failed: int
    indeterminate: int
    requirements: tuple[RequirementOutcome, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "applicability_description": self.applicability_description,
            "instructions": self.instructions,
            "applicability": self.applicability.value,
            "status": self.status.value,
            "cardinality": self.cardinality,
            "matched": self.matched,
            "reason_code": self.reason_code.value if self.reason_code else None,
            "passed": self.passed,
            "failed": self.failed,
            "indeterminate": self.indeterminate,
            "requirements": [r.to_dict() for r in self.requirements],
        }


@dataclass(frozen=True, slots=True)
class Report:
    """One evaluation of one model against one rule set.

    Reproducible from its inputs: `engine_version` and the two file identities are what an
    old run needs in order to stay explainable after the engine moves on.
    """

    ifc_filename: str
    ifc_schema: str
    ids_title: str
    engine_version: str
    status: Status
    specifications_passed: int
    specifications_failed: int
    specifications_indeterminate: int
    passed: int
    failed: int
    indeterminate: int
    specifications: tuple[SpecificationOutcome, ...]

    @property
    def checked(self) -> int:
        """Entity-level outcomes reached. Excludes nothing; INDETERMINATE is not a pass."""
        return self.passed + self.failed + self.indeterminate

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": REPORT_SCHEMA_VERSION,
            "engine_version": self.engine_version,
            "ifc_filename": self.ifc_filename,
            "ifc_schema": self.ifc_schema,
            "ids_title": self.ids_title,
            "status": self.status.value,
            "specifications_passed": self.specifications_passed,
            "specifications_failed": self.specifications_failed,
            "specifications_indeterminate": self.specifications_indeterminate,
            "passed": self.passed,
            "failed": self.failed,
            "indeterminate": self.indeterminate,
            "specifications": [s.to_dict() for s in self.specifications],
        }
