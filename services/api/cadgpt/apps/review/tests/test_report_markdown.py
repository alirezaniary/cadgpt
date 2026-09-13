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
import uuid
from collections.abc import Iterator
from datetime import datetime, timedelta
from datetime import timezone as dt_timezone
from pathlib import Path
from typing import Any

import pytest
from cadgpt_engine import SEVERITY_RANK
from django.utils import translation
from django.utils.translation import pgettext

from cadgpt.apps.review.services.presentation import localize_report
from cadgpt.apps.review.services.report_markdown import render_markdown_report
from cadgpt.apps.review.tests.test_check_run import _is_persian, _persian

#: A fixed run identity for every test below -- what changed is the report's content, not
#: which run produced it, so one constant keeps every assertion about the identifying block
#: (T-0055) independent of which fixture a given test happens to render.
_RUN_UUID = uuid.UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")
_CHECKED_AT = datetime(2026, 9, 13, 18, 42, 10, tzinfo=dt_timezone.utc)


def _persian_pgettext(context: str, msgid: str) -> str:
    """The `pgettext` analogue of `test_check_run.py`'s `_persian`: what `msgid` actually
    translates to in the real, compiled `fa` catalogue under `msgctxt` `context`, computed
    with an explicit, local `translation.override` -- used only to build the *expected*
    side of an assertion, never anywhere near the code under test. `requirements.py`'s
    `cardinality_label` renders through `pgettext_lazy("specification cardinality", ...)`,
    not bare `gettext`, so a plain `_persian` lookup would miss the msgctxt entirely and
    silently fall back to any unscoped `msgid` of the same spelling -- this reproduces the
    exact lookup `cardinality_label` performs, against the same compiled `.mo`.
    """
    with translation.override("fa"):
        return str(pgettext(context, msgid))


@pytest.fixture(autouse=True)
def english() -> Iterator[None]:
    with translation.override("en"):
        yield


def _render(
    report: dict[str, Any], rule_pack_selection: list[dict[str, Any]] | None = None
) -> str:
    """`render_markdown_report`, with the T-0055 identity kwargs already supplied.

    Every test in this file renders the same run identity (`_RUN_UUID`, `_CHECKED_AT`)
    unless it is specifically testing that block -- see
    `test_the_file_identifies_its_own_run_and_check_date` below.
    """
    return render_markdown_report(
        report, rule_pack_selection, run_uuid=_RUN_UUID, checked_at=_CHECKED_AT
    )


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
    return _render(localized, [])


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
    text = _render(forced, [])
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
    text = _render(localized, [])
    assert "### Nothing was checked" in text


