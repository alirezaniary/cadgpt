"""The real path: real IFC, real IDS, real output. No mocks anywhere in this file."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
from cadgpt_engine import (
    REPORT_SCHEMA_VERSION,
    Applicability,
    InvalidIdsError,
    InvalidIfcError,
    ReasonCode,
    Status,
    run_check,
)

pytestmark = pytest.mark.integration


def test_the_real_path_separates_a_violation_from_missing_data(
    three_doors_ifc: Path, door_width_ids: Path
) -> None:
    """Three real doors, one real IDS, three different answers.

    This is the behaviour the product exists for: `ifctester` alone reports two failures
    here. Only one of them is a code violation.
    """
    report = run_check(three_doors_ifc, door_width_ids)

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
    assert narrow.reason_code is ReasonCode.ATTRIBUTE_VALUE_MISMATCH
    assert "800.0" in narrow.detail, "the measured value is what a reviewer argues with"

    unknown = outcomes["3worKcMPzD8x0Y1nJVBqA3"]
    assert unknown.status is Status.INDETERMINATE
    assert unknown.reason_code is ReasonCode.ATTRIBUTE_EMPTY


def test_the_requirement_description_is_the_rule_in_words_not_an_object_repr(
    three_doors_ifc: Path, door_width_ids: Path
) -> None:
    """I5: a finding cites a resolvable basis, and a CPython object address is not one.

    `ifctester` renders every facet's own template via `to_string`; the engine must call
    it with the real `Specification` in scope rather than falling back to `str(facet)`,
    which is the default `object.__repr__` because no facet defines `__str__`.
    """
    report = run_check(three_doors_ifc, door_width_ids)
    requirement = report.specifications[0].requirements[0]

    assert requirement.description == "The OverallWidth shall be {'minInclusive': '900'}"

    for spec in report.specifications:
        for req in spec.requirements:
            assert not re.search(r"<.* object at 0x", req.description), (
                "a facet whose template is lost renders as a memory address, not text"
            )


def test_a_prohibited_specifications_requirement_line_never_contradicts_its_verdict(
    three_doors_ifc: Path, door_prohibited_ids: Path
) -> None:
    """I5/I7: a requirement line must never say the opposite of the verdict beside it.

    `Facet.to_string("requirement", specification, ...)` short-circuits to the literal
    "The requirement is not applicable" whenever `specification.maxOccurs == 0` -- true of
    every facet on a prohibited specification, regardless of that facet's own cardinality.
    Threading the real `Specification` into a plain `to_string("requirement", ...)` call
    would put that literal directly under a FAIL verdict reporting
    `PROHIBITED_SUBJECTS_PRESENT` -- a line that reads as a limitation-shaped pass while the
    spec beside it failed. This
    is the one input where passing the real specification and passing `None` produce
    different text, so it is the regression guard the fix needs: `door_prohibited.ids`
    prohibits `IfcDoor` outright (`minOccurs="0" maxOccurs="0"`), and `three_doors.ifc` has
    three of them.
    """
    report = run_check(three_doors_ifc, door_prohibited_ids)
    spec = report.specifications[0]

    assert spec.applicability is Applicability.APPLIES
    assert spec.status is Status.FAIL
    assert spec.reason_code is ReasonCode.PROHIBITED_SUBJECTS_PRESENT
    assert spec.matched == 3

    requirement = spec.requirements[0]
    assert requirement.description == "The OverallWidth shall not be provided"
    assert "not applicable" not in requirement.description, (
        "a requirement line must never contradict the FAIL verdict beside it"
    )


def test_indeterminate_is_never_counted_as_a_pass(
    three_doors_ifc: Path, door_width_ids: Path
) -> None:
    report = run_check(three_doors_ifc, door_width_ids)
    spec = report.specifications[0]
    assert spec.passed == 1
    assert spec.passed + spec.failed + spec.indeterminate == 3
    assert spec.status is not Status.PASS
    assert report.checked == 3


def test_the_report_records_what_produced_it(
    three_doors_ifc: Path, door_width_ids: Path
) -> None:
    """An old run stays explainable only if it says which engine and schema made it."""
    report = run_check(three_doors_ifc, door_width_ids)
    assert report.ifc_schema.startswith("IFC")
    assert report.engine_version


def test_the_report_serializes_to_a_stable_json_document(
    three_doors_ifc: Path, door_width_ids: Path
) -> None:
    """This document is stored in the database and served to the browser."""
    document = run_check(three_doors_ifc, door_width_ids).to_dict()
    round_tripped = json.loads(json.dumps(document))

    assert round_tripped == document, "the document must survive a JSON round trip"
    assert round_tripped["schema_version"] == REPORT_SCHEMA_VERSION
    assert round_tripped["status"] == "FAIL"
    assert round_tripped["specifications"][0]["requirements"][0]["entities_omitted"] == 0

    statuses = {
        e["status"]
        for s in round_tripped["specifications"]
        for r in s["requirements"]
        for e in r["entities"]
    }
    assert statuses == {"FAIL", "INDETERMINATE"}


def test_counts_stay_exact_when_the_itemised_list_is_capped(
    three_doors_ifc: Path, door_width_ids: Path
) -> None:
    """Truncating the detail must never move a count. A capped list states its omission."""
    full = run_check(three_doors_ifc, door_width_ids)
    capped = run_check(three_doors_ifc, door_width_ids, entity_limit=1)

    assert (capped.passed, capped.failed, capped.indeterminate) == (
        full.passed,
        full.failed,
        full.indeterminate,
    )
    requirement = capped.specifications[0].requirements[0]
    assert len(requirement.entities) == 1
    assert requirement.entities_omitted == 1


def test_a_malformed_ids_is_refused_rather_than_partly_evaluated(tmp_path: Path) -> None:
    """A rule set that half-parses under-checks the model while looking complete."""
    bad = tmp_path / "broken.ids"
    bad.write_text("<ids>not an ids file</ids>", encoding="utf-8")
    with pytest.raises(InvalidIdsError):
        run_check(Path("/nonexistent.ifc"), bad)


def test_an_unparseable_ifc_is_a_typed_error(door_width_ids: Path, tmp_path: Path) -> None:
    """The API layer distinguishes a bad upload from a broken engine on this type."""
    bad = tmp_path / "broken.ifc"
    bad.write_text("this is not an IFC file", encoding="utf-8")
    with pytest.raises(InvalidIfcError):
        run_check(bad, door_width_ids)


def test_a_requirement_that_evaluated_nothing_is_indeterminate_not_pass(
    three_doors_ifc: Path, door_prohibited_ids: Path
) -> None:
    """I7 pushed down one level: `_aggregate` must not read `failed == indeterminate == 0`
    as compliance when nothing was evaluated either.

    `door_prohibited.ids` forbids `IfcDoor` outright. Its own requirement facet is never
    run against the three doors that exist -- ifctester interprets a prohibited
    specification as "the requirement does not apply", not "check it and see" -- so the
    requirement reaches `_aggregate` with `passed == failed == indeterminate == 0`. The old
    code read that as PASS: a requirement that checked nothing, reported green.
    """
    report = run_check(three_doors_ifc, door_prohibited_ids)
    requirement = report.specifications[0].requirements[0]

    assert (requirement.passed, requirement.failed, requirement.indeterminate) == (0, 0, 0)
    assert requirement.status is Status.INDETERMINATE, (
        "a requirement with zero outcomes has established no compliance"
    )


def test_a_requirement_that_genuinely_evaluated_entities_and_all_passed_stays_pass(
    three_doors_ifc: Path, door_name_recorded_ids: Path
) -> None:
    """The direction this task must not break: real evidence, all of it a pass, is PASS.

    Every door in `three_doors_ifc` genuinely has a `Name`, so this requirement matches
    three real entities and passes all three -- unlike the prohibited-specification case
    above, `passed` here is not zero.
    """
    report = run_check(three_doors_ifc, door_name_recorded_ids)
    requirement = report.specifications[0].requirements[0]

    assert (requirement.passed, requirement.failed, requirement.indeterminate) == (3, 0, 0)
    assert requirement.status is Status.PASS
    assert report.status is Status.PASS


def test_the_report_can_be_told_what_to_call_the_model(
    three_doors_ifc: Path, door_width_ids: Path
) -> None:
    """On a server the file is stored under a generated key, not its own name.

    A report naming a UUID is one the architect cannot match to their own work.
    """
    report = run_check(three_doors_ifc, door_width_ids, ifc_name="Block A - level 00.ifc")
    assert report.ifc_filename == "Block A - level 00.ifc"
