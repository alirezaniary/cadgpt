"""Tests for ``engine.observation.property_name``.

Unit tests exercise each rejection path, the convention-free pass-through and the
round-trip in isolation, over literal names. Integration tests drive the same construction
path across every one of the 27 names in ``docs/ddd/06-property-vocabulary.md``, extracted
from that document's own table — plus the two DEC-0031 supersessions the same document
records in prose — rather than retyped here.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from engine.observation.property_name import (
    CONVENTION_FREE_BASES,
    CONVENTIONS,
    ConventionMissing,
    PropertyName,
    UnknownConvention,
)

VOCABULARY_DOC = (
    Path(__file__).resolve().parents[4] / "docs" / "ddd" / "06-property-vocabulary.md"
)

_TABLE_ROW = re.compile(r"^\|\s*`([A-Za-z0-9_]+)`", re.MULTILINE)
_SUPERSEDED_BY = re.compile(r"`([A-Za-z0-9_]+)`\s*→\s*\*\*`([A-Za-z0-9_]+)`\*\*")


def _names_in_vocabulary() -> list[str]:
    """The §5.3 names ``docs/ddd/06-property-vocabulary.md``'s own table lists, with the
    DEC-0031 supersessions the same document records in prose applied — parsed from the
    document's own text, never retyped into this test."""
    text = VOCABULARY_DOC.read_text()
    table_section = text.split("## The counts")[0]
    names = _TABLE_ROW.findall(table_section)
    supersessions = dict(_SUPERSEDED_BY.findall(text))
    return [supersessions.get(name, name) for name in names]


# --- Unit: each rejection path, with its own name ---------------------------------------


def test_bare_measurement_name_raises_convention_missing() -> None:
    with pytest.raises(ConventionMissing, match="Area"):
        PropertyName.parse("Area")


def test_unknown_convention_segment_raises_unknown_convention() -> None:
    with pytest.raises(UnknownConvention, match="Bogus"):
        PropertyName.parse("NetFloorArea_Bogus")


# --- Unit: convention-free base parses with convention=None -----------------------------


def test_convention_free_base_parses_with_none_convention() -> None:
    name = PropertyName.parse("StallCount")
    assert name == PropertyName(base="StallCount", convention=None)


# --- Unit: round-trip, one convention-bearing name and one convention-free name ---------


def test_round_trip_for_a_convention_bearing_name() -> None:
    raw = "NetFloorArea_InsideFace"
    assert str(PropertyName.parse(raw)) == raw


def test_round_trip_for_a_convention_free_name() -> None:
    raw = "StallCount"
    assert str(PropertyName.parse(raw)) == raw


# --- Integration: every one of the 27 vocabulary names, driven from the document --------


@pytest.mark.integration
def test_vocabulary_document_lists_exactly_27_names() -> None:
    assert len(_names_in_vocabulary()) == 27


@pytest.mark.integration
def test_every_vocabulary_name_parses_without_raising() -> None:
    for raw in _names_in_vocabulary():
        PropertyName.parse(raw)


@pytest.mark.integration
def test_every_vocabulary_name_round_trips() -> None:
    for raw in _names_in_vocabulary():
        assert str(PropertyName.parse(raw)) == raw


@pytest.mark.integration
def test_conventions_and_free_bases_are_exactly_what_the_vocabulary_uses() -> None:
    """CONVENTIONS and CONVENTION_FREE_BASES carry no member the vocabulary does not use,
    and every segment/base the vocabulary uses is a member — the two closed sets and the
    document agree exactly, not just on the counts."""
    used_conventions: set[str] = set()
    used_free_bases: set[str] = set()
    for raw in _names_in_vocabulary():
        parsed = PropertyName.parse(raw)
        if parsed.convention is None:
            used_free_bases.add(parsed.base)
        else:
            used_conventions.add(parsed.convention)
    assert used_conventions == CONVENTIONS
    assert used_free_bases == CONVENTION_FREE_BASES
