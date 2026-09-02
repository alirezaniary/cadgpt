"""requirement_text: the sentence built from a requirement's structured `basis`.

Translated wording is proven against the real running API in two languages
(`docs/tasks/T-0027-requirement-as-structured-citation.md`'s evidence) rather than here --
this process's `.po` catalogue is not compiled to `.mo` outside the container build
(`deploy/docker/api.Dockerfile`), so `gettext` here returns the English source string
verbatim, same as `reasons.py`'s own tests already rely on for `REASON_LABELS`. What this
file proves is the branching: a bound renders a comparison, no bound states only that the
attribute must be provided, cardinality picks "shall" / "shall not" / "may", an
`enumeration` joins as a disjunction ("or") while every other multi-part bound joins as a
conjunction ("and"), and anything this table does not recognise -- an unsupported facet
type, no `basis` at all, or a comparison operator not in `_COMPARISON_TEMPLATES` -- falls
back to `description` rather than to a blank line or, worse, a confident sentence for the
wrong rule.
"""

from __future__ import annotations

from cadgpt.apps.review.requirements import requirement_text


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
