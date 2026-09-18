from __future__ import annotations

import json
from pathlib import Path

import pytest
from cadgpt_regulations.rule_normalization import (
    RuleNormalizationError,
    normalize_rule_token,
)

FIXTURE = Path(__file__).parent / "fixtures" / "inbr_transcript_volume10_page586.json"


def test_normalization_preserves_existing_inbr_persian_source_token() -> None:
    transcript = json.loads(FIXTURE.read_text(encoding="utf-8"))
    source_text = transcript["tables"][0]["text_fa"].splitlines()[0]
    token = normalize_rule_token(source_text)

    assert token.original_fa == source_text
    assert token.normalized_fa == source_text
    assert "10-6-5" in token.ascii_view
    assert token.numeric_value is None
    assert token.unit_ucum is None


def test_normalization_maps_explicit_persian_unit_and_digits() -> None:
    token = normalize_rule_token("\u06f1\u066b\u06f5", unit_fa="متر مربع")

    assert token.original_fa == "\u06f1\u066b\u06f5"
    assert token.ascii_view == "1\u066b5"
    assert str(token.numeric_value) == "1.5"
    assert token.unit_ucum == "m2"


def test_normalization_rejects_ambiguous_unit() -> None:
    with pytest.raises(RuleNormalizationError, match="ambiguous"):
        normalize_rule_token("\u06f1", unit_fa="واحد")
