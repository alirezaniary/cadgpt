"""applicability_text: the sentence built from a specification's structured
`applicability_facets` (T-0039).

Mirrors `test_requirements.py`'s own approach and its reasoning for activating English
deliberately (`english` below): what this file proves is the branching -- only an `Entity`
facet with a literal `name` renders, a `predefinedType` extends the template, more than
one facet joins with the localized joiner instead of the engine's hardcoded `" and "`, and
anything this table does not recognise falls back to each facet's own `description` --
not any one language's wording, which the real running API already proved
(`docs/tasks/T-0039-the-subject-of-a-citation.md`'s evidence).
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from django.utils import translation

from cadgpt.apps.review.applicability import applicability_text


@pytest.fixture(autouse=True)
def english() -> Iterator[None]:
    with translation.override("en"):
        yield


def test_a_single_entity_facet_renders_its_class_name() -> None:
    """`description` is deliberately *not* the sentence rendering would produce --
    upstream's English happens to read identically to this table's own English template,
    which would let a mutation that always returned `description` hide behind that
    coincidence. A `description` that reads differently is what makes this assertion mean
    "rendered from `name`", not "the field ifctester already wrote".
    """
    facets = [
        {
            "facet_type": "entity",
            "name": "IFCDOOR",
            "predefined_type": None,
            "description": "upstream's own unrendered fallback sentence for this facet",
        }
    ]
    assert applicability_text(facets, "fallback") == "All IFCDOOR data"


def test_an_entity_facet_with_a_predefined_type_states_it() -> None:
    facets = [
        {
            "facet_type": "entity",
            "name": "IFCWALL",
            "predefined_type": "SOLIDWALL",
            "description": "upstream's own unrendered fallback sentence for this facet",
        }
    ]
    assert applicability_text(facets, "fallback") == "All IFCWALL data of type SOLIDWALL"


def test_two_entity_facets_join_with_the_localized_joiner() -> None:
    """T-0039's second finding: `check.py` built `applicability_description` with a bare
    `" and ".join(...)` -- English even when every facet inside it renders in Persian. This
    is the test that would have caught it: the joiner comes from this module's own
    `_JOINER`, not from the engine.
    """
    facets = [
        {
            "facet_type": "entity",
            "name": "IFCDOOR",
            "predefined_type": None,
            "description": "upstream door fallback",
        },
        {
            "facet_type": "entity",
            "name": "IFCWINDOW",
            "predefined_type": None,
            "description": "upstream window fallback",
        },
    ]
    assert (
        applicability_text(facets, "fallback") == "All IFCDOOR data and All IFCWINDOW data"
    )


def test_a_non_entity_facet_falls_back_to_its_own_description() -> None:
    """`Property`, `Attribute`, `Classification`, `PartOf` and `Material` do not share the
    `Entity` sentence shape; rendering them would be the renderer registry T-0027 and this
    task both forbid building for a facet type the shipped fixtures do not exercise.
    """
    facets = [
        {
            "facet_type": "attribute",
            "name": "Name",
            "predefined_type": None,
            "description": "Data where the Name is provided",
        }
    ]
    assert applicability_text(facets, "fallback") == "Data where the Name is provided"


def test_an_entity_facet_and_a_non_entity_facet_join_one_localized_one_not() -> None:
    facets = [
        {
            "facet_type": "entity",
            "name": "IFCDOOR",
            "predefined_type": None,
            "description": "upstream door fallback",
        },
        {
            "facet_type": "attribute",
            "name": "Name",
            "predefined_type": None,
            "description": "Data where the Name is provided",
        },
    ]
    assert (
        applicability_text(facets, "fallback")
        == "All IFCDOOR data and Data where the Name is provided"
    )


def test_a_restricted_entity_name_has_no_literal_class_to_render_and_falls_back() -> None:
    """An `Entity` facet whose own `name` is itself an `xs:restriction` (e.g. "IFCDOOR or
    IFCWINDOW") reaches here with `name: null` -- `check.py`'s `_applicability_facet`
    already collapsed it, the same degrade `_facet_subject_name` makes for a requirement's
    restricted name. There is no single class name to put in the template.
    """
    facets = [
        {
            "facet_type": "entity",
            "name": None,
            "predefined_type": None,
            "description": "All {'enumeration': ['IFCDOOR', 'IFCWINDOW']} data",
        }
    ]
    assert (
        applicability_text(facets, "fallback")
        == "All {'enumeration': ['IFCDOOR', 'IFCWINDOW']} data"
    )


def test_a_document_stored_before_applicability_facets_existed_falls_back_whole() -> None:
    """REPORT_SCHEMA_VERSION 3 and earlier has no `applicability_facets` key at all --
    `facets` arrives as `None`, and the whole engine-joined sentence is used as-is, exactly
    as it always rendered before this task."""
    old_description = "All IFCDOOR data and Data where the Name is provided"
    assert applicability_text(None, old_description) == old_description


def test_an_empty_applicability_joins_to_the_empty_string() -> None:
    assert applicability_text([], "") == ""
