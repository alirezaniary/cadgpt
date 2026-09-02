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
    """A prohibited-cardinality IDS: no IfcDoor may be present (minOccurs=maxOccurs=0)."""
    return FIXTURES / "door_prohibited.ids"


@pytest.fixture(scope="session")
def door_name_recorded_ids() -> Path:
    """An IDS every door in `three_doors_ifc` genuinely satisfies: each has a Name."""
    return FIXTURES / "door_name_recorded.ids"
