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
