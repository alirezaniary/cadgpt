"""Wording exists for every reason the engine can produce."""

from __future__ import annotations

import pytest
from cadgpt_engine import ReasonCode

from cadgpt.apps.review.reasons import REASON_LABELS, label_for


@pytest.mark.parametrize("code", list(ReasonCode))
def test_every_engine_reason_code_has_a_translatable_label(code: ReasonCode) -> None:
    """An engine upgrade that adds a code must add wording, or a user sees an identifier."""
    assert code in REASON_LABELS, f"{code.value} has no label in cadgpt.apps.review.reasons"
    assert str(REASON_LABELS[code]).strip()


def test_no_label_exists_for_a_code_the_engine_no_longer_emits() -> None:
    """Dead wording is a sign the mapping drifted from the engine it describes."""
    known = {code.value for code in ReasonCode}
    orphans = sorted(str(key) for key in REASON_LABELS if str(key) not in known)
    assert orphans == []


def test_an_unknown_code_degrades_to_the_code_itself() -> None:
    """A report written by a newer engine must not render as a blank line."""
    assert label_for("SOMETHING_NEW") == "SOMETHING_NEW"
    assert label_for(None) is None
    assert label_for("") is None
