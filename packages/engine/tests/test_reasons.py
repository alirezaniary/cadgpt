"""Every reason ifctester can emit maps to a status and a named cause."""

from __future__ import annotations

import ast
import inspect

import ifctester.facet
import pytest
from cadgpt_engine import ReasonCode, Status, classify, is_recognised, status_for

# Grouped by the question that decides the status: was the datum there to judge?

NOT_EVALUABLE: tuple[tuple[str, ReasonCode], ...] = (
    ("The required attribute did not exist", ReasonCode.ATTRIBUTE_MISSING),
    ('The attribute value "None" is empty', ReasonCode.ATTRIBUTE_EMPTY),
    (
        "An invalid attribute name was specified in the IDS",
        ReasonCode.ATTRIBUTE_NAME_INVALID,
    ),
    ("The entity has no classification", ReasonCode.CLASSIFICATION_MISSING),
    ("The entity has no relationship", ReasonCode.RELATIONSHIP_MISSING),
    ("The required property set does not exist", ReasonCode.PROPERTY_SET_MISSING),
    (
        "The property set does not contain the required property",
        ReasonCode.PROPERTY_MISSING,
    ),
    (
        'The property\'s data type "IfcText" does not match the required data type'
        ' of "IfcLengthMeasure"',
        ReasonCode.DATA_TYPE_MISMATCH,
    ),
    ("The entity has no material", ReasonCode.MATERIAL_MISSING),
)

VIOLATIONS: tuple[tuple[str, ReasonCode], ...] = (
    (
        'The entity class "IFCWALL" does not meet the required IFC class',
        ReasonCode.ENTITY_CLASS_MISMATCH,
    ),
    (
        'The predefined type "PARTITIONING" does not meet the required type',
        ReasonCode.PREDEFINED_TYPE_MISMATCH,
    ),
    (
        'The attribute value "800.0" does not match the requirement',
        ReasonCode.ATTRIBUTE_VALUE_MISMATCH,
    ),
    (
        "The attribute value should not have met the requirement",
        ReasonCode.ATTRIBUTE_VALUE_PROHIBITED,
    ),
    (
        'The references "A1" do not match the requirements',
        ReasonCode.CLASSIFICATION_REFERENCE_MISMATCH,
    ),
    (
        'The systems "Uniclass" do not match the requirements',
        ReasonCode.CLASSIFICATION_SYSTEM_MISMATCH,
    ),
    (
        "The classification should not have met the requirement",
        ReasonCode.CLASSIFICATION_PROHIBITED,
    ),
    (
        'The entity has a relationship with incorrect entities: "IFCSITE"',
        ReasonCode.RELATIONSHIP_ENTITY_MISMATCH,
    ),
    (
        'The entity has a relationship with incorrect predefined type: "USERDEFINED"',
        ReasonCode.RELATIONSHIP_PREDEFINED_TYPE_MISMATCH,
    ),
    (
        "The relationship should not have met the requirement",
        ReasonCode.RELATIONSHIP_PROHIBITED,
    ),
    (
        'The property value "12" does not match the requirements',
        ReasonCode.PROPERTY_VALUE_MISMATCH,
    ),
    (
        'The property values "12, 13" do not match the requirements',
        ReasonCode.PROPERTY_VALUE_MISMATCH,
    ),
    (
        "The property should not have met the requirement",
        ReasonCode.PROPERTY_PROHIBITED,
    ),
    (
        'The material names and categories of "steel" does not match the requirement',
        ReasonCode.MATERIAL_MISMATCH,
    ),
    (
        "The material should not have met the requirement",
        ReasonCode.MATERIAL_PROHIBITED,
    ),
)


@pytest.mark.parametrize(("reason", "code"), NOT_EVALUABLE)
def test_absent_data_is_indeterminate(reason: str, code: ReasonCode) -> None:
    assert classify(reason) == (Status.INDETERMINATE, code)


@pytest.mark.parametrize(("reason", "code"), VIOLATIONS)
def test_present_but_wrong_data_is_a_failure(reason: str, code: ReasonCode) -> None:
    assert classify(reason) == (Status.FAIL, code)


@pytest.mark.parametrize(("reason", "code"), (*NOT_EVALUABLE, *VIOLATIONS))
def test_status_is_recoverable_from_the_code_alone(reason: str, code: ReasonCode) -> None:
    """The stored report keeps the code, not the status derivation. They must agree."""
    status, _ = classify(reason)
    assert status_for(code) is status


def test_an_unrecognised_reason_is_never_a_silent_violation() -> None:
    """We do not assert a violation we cannot justify."""
    assert classify("Some reason a future ifctester invents") == (
        Status.INDETERMINATE,
        ReasonCode.REASON_UNRECOGNISED,
    )
    assert not is_recognised("Some reason a future ifctester invents")


def ifctester_reason_templates() -> set[str]:
    """Every failure reason ifctester can render, read out of its own source.

    Each `to_string` branch returns either a plain string or an f-string; interpolated
    values become "X" so the result is a concrete reason to classify.
    """
    templates: set[str] = set()
    tree = ast.parse(inspect.getsource(ifctester.facet))
    for cls in tree.body:
        if not (isinstance(cls, ast.ClassDef) and cls.name.endswith("Result")):
            continue
        for fn in cls.body:
            if not (isinstance(fn, ast.FunctionDef) and fn.name == "to_string"):
                continue
            for node in ast.walk(fn):
                if not isinstance(node, ast.Return) or node.value is None:
                    continue
                value = node.value
                if isinstance(value, ast.Constant) and isinstance(value.value, str):
                    templates.add(value.value)
                elif isinstance(value, ast.JoinedStr):
                    templates.add(
                        "".join(
                            part.value
                            if isinstance(part, ast.Constant)
                            and isinstance(part.value, str)
                            else "X"
                            for part in value.values
                        )
                    )
    return templates


def test_our_mapping_still_covers_every_reason_ifctester_can_emit() -> None:
    """Fails when an ifctester upgrade adds or reworks a failure reason.

    Without this, a new reason would quietly fall through to INDETERMINATE and real
    violations would stop being reported as violations.
    """
    unmatched = sorted(r for r in ifctester_reason_templates() if not is_recognised(r))
    assert unmatched == [], (
        "ifctester can emit reasons cadgpt_engine.reasons does not classify:\n  "
        + "\n  ".join(unmatched)
    )
