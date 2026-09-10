from __future__ import annotations

from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture(scope="session")
def three_doors_ifc() -> Path:
    """Three real doors: one compliant, one too narrow, one with no width recorded."""
    return FIXTURES / "three_doors.ifc"


@pytest.fixture(scope="session")
def door_width_ids() -> Path:
    """A real IDS rule set: doors must be at least 900mm wide."""
    return FIXTURES / "door_width.ids"


@pytest.fixture(scope="session")
def door_prohibited_ids() -> Path:
    """A prohibited-cardinality IDS: no IfcDoor may be present (minOccurs=maxOccurs=0).

    `three_doors_ifc` has three doors, so this prohibition matches real subjects
    (`PROHIBITED_SUBJECTS_PRESENT`) -- for the zero-subject prohibited case, see
    `window_prohibited_ids`.
    """
    return FIXTURES / "door_prohibited.ids"


@pytest.fixture(scope="session")
def window_prohibited_ids() -> Path:
    """T-0037: a prohibited-cardinality IDS matching *nothing* -- `three_doors_ifc`
    contains no `IfcWindow` at all, so this applicability itself matches zero subjects
    (`NO_SUBJECTS_AND_PROHIBITED`), unlike `door_prohibited_ids` above. This is the case
    the T-0028 review reproduced: a prohibited specification that legitimately reaches
    PASS while every requirement beneath it evaluated nothing.
    """
    return FIXTURES / "window_prohibited.ids"


@pytest.fixture(scope="session")
def door_name_recorded_ids() -> Path:
    """An IDS every door in `three_doors_ifc` genuinely satisfies: each has a Name."""
    return FIXTURES / "door_name_recorded.ids"


@pytest.fixture(scope="session")
def door_schema_mismatch_ids() -> Path:
    """T-0037 review round 2 (F1): `door_name_recorded_ids` in every way except its
    declared `ifcVersion`, which names only `IFC2X3` -- `three_doors_ifc` is `IFC4`, so
    the specification's own applicability is never established (`SCHEMA_MISMATCH`,
    `UNDETERMINED_APPLICABILITY`) even though `ifctester` still matches all three real
    doors and genuinely evaluates the requirement against them (a real `PASS`, real
    non-zero counts).
    """
    return FIXTURES / "door_schema_mismatch.ids"


@pytest.fixture(scope="session")
def door_optional_no_requirements_ids() -> Path:
    """T-0038: an optional-cardinality IDS naming IFCDOOR with zero requirement facets.

    Matches real doors in `three_doors_ifc` but asserts nothing about them.
    """
    return FIXTURES / "door_optional_no_requirements.ids"


@pytest.fixture(scope="session")
def door_required_no_requirements_ids() -> Path:
    """T-0038's control case: `required` cardinality with zero requirement facets, a
    legitimate existence check that must stay PASS.
    """
    return FIXTURES / "door_required_no_requirements.ids"
