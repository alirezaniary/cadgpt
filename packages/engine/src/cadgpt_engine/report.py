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
REPORT_SCHEMA_VERSION = 1


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
class RequirementOutcome:
    description: str
    status: Status
    passed: int
    failed: int
    indeterminate: int
    entities: tuple[EntityOutcome, ...]
    entities_omitted: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "description": self.description,
            "status": self.status.value,
            "passed": self.passed,
            "failed": self.failed,
            "indeterminate": self.indeterminate,
            "entities": [e.to_dict() for e in self.entities],
            "entities_omitted": self.entities_omitted,
        }


@dataclass(frozen=True, slots=True)
class SpecificationOutcome:
    name: str
    description: str
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
