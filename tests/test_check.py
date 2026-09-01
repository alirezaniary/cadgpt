"""Behaviour tests for engine.check, entered at the real entry point over real files."""

from __future__ import annotations

import ast
import inspect
from pathlib import Path

import ifctester.facet
import pytest

from engine import Applicability, Status, classify, is_recognised, run_check
from engine.check import _judge

FIXTURES = Path(__file__).parent / "fixtures"
IFC = FIXTURES / "three_doors.ifc"
IDS = FIXTURES / "door_width.ids"


# Every reason ifctester 0.8.5 can render, with sample values substituted. Grouped by the
# question that decides the status: is the datum there to judge?

NOT_EVALUABLE = (
    "The required attribute did not exist",
    'The attribute value "None" is empty',
    "An invalid attribute name was specified in the IDS",
    "The entity has no classification",
    "The entity has no relationship",
    "The required property set does not exist",
    "The property set does not contain the required property",
    'The property\'s data type "IfcText" does not match the required data type'
    ' of "IfcLengthMeasure"',
    "The entity has no material",
)

VIOLATIONS = (
    'The entity class "IFCWALL" does not meet the required IFC class',
    'The predefined type "PARTITIONING" does not meet the required type',
    'The attribute value "800.0" does not match the requirement',
    "The attribute value should not have met the requirement",
    'The references "A1" do not match the requirements',
    'The systems "Uniclass" do not match the requirements',
    "The classification should not have met the requirement",
    'The entity has a relationship with incorrect entities: "IFCSITE"',
    'The entity has a relationship with incorrect predefined type: "USERDEFINED"',
    "The relationship should not have met the requirement",
    'The property value "12" does not match the requirements',
    'The property values "12, 13" do not match the requirements',
    "The property should not have met the requirement",
    'The material names and categories of "steel" does not match the requirement',
    "The material should not have met the requirement",
)


@pytest.mark.parametrize("reason", NOT_EVALUABLE)
def test_absent_data_is_indeterminate(reason: str) -> None:
    assert classify(reason) is Status.INDETERMINATE


@pytest.mark.parametrize("reason", VIOLATIONS)
def test_present_but_wrong_data_is_a_failure(reason: str) -> None:
    assert classify(reason) is Status.FAIL


def test_an_unrecognised_reason_is_never_a_silent_violation() -> None:
    """We do not assert a violation we cannot justify."""
    assert classify("Some reason a future ifctester invents") is Status.INDETERMINATE
    assert not is_recognised("Some reason a future ifctester invents")


# Applicability is a separate question from status, decided by how many elements the rule
# matched and what the IDS cardinality says about that - never by ifctester's own status.
# The zero-match rows are the ones ifctester gets wrong for our purposes: it passes them.

JUDGEMENTS = (
    # cardinality,   matched, schema, failed, indet, applicability,             status
    ("required", 0, True, 0, 0, Applicability.APPLIES, Status.FAIL),
    ("prohibited", 0, True, 0, 0, Applicability.APPLIES, Status.PASS),
    ("optional", 0, True, 0, 0, Applicability.DOES_NOT_APPLY, Status.INDETERMINATE),
    ("prohibited", 3, True, 0, 0, Applicability.APPLIES, Status.FAIL),
    ("required", 3, True, 1, 0, Applicability.APPLIES, Status.FAIL),
    ("required", 3, True, 0, 2, Applicability.APPLIES, Status.INDETERMINATE),
    ("required", 3, True, 1, 2, Applicability.APPLIES, Status.FAIL),
    ("required", 3, True, 0, 0, Applicability.APPLIES, Status.PASS),
    ("required", 3, False, 0, 0, Applicability.UNDETERMINED, Status.INDETERMINATE),
)


@pytest.mark.parametrize(
    ("cardinality", "matched", "schema", "failed", "indet", "expect_appl", "expect_status"),
    JUDGEMENTS,
)
def test_applicability_and_status_come_from_subjects_and_cardinality(
    cardinality: str,
    matched: int,
    schema: bool,
    failed: int,
    indet: int,
    expect_appl: Applicability,
    expect_status: Status,
) -> None:
    applicability, status, reason = _judge(cardinality, matched, schema, failed, indet)
    assert (applicability, status) == (expect_appl, expect_status)
    if matched == 0 or not schema or cardinality == "prohibited":
        assert reason, "a result reached without checking elements must say why"


def test_a_rule_that_matched_nothing_never_passes() -> None:
    """The whole point: checking nothing is not evidence of compliance (I7)."""
    for cardinality in ("required", "optional"):
        _, status, _ = _judge(cardinality, 0, True, 0, 0)
        assert status is not Status.PASS


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
        "ifctester can emit reasons engine/check.py does not classify:\n  "
        + "\n  ".join(unmatched)
    )


@pytest.mark.integration
def test_the_real_path_separates_a_violation_from_missing_data() -> None:
    """Three real doors, one real IDS, three different answers.

    This is the behaviour the product exists for: `ifctester` alone reports two failures
    here. Only one of them is a code violation.
    """
    report = run_check(IFC, IDS)

    assert report.ids_title == "Accessible door width"
    assert report.ifc_filename == "three_doors.ifc"
    assert (report.passed, report.failed, report.indeterminate) == (1, 1, 1)
    assert report.status is Status.FAIL
    assert report.specifications[0].applicability is Applicability.APPLIES
    assert report.specifications[0].matched == 3

    outcomes = {
        e.global_id: e
        for s in report.specifications
        for r in s.requirements
        for e in r.entities
    }
    assert len(outcomes) == 2, "only the two non-passing doors are itemised"

    narrow = outcomes["3worKcMPzD8x0Y1nJVBqA2"]
    assert narrow.status is Status.FAIL
    assert narrow.ifc_class == "IfcDoor"
    assert "800.0" in narrow.reason

    unknown = outcomes["3worKcMPzD8x0Y1nJVBqA3"]
    assert unknown.status is Status.INDETERMINATE
    assert "empty" in unknown.reason


@pytest.mark.integration
def test_indeterminate_is_never_counted_as_a_pass() -> None:
    report = run_check(IFC, IDS)
    spec = report.specifications[0]
    assert spec.passed == 1
    assert spec.passed + spec.failed + spec.indeterminate == 3
    assert spec.status is not Status.PASS
