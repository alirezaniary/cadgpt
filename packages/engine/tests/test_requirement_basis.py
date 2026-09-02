"""The two shapes `facet.value` can take, and the two shapes a facet's own name can take.

`test_check.py` drives `RequirementOutcome.basis` end to end through the shipped fixtures,
which exercise a `Restriction` with a single `minInclusive` bound. This file exercises the
other shapes `check.py`'s helpers must read correctly -- an `enumeration` restriction with
several members, and a bare literal with no `Restriction` at all, which is the "a literal"
operator this task's own scope names -- by constructing the real `ifctester` objects
`check.py` reads, rather than by widening the shipped `.ids` fixtures for branches they do
not otherwise need.
"""

from __future__ import annotations

import ifctester.ids
from cadgpt_engine.check import _comparisons, _facet_subject_name
from cadgpt_engine.report import Comparison


def test_a_restriction_becomes_an_operator_and_a_value_not_a_dict_repr() -> None:
    restriction = ifctester.ids.Restriction(options={"minInclusive": "900"}, base="double")
    assert _comparisons(restriction) == (Comparison(operator="minInclusive", value="900"),)


def test_an_enumeration_restriction_with_several_members_is_one_comparison_each() -> None:
    restriction = ifctester.ids.Restriction(
        options={"enumeration": ["A", "B"]}, base="string"
    )
    assert _comparisons(restriction) == (
        Comparison(operator="enumeration", value="A"),
        Comparison(operator="enumeration", value="B"),
    )


def test_a_bare_literal_value_has_no_restriction_operator_to_name() -> None:
    assert _comparisons("IfcDoor") == (Comparison(operator="literal", value="IfcDoor"),)


def test_no_value_at_all_is_no_comparisons() -> None:
    assert _comparisons(None) == ()


def test_the_subject_name_prefers_a_property_facets_base_name() -> None:
    prop = ifctester.ids.Property(propertySet="Pset_DoorCommon", baseName="FireRating")
    assert _facet_subject_name(prop) == "FireRating"


def test_the_subject_name_falls_back_to_an_attribute_facets_name() -> None:
    attribute = ifctester.ids.Attribute(name="OverallWidth")
    assert _facet_subject_name(attribute) == "OverallWidth"


def test_a_facet_with_neither_a_base_name_nor_a_name_has_no_subject() -> None:
    classification = ifctester.ids.Classification(value="X", system="Y")
    assert _facet_subject_name(classification) is None
