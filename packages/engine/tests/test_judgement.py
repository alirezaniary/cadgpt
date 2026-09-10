"""Applicability is a separate question from status.

It is decided by how many elements the rule matched and what the IDS cardinality says
about that -- never by ifctester's own status. The zero-match rows are the ones ifctester
gets wrong for our purposes: it reports them as passes.
"""

from __future__ import annotations

import pytest
from cadgpt_engine import Applicability, ReasonCode, Status, judge

JUDGEMENTS = (
    # cardinality, matched, schema, failed, indet, has_reqs, applicability,     status
    ("required", 0, True, 0, 0, True, Applicability.APPLIES, Status.FAIL),
    ("prohibited", 0, True, 0, 0, True, Applicability.APPLIES, Status.PASS),
    ("optional", 0, True, 0, 0, True, Applicability.DOES_NOT_APPLY, Status.INDETERMINATE),
    ("prohibited", 3, True, 0, 0, True, Applicability.APPLIES, Status.FAIL),
    ("required", 3, True, 1, 0, True, Applicability.APPLIES, Status.FAIL),
    ("required", 3, True, 0, 2, True, Applicability.APPLIES, Status.INDETERMINATE),
    ("required", 3, True, 1, 2, True, Applicability.APPLIES, Status.FAIL),
    ("required", 3, True, 0, 0, True, Applicability.APPLIES, Status.PASS),
    ("required", 3, False, 0, 0, True, Applicability.UNDETERMINED, Status.INDETERMINATE),
    # T-0038: zero requirement facets. `required` is a legitimate existence check and
    # stays PASS; `optional` established nothing and must not.
    ("required", 3, True, 0, 0, False, Applicability.APPLIES, Status.PASS),
    ("optional", 3, True, 0, 0, False, Applicability.APPLIES, Status.INDETERMINATE),
)


@pytest.mark.parametrize(
    (
        "cardinality",
        "matched",
        "schema",
        "failed",
        "indet",
        "has_reqs",
        "expect_appl",
        "expect_status",
    ),
    JUDGEMENTS,
)
def test_applicability_and_status_come_from_subjects_and_cardinality(
    cardinality: str,
    matched: int,
    schema: bool,
    failed: int,
    indet: int,
    has_reqs: bool,
    expect_appl: Applicability,
    expect_status: Status,
) -> None:
    applicability, status, code = judge(
        cardinality, matched, schema, failed, indet, has_reqs
    )
    assert (applicability, status) == (expect_appl, expect_status)
    reached_without_evidence = (
        matched == 0
        or not schema
        or cardinality == "prohibited"
        or (cardinality == "optional" and not has_reqs)
    )
    if reached_without_evidence:
        assert code is not None, "a result reached without checking elements must say why"
    else:
        assert code is None, "a verdict backed by real evidence carries no spec-level code"


def test_a_rule_that_matched_nothing_never_passes() -> None:
    """The whole point: checking nothing is not evidence of compliance (I7)."""
    for cardinality in ("required", "optional"):
        _, status, _ = judge(cardinality, 0, True, 0, 0, True)
        assert status is not Status.PASS


def test_a_rule_evaluated_on_real_evidence_carries_no_spec_level_reason() -> None:
    """A reason code at specification level means the verdict bypassed the evidence."""
    _, status, code = judge("required", 3, True, 0, 0, True)
    assert (status, code) == (Status.PASS, None)


def test_a_schema_mismatch_is_undetermined_not_failed() -> None:
    """3,343 confident failures came from an IFC4 rule run against an IFC2X3 model.

    They were not trustworthy: the rule was written for a different schema. Reporting
    them as violations is the failure mode this row prevents.
    """
    applicability, status, code = judge("required", 3, False, 3343, 0, True)
    assert applicability is Applicability.UNDETERMINED
    assert status is Status.INDETERMINATE
    assert code is ReasonCode.SCHEMA_MISMATCH


def test_an_optional_specification_with_no_requirements_never_passes() -> None:
    """T-0038: an optional specification that names a subject and asserts nothing about
    it has checked nothing and established nothing, matched subjects or not.
    """
    applicability, status, code = judge("optional", 3, True, 0, 0, False)
    assert applicability is Applicability.APPLIES
    assert status is Status.INDETERMINATE
    assert code is ReasonCode.NO_REQUIREMENTS_NOTHING_ASSERTED


def test_a_required_specification_with_no_requirements_stays_pass() -> None:
    """T-0038's control case: `required` with zero requirement facets is a legitimate
    existence check -- "at least one of these must exist" -- and matching real subjects
    genuinely establishes it. A fix here must not turn this INDETERMINATE too.
    """
    applicability, status, code = judge("required", 3, True, 0, 0, False)
    assert applicability is Applicability.APPLIES
    assert status is Status.PASS
    assert code is None
