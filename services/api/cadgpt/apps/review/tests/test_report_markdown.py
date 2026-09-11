"""render_markdown_report: the file mirrors ReportView.tsx's presentation rules exactly.

Coverage before findings, FAIL -> INDETERMINATE -> PASS ordering, a coverage numerator
that is a real measurement and never `N of N`, all three counts always -- the same
properties `test_presentation.py` and `ReportView.tsx` hold for the JSON and the screen,
proven here for the file `ReportView.tsx` is the specification for. These are properties of
*structure* (ordering, presence, injection-safety), not of any one language's wording, so
`english` below activates English deliberately (T-0083 made `fa` the process-wide default,
including for a bare pytest run with no request in sight) rather than re-encoding every
assertion below against the Persian translation by hand.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest
from cadgpt_engine import Status, judge
from django.utils import translation

from cadgpt.apps.review.services.presentation import localize_report
from cadgpt.apps.review.services.report_markdown import (
    _NOTHING_ESTABLISHED_REASONS,
    render_markdown_report,
)


@pytest.fixture(autouse=True)
def english() -> Iterator[None]:
    with translation.override("en"):
        yield


_REPORT: dict[str, Any] = {
    "schema_version": 2,
    "engine_version": "0.1.0",
    "ifc_filename": "three_doors.ifc",
    "ifc_schema": "IFC4",
    "ids_title": "Accessible door width",
    "status": "FAIL",
    "specifications_passed": 0,
    "specifications_failed": 1,
    "specifications_indeterminate": 1,
    "passed": 1,
    "failed": 1,
    "indeterminate": 1,
    "specifications": [
        {
            "name": "Minimum clear door width 900 mm",
            "description": "",
            "instructions": "",
            "applicability": "APPLIES",
            "status": "FAIL",
            "cardinality": "required",
            "matched": 3,
            "reason_code": None,
            "passed": 1,
            "failed": 1,
            "indeterminate": 1,
            "requirements": [
                {
                    "description": "The OverallWidth shall be {'minInclusive': '900'}",
                    "basis": {
                        "facet_type": "attribute",
                        "name": "OverallWidth",
                        "cardinality": "required",
                        "comparisons": [{"operator": "minInclusive", "value": "900"}],
                    },
                    "status": "FAIL",
                    "passed": 1,
                    "failed": 1,
                    "indeterminate": 1,
                    "entities": [
                        {
                            "global_id": "3worKcMPzD8x0Y1nJVBqA2",
                            "ifc_class": "IfcDoor",
                            "status": "FAIL",
                            "reason_code": "ATTRIBUTE_VALUE_MISMATCH",
                            "detail": (
                                'The attribute value "800.0" does not match the requirement'
                            ),
                        },
                        {
                            "global_id": "1abcDEfghijklmno0Y1nJZ",
                            "ifc_class": "IfcDoor",
                            "status": "INDETERMINATE",
                            "reason_code": "ATTRIBUTE_EMPTY",
                            "detail": "The attribute is present but holds no value",
                        },
                    ],
                    "entities_omitted": 0,
                }
            ],
        },
        {
            "name": "A schema-mismatched specification",
            "description": "",
            "instructions": "",
            "applicability": "UNDETERMINED_APPLICABILITY",
            "status": "INDETERMINATE",
            "cardinality": "required",
            "matched": 0,
            "reason_code": "SCHEMA_MISMATCH",
            "passed": 0,
            "failed": 0,
            "indeterminate": 0,
            "requirements": [],
        },
    ],
}


def _rendered() -> str:
    localized = localize_report(_REPORT)
    assert localized is not None
    return render_markdown_report(localized, [])


def test_the_disclosure_precedes_coverage_which_precedes_findings() -> None:
    text = _rendered()
    assert text.index("What this report checked") < text.index("## Coverage")
    assert text.index("## Coverage") < text.index("## Specifications")


def test_severity_orders_fail_before_indeterminate() -> None:
    """The specification order and, within it, the entity order both put FAIL first."""
    text = _rendered()
    assert text.index("## A schema-mismatched") > text.index(
        "## Minimum clear door width"
    ), "the FAIL specification must be listed before the INDETERMINATE one"
    assert text.index("| Fail | IfcDoor") < text.index("| Indeterminate | IfcDoor")


def test_the_coverage_numerator_is_a_real_measurement_not_n_of_n() -> None:
    """One of the two specifications established nothing (SCHEMA_MISMATCH); the
    numerator must say 1, never the total 2 -- `N of N` is exactly the bug T-0025 fixed
    on screen."""
    text = _rendered()
    assert "1 of 2 specifications were evaluated." in text
    assert "2 of 2 specifications" not in text


def test_the_specification_that_established_nothing_is_named() -> None:
    text = _rendered()
    assert "1 specification established nothing" in text
    assert "A schema-mismatched specification" in text


def test_every_established_nothing_reason_code_is_excluded_from_coverage() -> None:
    """Total over every `(status, code)` `judge()` can produce -- not a hand-typed list.

    `judge()` assigns a reason code only when it reaches a verdict without inspecting
    per-entity evidence, and it pairs that early-returned code with `Status.INDETERMINATE`
    in exactly the cases where nothing was established -- as opposed to a `FAIL`/`PASS`
    pairing like `NO_SUBJECTS_BUT_REQUIRED`/`NO_SUBJECTS_AND_PROHIBITED`, which is a real
    verdict the engine reached, not an absence of evidence. Sweeping every reachable
    parameter combination and asserting the resulting set against
    `_NOTHING_ESTABLISHED_REASONS` means a future `judge()` change that produces a new
    INDETERMINATE-paired code fails this test until that code is added to the
    coverage-exclusion set here -- exactly the gap a T-0038 review found:
    `NO_REQUIREMENTS_NOTHING_ASSERTED` shipped without any test forcing it into this set,
    the same way `test_every_engine_reason_code_has_a_translatable_label`
    (`test_reasons.py`) forces every code into a translated label.

    `ReportView.tsx`'s `NOTHING_ESTABLISHED_REASONS` mirrors `_NOTHING_ESTABLISHED_REASONS`
    by hand and has no compiler or test enforcing that mirror -- this test only proves the
    Python side is total, and a change here must be carried into the TypeScript constant by
    the same hand that makes it.
    """
    observed: set[str] = set()
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
                                observed.add(code.value)
    assert observed == _NOTHING_ESTABLISHED_REASONS


def test_all_three_counts_are_always_present() -> None:
    text = _rendered()
    assert "| Passed | Failed | Could not be determined |" in text
    assert "| 1 | 1 | 1 |" in text


def test_the_disclosure_names_the_model_from_the_report_not_hardcoded() -> None:
    text = _rendered()
    assert "three_doors.ifc" in text


def test_a_specification_with_no_name_reads_nothing_was_checked() -> None:
    report = {**_REPORT, "specifications": [{**_REPORT["specifications"][1], "name": ""}]}
    localized = localize_report(report)
    assert localized is not None
    text = render_markdown_report(localized, [])
    assert "### Nothing was checked" in text


def test_a_rule_pack_selection_is_rendered_when_present() -> None:
    localized = localize_report(_REPORT)
    assert localized is not None
    text = render_markdown_report(
        localized,
        [
            {
                "uuid": "11111111-1111-1111-1111-111111111111",
                "name": "Sample pack",
                "jurisdiction": "sample",
                "region": "",
                "version": "0.1",
                "specification_count": 2,
                "checksum_sha256": "abc123",
            }
        ],
    )
    assert "## Rule packs checked" in text
    assert "Sample pack" in text


def test_no_selection_section_when_the_run_used_an_uploaded_rule_set() -> None:
    text = _rendered()
    assert "Rule packs checked" not in text


def test_a_requirement_line_uses_requirement_text_not_the_raw_facet() -> None:
    text = _rendered()
    assert "The OverallWidth shall be at least 900." in text


def test_entities_omitted_is_stated_when_present() -> None:
    report = {
        **_REPORT,
        "specifications": [
            {
                **_REPORT["specifications"][0],
                "requirements": [
                    {
                        **_REPORT["specifications"][0]["requirements"][0],
                        "entities_omitted": 5,
                    }
                ],
            }
        ],
    }
    localized = localize_report(report)
    assert localized is not None
    text = render_markdown_report(localized, [])
    assert "5 further elements counted but not listed" in text


def _headings(text: str) -> list[str]:
    """Lines that are genuinely Markdown headings -- start with "#" at position 0.

    Injected text containing the literal characters "## Coverage" still appears
    *somewhere* in the document once sanitized (it prints, just inertly); what must be
    true is that it never starts a line of its own. Raw substring checks cannot tell a
    real heading from injected text that merely contains heading-shaped characters
    mid-line -- this can.
    """
    return [line for line in text.splitlines() if line.startswith("#")]


def test_a_specification_name_cannot_inject_a_second_coverage_section() -> None:
    """T-0032 review (A3): a specification's `name` is IDS-author data, not server prose,
    and ifctester puts no constraint on it. Before this was fixed, a name containing an
    embedded blank line and a `##` heading rendered as a second, fabricated `## Coverage`
    section inside the generated file, reading "99 of 99 specifications were evaluated.
    Everything complies." -- a compliance claim nobody established, in the one artifact
    that leaves the building. Reproduced here with the reviewer's exact string.
    """
    injected_name = (
        "Doors\n\n## Coverage\n\n99 of 99 specifications were evaluated."
        "\n\nEverything complies."
    )
    report = {
        **_REPORT,
        "specifications": [{**_REPORT["specifications"][0], "name": injected_name}],
    }
    localized = localize_report(report)
    assert localized is not None
    text = render_markdown_report(localized, [])

    # The real, legitimate Coverage section is still there exactly once, as a heading.
    assert _headings(text).count("## Coverage") == 1
    # The injected text survives -- readable, not silently dropped -- but inertly: no
    # line in the document is a second, fabricated coverage claim.
    assert "Everything complies." in text, "the injected text still prints, just inertly"
    assert not any(
        line.strip() == "99 of 99 specifications were evaluated."
        for line in text.splitlines()
    )


def test_the_applicability_sentence_cannot_open_a_block_from_position_zero() -> None:
    """`applicability_text` (T-0039's localized rendering, falling back here to
    `applicability_description` since this fixture carries no `applicability_facets`) is
    rendered as a bare paragraph with nothing server-written on its own line first (unlike
    the specification name, which always follows `"### "`). A field whose first character
    is itself one Markdown treats as a block starter must not be read as one."""
    report = {
        **_REPORT,
        "specifications": [
            {
                **_REPORT["specifications"][0],
                "applicability_description": "## Forged section\n\nEverything complies.",
            }
        ],
    }
    localized = localize_report(report)
    assert localized is not None
    text = render_markdown_report(localized, [])

    assert _headings(text).count("## Coverage") == 1
    assert not any(line.startswith("## Forged section") for line in text.splitlines())
    assert "Forged section" in text, "the text still prints, just not as a heading"


def test_an_uploaded_filename_cannot_inject_structure_via_the_disclosure() -> None:
    """`disclosure_text` interpolates the uploaded model's filename -- server prose, but
    with attacker-chosen data inside it (T-0032 review, A3)."""
    report = {**_REPORT, "ifc_filename": "evil.ifc\n\n## Coverage\n\nEverything complies."}
    localized = localize_report(report)
    assert localized is not None
    text = render_markdown_report(localized, [])

    assert _headings(text).count("## Coverage") == 1
