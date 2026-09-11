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
from cadgpt_engine.check import (
    _applicability_facet,
    _comparisons,
    _facet_subject_name,
    _facet_subject_name_comparisons,
)
from cadgpt_engine.report import ApplicabilityFacet, Comparison


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


# T-0039: the attribute or property *name* can itself be an `xs:restriction` -- `Facet.
# parse` is generic over every parameter the IDS wraps in `<xs:restriction>`, `name`
# included -- which is exactly the case `_facet_subject_name` above returns `None` for
# without this sibling function, that restriction was simply dropped.


def test_a_restricted_attribute_name_is_carried_as_name_comparisons_not_dropped() -> None:
    attribute = ifctester.ids.Attribute(
        name=ifctester.ids.Restriction(
            options={"enumeration": ["OverallWidth", "OverallHeight"]}, base="string"
        )
    )
    assert _facet_subject_name(attribute) is None
    assert _facet_subject_name_comparisons(attribute) == (
        Comparison(operator="enumeration", value="OverallWidth"),
        Comparison(operator="enumeration", value="OverallHeight"),
    )


def test_a_restricted_property_base_name_is_carried_the_same_way() -> None:
    prop = ifctester.ids.Property(
        propertySet="Pset_DoorCommon",
        baseName=ifctester.ids.Restriction(options={"pattern": "Fire.*"}, base="string"),
    )
    assert _facet_subject_name(prop) is None
    assert _facet_subject_name_comparisons(prop) == (
        Comparison(operator="pattern", value="Fire.*"),
    )


def test_a_literal_name_has_no_name_comparisons_to_state() -> None:
    attribute = ifctester.ids.Attribute(name="OverallWidth")
    assert _facet_subject_name_comparisons(attribute) == ()


def test_a_facet_with_no_name_at_all_has_no_name_comparisons() -> None:
    classification = ifctester.ids.Classification(value="X", system="Y")
    assert _facet_subject_name_comparisons(classification) == ()


# T-0039: `ApplicabilityFacet` -- the structured counterpart of one term in
# `applicability_description`.


def test_an_entity_facet_becomes_structured_data_with_its_class_name() -> None:
    entity = ifctester.ids.Entity(name="IFCDOOR")
    facet = _applicability_facet(entity)
    assert facet == ApplicabilityFacet(
        facet_type="entity",
        name="IFCDOOR",
        predefined_type=None,
        description="All IFCDOOR data",
    )


def test_an_entity_facet_with_a_predefined_type_carries_it_too() -> None:
    entity = ifctester.ids.Entity(name="IFCWALL", predefinedType="SOLIDWALL")
    facet = _applicability_facet(entity)
    assert facet.name == "IFCWALL"
    assert facet.predefined_type == "SOLIDWALL"
    assert facet.description == "All IFCWALL data of type SOLIDWALL"


def test_a_non_entity_facet_still_carries_its_own_name_as_data() -> None:
    """The engine names what it reads regardless of facet type -- the same shape
    `RequirementBasis.name`/`_facet_subject_name` already use, generic over the facet.
    *Rendering* only `Entity` into a sentence is the service's decision
    (`cadgpt.apps.review.applicability`), not this layer's: gating here would make the
    engine responsible for wording it never authors.
    """
    attribute = ifctester.ids.Attribute(name="Name")
    facet = _applicability_facet(attribute)
    assert facet.facet_type == "attribute"
    assert facet.name == "Name"
    assert facet.predefined_type is None
    assert facet.description == "Data where the Name is provided"


def test_a_restricted_entity_name_has_no_structured_name_either() -> None:
    entity = ifctester.ids.Entity(
        name=ifctester.ids.Restriction(options={"enumeration": ["IFCDOOR", "IFCWINDOW"]})
    )
    facet = _applicability_facet(entity)
    assert facet.name is None


def test_a_restricted_predefined_type_also_drops_the_literal_name() -> None:
    """T-0039 review, F2. `name` is a plain literal ("IFCDOOR") here, but `predefinedType`
    is itself restricted to a set (`DOOR` or `GATE`) -- the applicability is genuinely
    narrower than "every IFCDOOR", but `predefined_type` alone collapsing to `None` is
    indistinguishable, downstream, from "no predefinedType stated at all": the service
    would render the unrestricted "All IFCDOOR data" template and overstate what the
    specification covers (reviewer's live repro: such a specification matched 0 real
    elements and FAILed, while the printed line claimed to cover every IFCDOOR in a model
    that has three). `name` must also drop to `None` here so the whole facet falls back to
    `description`, which still states the restriction correctly.
    """
    entity = ifctester.ids.Entity(
        name="IFCDOOR",
        predefinedType=ifctester.ids.Restriction(options={"enumeration": ["DOOR", "GATE"]}),
    )
    facet = _applicability_facet(entity)
    assert facet.name is None
    assert facet.predefined_type is None
    assert facet.facet_type == "entity"
