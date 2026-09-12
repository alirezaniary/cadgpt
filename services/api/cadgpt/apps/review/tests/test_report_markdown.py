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

import re
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from cadgpt_engine import SEVERITY_RANK
from django.utils import translation

from cadgpt.apps.review.services.presentation import localize_report
from cadgpt.apps.review.services.report_markdown import render_markdown_report


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


def test_established_nothing_reads_the_field_presentation_computed() -> None:
    """T-0052: this file no longer decides which reason codes mean "nothing was
    evaluated" -- `presentation.localize_report` already annotates `established_nothing`
    on every specification, from `cadgpt_engine.established_nothing`, before this module
    ever sees the report. `test_nothing_established_reason_codes_are_total_over_judge`
    (`packages/engine/tests/test_judgement.py`) is the exhaustive test over every
    `judge()` combination, total over `NOTHING_ESTABLISHED_REASONS`; this test only proves
    the Markdown renderer actually *reads* that field rather than re-deriving one of its
    own from `reason_code` -- forcing `established_nothing` to `True` on a specification
    whose `reason_code` is `None` (a real evaluation) and confirming the renderer follows
    the field, not the code, is exactly the mutation a regression back to a hand-copied
    set would fail.
    """
    localized = localize_report(_REPORT)
    assert localized is not None
    forced = {
        **localized,
        "specifications": [
            {**spec, "established_nothing": True} for spec in localized["specifications"]
        ],
    }
    text = render_markdown_report(forced, [])
    assert "0 of 2 specifications were evaluated." in text
    assert "2 specifications established nothing" in text


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


def test_a_specification_with_a_rule_pack_states_its_source_beneath_the_heading() -> None:
    """T-0049: a specification's own `rule_pack` (`{"uuid", "name", "version"}`, added by
    `execution._attribute_specifications`) is resolved against `rule_pack_selection` for
    the jurisdiction/region that entry additionally carries, and its `source_citation` is
    rendered as a blockquote beneath -- the same fact `RulePack.source_citation` exists to
    make reachable from a finding (`prd.md` 5.7), not just from the top-of-file selection
    block `test_a_rule_pack_selection_is_rendered_when_present` already covers.
    """
    report = {
        **_REPORT,
        "specifications": [
            {
                **_REPORT["specifications"][0],
                "rule_pack": {
                    "uuid": "11111111-1111-1111-1111-111111111111",
                    "name": "Sample pack",
                    "version": "0.1",
                },
            },
            _REPORT["specifications"][1],
        ],
    }
    localized = localize_report(report)
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
                "source_citation": "Sample regulation, 2026 edition, article 4.",
            }
        ],
    )
    assert "Source: Sample pack — sample v0.1" in text
    assert "Sample regulation, 2026 edition, article 4." in text
    # The second specification carries no `rule_pack` at all -- no source line under
    # *its* heading. `### A schema-mismatched specification` (the Specifications-section
    # heading, not its earlier mention in the "established nothing" bullet list above it)
    # is the unambiguous anchor; nothing follows it in this fixture's two-specification
    # report, so the rest of the file is exactly that spec's own section.
    heading_index = text.index("### A schema-mismatched specification")
    assert "Source:" not in text[heading_index:]


