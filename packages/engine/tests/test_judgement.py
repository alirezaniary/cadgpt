"""Applicability is a separate question from status.

It is decided by how many elements the rule matched and what the IDS cardinality says
about that -- never by ifctester's own status. The zero-match rows are the ones ifctester
gets wrong for our purposes: it reports them as passes.
"""

from __future__ import annotations

import pytest
from cadgpt_engine import (
    NOTHING_ESTABLISHED_REASONS,
    Applicability,
    ReasonCode,
    Status,
    established_nothing,
    judge,
)

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


def test_nothing_established_reason_codes_are_total_over_judge() -> None:
    """`NOTHING_ESTABLISHED_REASONS` is total over every `(status, code)` `judge()` can
    produce -- not a hand-typed list (T-0052).

    `judge()` assigns a reason code only when it reaches a verdict without inspecting
    per-entity evidence, and it pairs that early-returned code with `Status.INDETERMINATE`
    in exactly the cases where nothing was established -- as opposed to a `FAIL`/`PASS`
    pairing like `NO_SUBJECTS_BUT_REQUIRED`/`NO_SUBJECTS_AND_PROHIBITED`, which is a real
    verdict the engine reached, not an absence of evidence. Sweeping every reachable
    parameter combination and asserting the resulting set against
    `NOTHING_ESTABLISHED_REASONS` means a future `judge()` change that produces a new
    INDETERMINATE-paired code fails this test until that code is added to the set in
    `status.py` -- exactly the gap a T-0038 review found: `NO_REQUIREMENTS_NOTHING_ASSERTED`
    shipped without any test forcing it into this set, the same way
    `test_every_engine_reason_code_has_a_translatable_label` (`test_reasons.py` in the
    service) forces every code into a translated label.

    This is now the single test that guards both renderers (T-0052): `report_markdown.py`
    imports `established_nothing`/`NOTHING_ESTABLISHED_REASONS` directly from here, and
    `ReportView.tsx` reads the `established_nothing` field `presentation.localize_report`
    computes from the same predicate, so neither restates this set for this test to drift
    away from independently -- a fourth zero-evidence code missing from
    `NOTHING_ESTABLISHED_REASONS` now fails exactly here, not silently in one renderer and
    not the other.
    """
    observed: set[ReasonCode] = set()
    for cardinality in ("required", "optional", "prohibited"):
        for matched in (0, 3):
            for schema_matches in (True, False):
                for failed in (0, 1):
                    for indeterminate in (0, 1):
                        for has_requirements in (True, False):
                            _, status, code = judge(
                                cardinality,
                                matched,
                                schema_matches,
                                failed,
                                indeterminate,
                                has_requirements,
                            )
                            if status is Status.INDETERMINATE and code is not None:
                                observed.add(code)
    assert observed == NOTHING_ESTABLISHED_REASONS
    assert all(established_nothing(code) for code in observed)
