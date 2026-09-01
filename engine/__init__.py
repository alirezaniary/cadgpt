"""Deterministic IFC/IDS checking.

No web framework and no inference client may be imported here; see the import contract in
pyproject.toml, which is enforced by `make verify`.
"""

from engine.check import (
    EntityOutcome,
    Report,
    RequirementOutcome,
    SpecificationOutcome,
    Status,
    classify,
    is_recognised,
    run_check,
)

__all__ = [
    "EntityOutcome",
    "Report",
    "RequirementOutcome",
    "SpecificationOutcome",
    "Status",
    "classify",
    "is_recognised",
    "run_check",
]
