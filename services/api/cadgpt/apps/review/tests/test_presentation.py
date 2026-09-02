"""localize_report: rendering a stored report, including one stored before this task.

`test_check_run.py` proves the current shape end to end through the real engine and the
real HTTP stack. This file proves the one thing that cannot come from a fresh run: a
document a `CheckRun` already has stored, written by an engine before
`REPORT_SCHEMA_VERSION` was bumped to 2, still localizes without raising and still renders
a requirement line -- through `description`, because it has no `basis` -- which is what
makes bumping the schema version safe rather than a silent break for every run checked
before this task shipped.
"""

from __future__ import annotations

from typing import Any

from cadgpt.apps.review.services.presentation import localize_report

#: A report exactly as `REPORT_SCHEMA_VERSION` 1 wrote it: no `basis` on the requirement, no
#: `applicability_description` on the specification -- both keys did not exist yet.
_V1_REPORT: dict[str, Any] = {
    "schema_version": 1,
    "engine_version": "0.1.0",
    "ifc_filename": "three_doors.ifc",
    "ifc_schema": "IFC4",
    "ids_title": "Accessible door width",
    "status": "FAIL",
    "specifications_passed": 0,
    "specifications_failed": 1,
    "specifications_indeterminate": 0,
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
                    ],
                    "entities_omitted": 0,
                }
            ],
        }
    ],
}


def test_a_v1_schema_document_still_localizes_through_the_fallback() -> None:
    localized = localize_report(_V1_REPORT)

    assert localized is not None
    requirement = localized["specifications"][0]["requirements"][0]
    assert (
        requirement["requirement_text"]
        == "The OverallWidth shall be {'minInclusive': '900'}"
    )
    assert requirement["entities"][0]["reason_label"], (
        "reason_label already handles an old document; this must not have regressed it"
    )


def test_a_v1_schema_document_still_gets_the_i7_disclosure() -> None:
    # The disclosure predates no schema version -- it is derived from `ifc_filename`,
    # present since `REPORT_SCHEMA_VERSION` 1 -- so a pre-existing stored document must
    # render it exactly like a fresh one.
    localized = localize_report(_V1_REPORT)

    assert localized is not None
    assert localized["disclosure_title"]
    assert "three_doors.ifc" in localized["disclosure_text"]


def test_none_stays_none() -> None:
    assert localize_report(None) is None
