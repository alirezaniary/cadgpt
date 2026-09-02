"""Map one `ifctester` failure reason to a `ReasonCode`.

`ifctester` discards its structured reason dict at `ids.py:312` and keeps only the
rendered string, so the question "was the datum there to judge?" has to be asked of that
string. These patterns cover every reason ifctester 0.8.5 can emit, and
`test_reasons.py` asserts that exhaustively by parsing ifctester's own source: an upgrade
that adds or reworks a reason breaks the suite instead of silently misreporting.

The order of the two tables matters. A reason is checked against the not-evaluable
patterns first, because "the property's data type does not match the required data type"
reads like a violation and is not one -- the value cannot be compared at all.
"""

from __future__ import annotations

import re
from collections.abc import Iterable

from cadgpt_engine.status import NOT_EVALUABLE_CODES, ReasonCode, Status

_Rule = tuple[re.Pattern[str], ReasonCode]


def _compile(pairs: Iterable[tuple[str, ReasonCode]]) -> tuple[_Rule, ...]:
    return tuple((re.compile(pattern), code) for pattern, code in pairs)


# The model does not carry what the rule needed. INDETERMINATE, never FAIL.
_NOT_EVALUABLE: tuple[_Rule, ...] = _compile(
    (
        (r"^The required attribute did not exist$", ReasonCode.ATTRIBUTE_MISSING),
        (r"^The attribute value .* is empty$", ReasonCode.ATTRIBUTE_EMPTY),
        (
            r"^An invalid attribute name was specified in the IDS$",
            ReasonCode.ATTRIBUTE_NAME_INVALID,
        ),
        (r"^The entity has no classification$", ReasonCode.CLASSIFICATION_MISSING),
        (r"^The entity has no relationship$", ReasonCode.RELATIONSHIP_MISSING),
        (r"^The required property set does not exist$", ReasonCode.PROPERTY_SET_MISSING),
        (
            r"^The property set does not contain the required property$",
            ReasonCode.PROPERTY_MISSING,
        ),
        (r"does not match the required data type of", ReasonCode.DATA_TYPE_MISMATCH),
        (r"^The entity has no material$", ReasonCode.MATERIAL_MISSING),
    )
)

# The model carries the datum and it breaks the rule. FAIL.
_VIOLATION: tuple[_Rule, ...] = _compile(
    (
        (
            r"^The entity class .* does not meet the required IFC class$",
            ReasonCode.ENTITY_CLASS_MISMATCH,
        ),
        (
            r"^The predefined type .* does not meet the required type$",
            ReasonCode.PREDEFINED_TYPE_MISMATCH,
        ),
        (
            r"^The attribute value .* does not match the requirement$",
            ReasonCode.ATTRIBUTE_VALUE_MISMATCH,
        ),
        (
            r"^The attribute value should not have met the requirement$",
            ReasonCode.ATTRIBUTE_VALUE_PROHIBITED,
        ),
        (
            r"^The references .* do not match the requirements$",
            ReasonCode.CLASSIFICATION_REFERENCE_MISMATCH,
        ),
        (
            r"^The systems .* do not match the requirements$",
            ReasonCode.CLASSIFICATION_SYSTEM_MISMATCH,
        ),
        (
            r"^The classification should not have met the requirement$",
            ReasonCode.CLASSIFICATION_PROHIBITED,
        ),
        (
            r"^The entity has a relationship with incorrect entities",
            ReasonCode.RELATIONSHIP_ENTITY_MISMATCH,
        ),
        (
            r"^The entity has a relationship with incorrect predefined type",
            ReasonCode.RELATIONSHIP_PREDEFINED_TYPE_MISMATCH,
        ),
        (
            r"^The relationship should not have met the requirement$",
            ReasonCode.RELATIONSHIP_PROHIBITED,
        ),
        (
            r"^The property values? .* do(es)? not match the requirements?$",
            ReasonCode.PROPERTY_VALUE_MISMATCH,
        ),
        (
            r"^The property should not have met the requirement$",
            ReasonCode.PROPERTY_PROHIBITED,
        ),
        (
            r"^The material names and categories of .* does not match the requirement$",
            ReasonCode.MATERIAL_MISMATCH,
        ),
        (
            r"^The material should not have met the requirement$",
            ReasonCode.MATERIAL_PROHIBITED,
        ),
    )
)


def classify(reason: str) -> tuple[Status, ReasonCode]:
    """Decide status and name the cause for one ifctester failure reason.

    A reason we do not recognise is INDETERMINATE, never FAIL: we do not assert a
    violation we cannot justify. The raw reason travels with the outcome either way, so
    nothing is hidden from the reader.
    """
    for pattern, code in _NOT_EVALUABLE:
        if pattern.search(reason):
            return Status.INDETERMINATE, code
    for pattern, code in _VIOLATION:
        if pattern.search(reason):
            return Status.FAIL, code
    return Status.INDETERMINATE, ReasonCode.REASON_UNRECOGNISED


def status_for(code: ReasonCode) -> Status:
    """The status a `ReasonCode` implies, without going back through the raw string."""
    return Status.INDETERMINATE if code in NOT_EVALUABLE_CODES else Status.FAIL


def is_recognised(reason: str) -> bool:
    """Whether `reason` matches a reason ifctester is known to emit.

    Used by the coverage test that reads ifctester's source. A reason that stops being
    recognised is a real regression: real violations would start reporting as unknowns.
    """
    return any(p.search(reason) for p, _ in (*_NOT_EVALUABLE, *_VIOLATION))