def test_a_specification_attributed_to_one_pack_never_cites_the_other() -> None:
    """T-0049 review F1: `citation_by_uuid.get(pack_ref["uuid"], {})` must resolve each
    specification's citation by *its own* pack's uuid, never by selection order.

    Every test above this one selects from exactly one pack, so none of them can see
    cross-pack leakage: the reviewer proved that replacing the `.get(pack_ref["uuid"], {})`
    lookup with `next(iter(citation_by_uuid.values()), {})` (always the *first* pack's
    citation, whichever pack a finding actually belongs to) left every existing test in
    this file green. A selection with two packs, and two specifications each attributed to
    a *different* one of them, is the only report shape that can catch it: each
    specification's own citation must be its own pack's `source_citation`, and the other
    pack's citation must never appear in its section.
    """
    report = {
        **_REPORT,
        "specifications": [
            {
                **_REPORT["specifications"][0],
                "rule_pack": {
                    "uuid": "11111111-1111-1111-1111-111111111111",
                    "name": "Pack A",
                    "version": "1.0",
                },
            },
            {
                **_REPORT["specifications"][1],
                "name": "A specification from pack B",
                "rule_pack": {
                    "uuid": "22222222-2222-2222-2222-222222222222",
                    "name": "Pack B",
                    "version": "2.0",
                },
            },
        ],
    }
    localized = localize_report(report)
    assert localized is not None
    text = render_markdown_report(
        localized,
        [
            {
                "uuid": "11111111-1111-1111-1111-111111111111",
                "name": "Pack A",
                "jurisdiction": "jurisdiction-a",
                "region": "",
                "version": "1.0",
                "specification_count": 1,
                "checksum_sha256": "aaa",
                "source_citation": "Citation belonging to pack A only.",
            },
            {
                "uuid": "22222222-2222-2222-2222-222222222222",
                "name": "Pack B",
                "jurisdiction": "jurisdiction-b",
                "region": "",
                "version": "2.0",
                "specification_count": 1,
                "checksum_sha256": "bbb",
                "source_citation": "Citation belonging to pack B only.",
            },
        ],
    )
    # FAIL (spec 0, pack A) sorts before INDETERMINATE (spec 1, pack B) -- both headings
    # must be present so slicing the text between them is meaningful.
    spec_a_index = text.index("### Minimum clear door width 900 mm")
    spec_b_index = text.index("### A specification from pack B")
    assert spec_a_index < spec_b_index
    spec_a_section = text[spec_a_index:spec_b_index]
    spec_b_section = text[spec_b_index:]

    assert "Citation belonging to pack A only." in spec_a_section
    assert "Citation belonging to pack B only." not in spec_a_section
    assert "Citation belonging to pack B only." in spec_b_section
    assert "Citation belonging to pack A only." not in spec_b_section


def test_a_specification_with_no_rule_pack_states_no_source() -> None:
    """The ordinary case today -- a run against an uploaded `RuleSet` -- and every
    document stored before T-0049 alike: no `rule_pack` key on any specification, and
    `render_markdown_report` must not invent a source line for either.
    """
    text = _rendered()
    assert "Source:" not in text


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


def test_report_view_severity_rank_matches_the_engine() -> None:
    """T-0052: `ReportView.tsx` cannot import `cadgpt_engine.SEVERITY_RANK` the way this
    module does -- it keeps its own copy for the client-side sort a report from a *newer*
    engine, read by an *older* frontend, still needs (T-0025 review Q2's
    `UNKNOWN_STATUS_RANK` fallback has no wire-format equivalent this module could hand
    down instead). Reading that literal back out of the `.tsx` source and comparing it to
    the engine's own `SEVERITY_RANK` is the drift test for the one duplicate this task
    could not eliminate structurally: a rank reordered on one side and not the other fails
    here rather than silently sorting the file and the screen differently.
    """
    tsx_path = (
        Path(__file__).resolve().parents[6]
        / "services"
        / "web"
        / "src"
        / "components"
        / "ReportView.tsx"
    )
    source = tsx_path.read_text(encoding="utf-8")
    match = re.search(r"const SEVERITY_RANK: Record<Status, number> = \{([^}]*)\};", source)
    assert match is not None, "ReportView.tsx no longer declares SEVERITY_RANK as expected"
    frontend_rank = {
        name: int(value) for name, value in re.findall(r"(\w+):\s*(\d+)", match.group(1))
    }
    engine_rank = {status.value: rank for status, rank in SEVERITY_RANK.items()}
    assert frontend_rank == engine_rank
