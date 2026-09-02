"""The reason catalogue is total over the enum, and the enum is the stored contract."""

from __future__ import annotations

import pytest
from cadgpt_engine import ReasonCode, default_message


@pytest.mark.parametrize("code", list(ReasonCode))
def test_every_reason_code_has_text(code: ReasonCode) -> None:
    """A missing entry must be a KeyError at test time, never a blank in a report."""
    assert default_message(code).strip()


def test_reason_code_values_are_stable_identifiers() -> None:
    """These strings are persisted in stored reports and served over HTTP.

    Renaming one silently reinterprets every report already in the database, so the
    values are pinned to the member names and a rename has to be a deliberate migration.
    """
    for code in ReasonCode:
        assert code.value == code.name
