"""requirement_text: the sentence built from a requirement's structured `basis`.

Translated wording is proven against the real running API in two languages
(`docs/tasks/T-0027-requirement-as-structured-citation.md`'s evidence) rather than here.
What this file proves is the branching: a bound renders a comparison, no bound states only
that the attribute must be provided, cardinality picks "shall" / "shall not" / "may", an
`enumeration` joins as a disjunction ("or") while every other multi-part bound joins as a
conjunction ("and"), and anything this table does not recognise -- an unsupported facet
type, no `basis` at all, or a comparison operator not in `_COMPARISON_TEMPLATES` -- falls
back to `description` rather than to a blank line or, worse, a confident sentence for the
wrong rule. That is a property of the branching, not of any one language's wording, so
`english` below activates English deliberately (T-0083 made `fa` the process-wide default,
including for a bare pytest run with no request in sight -- see `cadgpt.apps.base.tasks.
BaseTask` and `LANGUAGE_CODE` in `cadgpt/config/settings/base.py`) rather than asserting
against Persian sentences re-encoded by hand here, which would test this file's own
transcription as much as `requirement_text`.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest
from django.utils import translation

from cadgpt.apps.review.requirements import requirement_text


@pytest.fixture(autouse=True)
def english() -> Iterator[None]:
    with translation.override("en"):
        yield


def test_a_bounded_required_attribute_becomes_a_sentence_not_the_stored_description() -> (
    None
):
    basis = {
        "facet_type": "attribute",
        "name": "OverallWidth",
        "cardinality": "required",
        "comparisons": [{"operator": "minInclusive", "value": "900"}],
    }
    assert (
        requirement_text(basis, "The OverallWidth shall be {'minInclusive': '900'}")
        == "The OverallWidth shall be at least 900."
    )


def test_a_required_attribute_with_no_bound_states_only_that_it_must_be_provided() -> None:
    basis = {
        "facet_type": "attribute",
        "name": "Name",
        "cardinality": "required",
        "comparisons": [],
    }
    assert requirement_text(basis, "fallback") == "The Name shall be provided."


def test_a_prohibited_attribute_renders_shall_not() -> None:
    basis = {
        "facet_type": "attribute",
        "name": "OverallWidth",
        "cardinality": "prohibited",
        "comparisons": [],
    }
    assert requirement_text(basis, "fallback") == "The OverallWidth shall not be provided."


def test_an_optional_attribute_renders_may() -> None:
    basis = {
        "facet_type": "attribute",
        "name": "FireRating",
        "cardinality": "optional",
        "comparisons": [{"operator": "literal", "value": "F90"}],
    }
    assert requirement_text(basis, "fallback") == "The FireRating may be F90."


def test_an_enumeration_becomes_a_disjunction_not_a_conjunction() -> None:
    """IDS `xs:enumeration` is a disjunction: the value must be *one of* the members, never
    all of them at once. Joining with "and" would tell an architect the attribute must
    equal two values simultaneously -- a citation no model could ever satisfy and no IDS
    ever asked for. This asserts the rendered sentence, not `_comparisons`' output: the
    engine already had a correct test for the data shape
    (`packages/engine/tests/test_requirement_basis.py`); the bug this test guards was in
    how the *service* joined that data into a sentence, and only a test of the sentence
    would have caught it.
    """
    basis = {
        "facet_type": "attribute",
        "name": "Name",
        "cardinality": "required",
        "comparisons": [
            {"operator": "enumeration", "value": "D-01"},
            {"operator": "enumeration", "value": "D-02"},
        ],
    }
    assert requirement_text(basis, "fallback") == "The Name shall be D-01 or D-02."


def test_a_range_with_two_bounds_stays_a_conjunction() -> None:
    """The direction this fix must not break: a real range (both a minimum and a maximum)
    is a conjunction, and must keep reading as one.
    """
    basis = {
        "facet_type": "attribute",
        "name": "OverallWidth",
        "cardinality": "required",
        "comparisons": [
            {"operator": "minInclusive", "value": "900"},
            {"operator": "maxInclusive", "value": "1200"},
        ],
    }
    assert (
        requirement_text(basis, "fallback")
        == "The OverallWidth shall be at least 900 and at most 1200."
    )


def test_an_unrecognised_operator_falls_back_to_description() -> None:
    """`totalDigits` is a real, valid IDS restriction (`ifctester.facet.Restriction.asdict`
    lists it) that this table does not have a template for. Rendering "%(value)s" for it
    would say "shall be 4" for a rule that actually means "at most 4 significant digits" --
    a wrong sentence with the same confidence as a right one. The only safe degrade is the
    one already used for a report stored before `basis` existed: fall back to `description`.
    """
    basis = {
        "facet_type": "attribute",
        "name": "Name",
        "cardinality": "required",
        "comparisons": [{"operator": "totalDigits", "value": "4"}],
    }
    assert (
        requirement_text(basis, "the real ifctester sentence")
        == "the real ifctester sentence"
    )


def test_a_facet_type_this_table_does_not_render_falls_back_to_description() -> None:
    """`Property`, `Entity`, `Classification`, `PartOf` and `Material` do not share the
    attribute sentence shape; rendering them would be the renderer registry this task's
    scope forbids building for facet types the shipped fixtures do not exercise.
    """
    basis = {
        "facet_type": "entity",
        "name": "IFCDOOR",
        "cardinality": "required",
        "comparisons": [],
    }
    assert requirement_text(basis, "All IFCDOOR data") == "All IFCDOOR data"


def test_a_document_stored_before_basis_existed_falls_back_to_description() -> None:
    """REPORT_SCHEMA_VERSION 1 has no `basis` key at all -- this is what makes the bump to
    2 safe: an old document degrades to the sentence the engine already wrote instead of
    raising `KeyError` or rendering a blank line.
    """
    old_description = "The OverallWidth shall be {'minInclusive': '900'}"
    assert requirement_text(None, old_description) == old_description


# T-0039: the attribute *name* can itself be a restriction (`name_comparisons`), not just
# the value. Before this fix, `basis["name"]` came back `None` for exactly this case and
# the sentence fell back to `description` -- upstream's own dict-repr string,
# `"The {'enumeration': [...]} shall be provided"` -- as the report's primary line.


def test_a_restricted_attribute_name_becomes_a_disjunctive_subject_not_a_dict_repr() -> (
    None
):
    basis = {
        "facet_type": "attribute",
        "name": None,
        "cardinality": "required",
        "comparisons": [],
        "name_comparisons": [
            {"operator": "enumeration", "value": "OverallWidth"},
            {"operator": "enumeration", "value": "OverallHeight"},
        ],
    }
    fallback = "The {'enumeration': ['OverallWidth', 'OverallHeight']} shall be provided"
    assert (
        requirement_text(basis, fallback)
        == "The OverallWidth or OverallHeight shall be provided."
    )


def test_a_single_member_restricted_name_reads_as_a_plain_subject() -> None:
    basis = {
        "facet_type": "attribute",
        "name": None,
        "cardinality": "required",
        "comparisons": [],
        "name_comparisons": [{"operator": "literal", "value": "OverallWidth"}],
    }
    assert requirement_text(basis, "fallback") == "The OverallWidth shall be provided."


def test_a_name_restricted_by_pattern_has_no_natural_subject_and_falls_back() -> None:
    """`pattern` restricts what characters a name may contain, not which attribute is
    meant -- there is no single word to put in the sentence's subject position, so this
    degrades to `description` exactly as an unrecognised *value* comparison operator does.
    """
    basis = {
        "facet_type": "attribute",
        "name": None,
        "cardinality": "required",
        "comparisons": [],
        "name_comparisons": [{"operator": "pattern", "value": "Overall.*"}],
    }
    assert (
        requirement_text(basis, "the real ifctester sentence")
        == "the real ifctester sentence"
    )


def test_a_restricted_name_with_a_value_bound_falls_back_not_a_false_disjunction() -> None:
    """T-0039 review, F1. A restricted name plus a value bound is what `ifctester`'s own
    `Attribute.__call__` evaluates *conjunctively* -- every matching attribute must satisfy
    the bound, not just one of them -- so rendering the multi-member name with the
    disjunctive joiner would print an "or" for what is actually an "and". Reviewer's live
    repro: a door with OverallHeight=2100 (satisfies "at least 900") and OverallWidth=800
    (does not) is reported FAIL, and before this fix the sentence read "The OverallWidth or
    OverallHeight shall be at least 900" -- a sentence that door satisfies, contradicting
    its own FAIL. The safe degrade is `description`, exactly as for a `pattern`-restricted
    name or an unrecognised value operator.
    """
    basis = {
        "facet_type": "attribute",
        "name": None,
        "cardinality": "required",
        "comparisons": [{"operator": "minInclusive", "value": "900"}],
        "name_comparisons": [
            {"operator": "enumeration", "value": "OverallWidth"},
            {"operator": "enumeration", "value": "OverallHeight"},
        ],
    }
    fallback = (
        "The {'enumeration': ['OverallWidth', 'OverallHeight']} "
        "shall be {'minInclusive': '900'}"
    )
    assert requirement_text(basis, fallback) == fallback


def test_a_single_member_restricted_name_with_a_bound_still_renders() -> None:
    """The case F1's fix must not break: a *single*-member restricted name has no joiner to
    get wrong regardless of whether a value bound is also present, so it keeps rendering as
    a normal sentence.
    """
    basis = {
        "facet_type": "attribute",
        "name": None,
        "cardinality": "required",
        "comparisons": [{"operator": "minInclusive", "value": "900"}],
        "name_comparisons": [{"operator": "literal", "value": "OverallWidth"}],
    }
    assert requirement_text(basis, "fallback") == "The OverallWidth shall be at least 900."


def test_a_document_stored_before_name_comparisons_existed_still_falls_back() -> None:
    """REPORT_SCHEMA_VERSION 3 and earlier has no `name_comparisons` key on `basis` at
    all -- `.get(...)` must degrade to "nothing to say" rather than raising `KeyError`.
    """
    basis: dict[str, Any] = {
        "facet_type": "attribute",
        "name": None,
        "cardinality": "required",
        "comparisons": [],
    }
    assert (
        requirement_text(basis, "the real ifctester sentence")
        == "the real ifctester sentence"
    )


# T-0040: `requirement_text` reads a document it did not necessarily write -- a report
# stored by a newer engine, a restored dump, a hand-edited row -- so it must return a
# string for *any* shape that document happens to have, never raise. Each test below
# reproduces one of the crashes the T-0027 review found live in this module (`KeyError`,
# `TypeError`, `AttributeError`) and asserts the safe degrade: `fallback`, exactly as an
# unrecognised operator or an unsupported facet type already degrade.


def test_a_comparison_missing_operator_falls_back_instead_of_raising_key_error() -> None:
    basis = {
        "facet_type": "attribute",
        "name": "OverallWidth",
        "cardinality": "required",
        "comparisons": [{"value": "900"}],
    }
    assert requirement_text(basis, "fallback") == "fallback"


def test_a_comparison_missing_value_falls_back_instead_of_raising_key_error() -> None:
    basis = {
        "facet_type": "attribute",
        "name": "OverallWidth",
        "cardinality": "required",
        "comparisons": [{"operator": "minInclusive"}],
    }
    assert requirement_text(basis, "fallback") == "fallback"


def test_comparisons_stored_as_a_dict_not_a_list_does_not_raise_type_error() -> None:
    """Before this fix, iterating a dict yields its keys as bare strings, and
    `comparison["operator"]` on one of those raised `TypeError: string indices must be
    integers`. There genuinely is a name and a cardinality here, so the safe reading of a
    malformed `"comparisons"` is the same one an absent or `None` `"comparisons"` already
    gets: no bound stated.
    """
    basis = {
        "facet_type": "attribute",
        "name": "OverallWidth",
        "cardinality": "required",
        "comparisons": {"operator": "minInclusive", "value": "900"},
    }
    assert requirement_text(basis, "fallback") == "The OverallWidth shall be provided."


def test_basis_stored_as_a_string_falls_back_instead_of_raising_attribute_error() -> None:
    """Before this fix, `not basis` is `False` for a non-empty string, so execution fell
    through to `basis.get(...)`, which a `str` does not have.
    """
    assert requirement_text("not a mapping", "fallback") == "fallback"  # type: ignore[arg-type]


def test_basis_stored_as_a_list_falls_back_instead_of_raising() -> None:
    assert requirement_text([{"facet_type": "attribute"}], "fallback") == "fallback"  # type: ignore[arg-type]


def test_basis_none_still_falls_back_as_before() -> None:
    """Not a new case -- `REPORT_SCHEMA_VERSION` 1 already stores no `basis` at all -- but
    asserted here beside its siblings so this file states the whole property in one place:
    `requirement_text` returns a string for `None`, a string, a list, and a dict of any
    shape alike.
    """
    assert requirement_text(None, "fallback") == "fallback"


def test_a_basis_whose_comparisons_is_none_still_falls_back_to_no_bound_stated() -> None:
    basis: dict[str, Any] = {
        "facet_type": "attribute",
        "name": "OverallWidth",
        "cardinality": "required",
        "comparisons": None,
    }
    assert requirement_text(basis, "fallback") == "The OverallWidth shall be provided."


def test_name_comparisons_stored_as_a_dict_not_a_list_does_not_raise() -> None:
    basis: dict[str, Any] = {
        "facet_type": "attribute",
        "name": None,
        "cardinality": "required",
        "comparisons": [],
        "name_comparisons": {"operator": "literal", "value": "OverallWidth"},
    }
    assert requirement_text(basis, "the real ifctester sentence") == (
        "the real ifctester sentence"
    )