def test_a_rule_pack_selection_is_rendered_when_present() -> None:
    localized = localize_report(_REPORT)
    assert localized is not None
    text = _render(
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
    text = _render(
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
    text = _render(
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
    text = _render(localized, [])
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
    text = _render(localized, [])

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
    text = _render(localized, [])

    assert _headings(text).count("## Coverage") == 1
    assert not any(line.startswith("## Forged section") for line in text.splitlines())
    assert "Forged section" in text, "the text still prints, just not as a heading"


def test_an_uploaded_filename_cannot_inject_structure_via_the_disclosure() -> None:
    """`disclosure_text` interpolates the uploaded model's filename -- server prose, but
    with attacker-chosen data inside it (T-0032 review, A3)."""
    report = {**_REPORT, "ifc_filename": "evil.ifc\n\n## Coverage\n\nEverything complies."}
    localized = localize_report(report)
    assert localized is not None
    text = _render(localized, [])

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


def test_the_file_identifies_its_own_run_and_check_date() -> None:
    """T-0055: the file must stand on its own once it leaves the building -- the run this
    document is a record of, and when it was judged, must be readable from the body alone,
    with no dependence on a filename a rename or an archive step can discard.
    """
    localized = localize_report(_REPORT)
    assert localized is not None
    run_uuid = uuid.UUID("11111111-2222-3333-4444-555555555555")
    checked_at = datetime(2026, 1, 15, 9, 5, 0, tzinfo=dt_timezone.utc)
    text = render_markdown_report(localized, [], run_uuid=run_uuid, checked_at=checked_at)
    assert "Run 11111111-2222-3333-4444-555555555555" in text
    assert "Checked 2026-01-15 09:05 UTC" in text


def test_the_check_date_is_rendered_in_utc_regardless_of_the_input_timezone() -> None:
    """A reader of an archived file may be in any timezone -- `checked_at` must always
    read as one unambiguous instant, never a local time with no timezone stated."""
    localized = localize_report(_REPORT)
    assert localized is not None
    tehran = dt_timezone(timedelta(hours=3, minutes=30))
    checked_at = datetime(2026, 1, 15, 12, 35, 0, tzinfo=tehran)
    text = render_markdown_report(localized, [], run_uuid=_RUN_UUID, checked_at=checked_at)
    assert "Checked 2026-01-15 09:05 UTC" in text


def test_cardinality_renders_as_a_translated_word_not_the_raw_token() -> None:
    """T-0055 / T-0036: `spec["cardinality"]` is `ifctester`'s own machine token
    (`"required"` here); the matched line must print the translated word `cardinality_
    label` supplies, the same fix `ReportView.tsx` already applies on screen, never the
    bare English token as data.

    English alone cannot prove this: `pgettext("specification cardinality", "required")`
    *is* `"required"` in English, so this assertion passes identically whether
    `cardinality_label` runs or is deleted outright. It stays here only as the structural
    check (the word sits after the matched-count line, in the right place); the actual
    translation is proven under `fa`, below.
    """
    text = _rendered()
    assert "3 elements matched · required" in text


def test_cardinality_renders_as_the_persian_word_when_the_active_language_is_persian() -> (
    None
):
    """T-0055 fix-now: the review of this task found that the test above cannot detect a
    deleted or reverted `cardinality_label` -- `pgettext` returns the bare English token
    back in English regardless of whether the function is even called. Rendering under
    `fa` and checking the real compiled catalogue (`_persian_pgettext`, `_is_persian` --
    the latter imported from `test_check_run.py` rather than reinvented) is what actually
    exercises the feature: reverting `cardinality_label` to
    `lambda cardinality: cardinality` makes the assertion below fail, because the rendered
    word would then be the raw English token, not Persian script.
    """
    localized = localize_report(_REPORT)
    assert localized is not None
    with translation.override("fa"):
        text = _render(localized, [])
    expected = _persian_pgettext("specification cardinality", "required")
    assert _is_persian(expected), "the fa catalogue itself must actually be Persian"
    assert f"· {expected}" in text
    assert "· required" not in text


def test_the_detail_column_states_plainly_that_it_is_upstream_wording() -> None:
    """T-0055: `entity.detail` is `ifctester`'s own English sentence -- not ours to
    translate (checked directly against `ifctester` 0.8.5's source: no `.po`/`.mo`, no
    i18n hook, every `Result.to_string()` override a hardcoded English f-string). The
    honest fix is a plain, one-time statement in the document, not a silent untranslated
    fragment and not a machine translation of a sentence whose precision is the point.
    """
    text = _rendered()
    assert "the checking engine's own wording, in English" in text


def test_the_detail_column_caption_is_translated_when_the_active_language_is_persian() -> (
    None
):
    """T-0055 fix-now: the caption above is server prose -- ours to translate, unlike the
    Detail column's own cell contents (`entity.detail`, `ifctester`'s English, captioned as
    such on purpose). If the `msgid` in `report_markdown.py` ever drifted from the `msgid`
    compiled into `cadgpt/locale/fa/LC_MESSAGES/django.po`, `gettext` would silently fall
    back to the English source string; checking against the real compiled catalogue via
    `_persian` (imported from `test_check_run.py`), and confirming the result is actually
    Persian script via `_is_persian`, is what catches that silent fallback rather than a
    hand-typed Persian string that could drift right along with a bug.
    """
    with translation.override("fa"):
        text = _rendered()
    expected = _persian(
        "Where shown, the Detail column is the checking engine's own wording, in English."
    )
    assert _is_persian(expected), "the fa catalogue itself must actually be Persian"
    assert expected in text


def test_the_file_identifies_its_run_and_check_date_when_language_is_persian() -> None:
    """T-0055 fix-now: the run-identifying line is composed by the server, not by
    `ifctester`, so -- unlike `entity.detail` -- it must render in the reader's language
    the same as every other server-composed sentence in this file. Checked against the
    real compiled `fa` catalogue via `_persian` (imported from `test_check_run.py`) rather
    than a hand-typed Persian guess, so a deleted or drifted `msgid`/`msgstr` in
    `django.po` fails this test instead of silently reverting the line to English.
    """
    localized = localize_report(_REPORT)
    assert localized is not None
    run_uuid = uuid.UUID("11111111-2222-3333-4444-555555555555")
    checked_at = datetime(2026, 1, 15, 9, 5, 0, tzinfo=dt_timezone.utc)
    with translation.override("fa"):
        text = render_markdown_report(
            localized, [], run_uuid=run_uuid, checked_at=checked_at
        )
    expected_template = _persian("Run %(run_id)s · Checked %(date)s")
    assert _is_persian(expected_template), "the fa catalogue must actually be Persian"
    expected_line = expected_template % {
        "run_id": str(run_uuid),
        "date": "2026-01-15 09:05 UTC",
    }
    assert expected_line in text
