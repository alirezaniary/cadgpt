"""Deterministic IFC/IDS checking.

The one invariant this package exists to hold: the language model never evaluates a rule.
No web framework and no inference client may be imported here -- see the import contract
in the repository root `pyproject.toml`, enforced by `make verify`.
"""

from cadgpt_engine.check import DEFAULT_ENTITY_LIMIT, engine_version, judge, run_check
from cadgpt_engine.errors import (
    EngineError,
    InvalidIdsError,
    InvalidIfcError,
    InvalidInputError,
)
from cadgpt_engine.messages import default_message
from cadgpt_engine.reasons import classify, is_recognised, status_for
from cadgpt_engine.report import (
    REPORT_SCHEMA_VERSION,
    Comparison,
    EntityOutcome,
    Report,
    RequirementBasis,
    RequirementOutcome,
    SpecificationOutcome,
)
from cadgpt_engine.ruleset import (
    RuleSetSummary,
    SpecificationSummary,
    inspect_ruleset,
)
from cadgpt_engine.status import (
    NOT_EVALUABLE_CODES,
    Applicability,
    ReasonCode,
    Status,
)

__all__ = [
    "DEFAULT_ENTITY_LIMIT",
    "NOT_EVALUABLE_CODES",
    "REPORT_SCHEMA_VERSION",
    "Applicability",
    "Comparison",
    "EngineError",
    "EntityOutcome",
    "InvalidIdsError",
    "InvalidIfcError",
    "InvalidInputError",
    "ReasonCode",
    "Report",
    "RequirementBasis",
    "RequirementOutcome",
    "RuleSetSummary",
    "SpecificationOutcome",
    "SpecificationSummary",
    "Status",
    "classify",
    "default_message",
    "engine_version",
    "inspect_ruleset",
    "is_recognised",
    "judge",
    "run_check",
    "status_for",
]
