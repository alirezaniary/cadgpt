"""The real path: real IFC, real IDS, real output. No mocks anywhere in this file."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
from cadgpt_engine import (
    REPORT_SCHEMA_VERSION,
    Applicability,
    Comparison,
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


def test_the_requirement_basis_names_the_bound_as_data_not_a_stringified_dict(
    three_doors_ifc: Path, door_width_ids: Path
) -> None:
    """I5's structured counterpart to `description`: the operator and value `description`
    can only narrate, so a service can render "at least 900" in the reader's language
    without re-parsing `{'minInclusive': '900'}` back apart.
    """
    report = run_check(three_doors_ifc, door_width_ids)
    basis = report.specifications[0].requirements[0].basis

    assert basis.facet_type == "attribute"
    assert basis.name == "OverallWidth"
    assert basis.cardinality == "required"
    assert basis.comparisons == (Comparison(operator="minInclusive", value="900"),)


def test_the_specification_states_what_it_applies_to(
    three_doors_ifc: Path, door_width_ids: Path
) -> None:
    """I5: a requirement without its subject is half a citation.

    `spec.description` is the IDS author's own `<ids:description>`, empty in this fixture
    on purpose, so `applicability_description` -- `ifctester`'s own applicability rendering
    -- is the only place the subject reaches the report at all.
    """
    report = run_check(three_doors_ifc, door_width_ids)
    spec = report.specifications[0]

    assert spec.description == ""
    assert spec.applicability_description == "All IFCDOOR data"


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
    # The facet's own `cardinality="required"` attribute (see door_prohibited.ids) must not
    # leak into the structured citation: the specification's prohibition overrides it, the
    # same substitution `description` above just made, or the two would disagree.
    assert requirement.basis.cardinality == "prohibited"
    # T-0037: this requirement evaluated real subjects were prohibited and present, which
    # `judge()` already named `PROHIBITED_SUBJECTS_PRESENT` one level up -- the requirement
    # never independently ran against those three doors (see the test below), so it
    # carries that same reason rather than inventing one of its own.
    assert requirement.reason_code is ReasonCode.PROHIBITED_SUBJECTS_PRESENT


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
    # T-0037: real evidence was evaluated, so there is nothing to explain.
    assert requirement.reason_code is None
    # T-0037 review round 2 (F1): nor is there an unresolved applicability to caveat --
    # this is the "ordinary PASS, no caveat at all" control case for that fix.
    assert requirement.applicability_caveat is None


def test_a_prohibited_specification_matching_nothing_explains_its_own_requirement_row(
    three_doors_ifc: Path, window_prohibited_ids: Path
) -> None:
    """T-0037, the case the T-0028 review reproduced: `window_prohibited.ids` prohibits
    `IfcWindow`, and `three_doors_ifc` contains none at all -- the applicability itself
    matches zero subjects, so the specification legitimately reaches PASS
    (`NO_SUBJECTS_AND_PROHIBITED`) while its lone requirement evaluated nothing and reads
    `INDETERMINATE`, `passed == failed == indeterminate == 0`, exactly like
    `door_prohibited.ids`'s case above. Both statements are true and are not a
    contradiction (`docs/decisions.md`, "A requirement that evaluated nothing is
    explained, never suppressed") -- what changes here is that the requirement row now
    carries *why*, reusing `judge()`'s own reason rather than leaving a bare
    `INDETERMINATE` under a green verdict for the reader to puzzle out.
    """
    report = run_check(three_doors_ifc, window_prohibited_ids)
    spec = report.specifications[0]

    assert spec.applicability is Applicability.APPLIES
    assert spec.matched == 0
    assert spec.status is Status.PASS
    assert spec.reason_code is ReasonCode.NO_SUBJECTS_AND_PROHIBITED

    requirement = spec.requirements[0]
    assert (requirement.passed, requirement.failed, requirement.indeterminate) == (0, 0, 0)
    assert requirement.status is Status.INDETERMINATE
    assert requirement.reason_code is ReasonCode.NO_SUBJECTS_AND_PROHIBITED
    assert requirement.to_dict()["reason_code"] == "NO_SUBJECTS_AND_PROHIBITED"
    # T-0037 review round 2 (F1): this row already explains itself via `reason_code`
    # (it matched nothing), so `applicability_caveat` must stay `None` rather than
    # repeating the identical sentence under a second field.
    assert requirement.applicability_caveat is None


def test_real_evidence_under_an_unresolved_applicability_carries_a_caveat_not_a_bare_pass(
    three_doors_ifc: Path, door_schema_mismatch_ids: Path
) -> None:
    """T-0037 review round 2, finding F1 -- the hole the zero-count backfill above does
    not close: `door_schema_mismatch_ids` declares `ifcVersion="IFC2X3"` only, and
    `three_doors_ifc` is `IFC4`, so the specification's own applicability is never
    established (`SCHEMA_MISMATCH`, `UNDETERMINED_APPLICABILITY`). `ifctester` still
    matches all three real doors and genuinely evaluates the requirement against them --
    a real `PASS`, real non-zero counts -- so `reason_code` correctly stays `None` (this
    requirement did not evaluate nothing). Rendering that `PASS` with no caveat at all
    would assert a compliance this run never established was even applicable
    (`CLAUDE.md`, "Never assert compliance we did not establish"), so
    `applicability_caveat` carries the specification's own reason down instead.
    """
    report = run_check(three_doors_ifc, door_schema_mismatch_ids)
    spec = report.specifications[0]

    assert spec.applicability is Applicability.UNDETERMINED
    assert spec.status is Status.INDETERMINATE
    assert spec.reason_code is ReasonCode.SCHEMA_MISMATCH
    assert spec.matched == 3

    requirement = spec.requirements[0]
    assert (requirement.passed, requirement.failed, requirement.indeterminate) == (3, 0, 0)
    assert requirement.status is Status.PASS, "real evidence, all of it a pass, is PASS"
    assert requirement.reason_code is None, (
        "this requirement did not evaluate nothing -- it must not claim to"
    )
    assert requirement.applicability_caveat is ReasonCode.SCHEMA_MISMATCH
    assert requirement.to_dict()["applicability_caveat"] == "SCHEMA_MISMATCH"


def test_an_optional_specification_with_no_requirements_is_indeterminate_not_pass(
    three_doors_ifc: Path, door_optional_no_requirements_ids: Path
) -> None:
    """T-0038: reproduces the defect end to end through the real path.

    `door_optional_no_requirements.ids` is `optional` cardinality, matches all three real
    doors, and states zero requirement facets. It checked nothing and established
    nothing; before this fix, `judge()` read `matched > 0` alone as a pass.
    """
    report = run_check(three_doors_ifc, door_optional_no_requirements_ids)
    spec = report.specifications[0]

    assert spec.applicability is Applicability.APPLIES
    assert spec.matched == 3
    assert spec.requirements == ()
    assert spec.status is Status.INDETERMINATE
    assert spec.reason_code is ReasonCode.NO_REQUIREMENTS_NOTHING_ASSERTED
    assert report.status is Status.INDETERMINATE


def test_a_required_specification_with_no_requirements_still_passes(
    three_doors_ifc: Path, door_required_no_requirements_ids: Path
) -> None:
    """T-0038's control case, run through the real path: `required` with zero
    requirement facets is a legitimate existence check and must stay PASS.
    """
    report = run_check(three_doors_ifc, door_required_no_requirements_ids)
    spec = report.specifications[0]

    assert spec.applicability is Applicability.APPLIES
    assert spec.matched == 3
    assert spec.requirements == ()
    assert spec.status is Status.PASS
    assert spec.reason_code is None
    assert report.status is Status.PASS


def test_the_report_can_be_told_what_to_call_the_model(
    three_doors_ifc: Path, door_width_ids: Path
) -> None:
    """On a server the file is stored under a generated key, not its own name.

    A report naming a UUID is one the architect cannot match to their own work.
    """
    report = run_check(three_doors_ifc, door_width_ids, ifc_name="Block A - level 00.ifc")
    assert report.ifc_filename == "Block A - level 00.ifc"
