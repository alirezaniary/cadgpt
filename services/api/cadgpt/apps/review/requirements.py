"""Translate the engine's structured requirement citation.

The engine names a requirement facet's own comparison -- operator, value, cardinality,
subject -- as data (`cadgpt_engine.RequirementBasis`, stored on the report as
`requirement["basis"]`); this module supplies the sentence, in the reader's language, the
same way `reasons.label_for` supplies wording for a `ReasonCode`. Mirrors that module's
design on purpose: the stored document holds no prose for this line, only the pieces to
build one, so the same run reads in Persian and in English from one document and a
translation fix does not require rewriting history.

Only the `"attribute"` facet type is rendered into a sentence here -- the one the shipped
fixtures exercise, and the one whose sentence shape ("The X shall be Y") a `Property`,
`Entity`, `Classification`, `PartOf` or `Material` facet does not share. Every other facet
type, a report stored before `basis` existed at all, and a comparison whose operator this
table does not recognise, falls back to `description`: `ifctester`'s own English sentence,
which is what the engine's CLI and tests already print. This is *not* the same degrade
`reasons.label_for` makes for an unknown `ReasonCode` -- that one degrades to the bare
identifier, visibly unresolved. An unrecognised comparison operator degrading to a
plausible-looking sentence instead (e.g. treating `totalDigits`'s `4` as if it were the
required value) would state the wrong rule with the same confidence as a right one, which
is worse than saying nothing: falling back to `description` is the only safe degrade here.
"""

from __future__ import annotations

from typing import Any

from django.utils.translation import gettext_lazy as _

#: Sentence fragment for each XSD restriction facet name this module knows how to render.
#: `"literal"` is a bare value with no `Restriction` at all. A comparison whose operator is
#: not a key here (`totalDigits`, `fractionDigits`, `whiteSpace`, `assertion` -- all valid
#: IDS restrictions ifctester supports today, see `ifctester.facet.Restriction.asdict`) is
#: not rendered at all: see `_recognised` and the module docstring.
_COMPARISON_TEMPLATES: dict[str, Any] = {
    "minInclusive": _("at least %(value)s"),
    "maxInclusive": _("at most %(value)s"),
    "minExclusive": _("more than %(value)s"),
    "maxExclusive": _("less than %(value)s"),
    "enumeration": _("%(value)s"),
    "literal": _("%(value)s"),
    "pattern": _("matching %(value)s"),
    "length": _("exactly %(value)s characters"),
    "minLength": _("at least %(value)s characters"),
    "maxLength": _("at most %(value)s characters"),
}

#: The requirement sentence, by the effective cardinality `check.py`'s `_requirement_basis`
#: already resolved (substituting `"prohibited"` for a prohibited specification regardless
#: of the facet's own `cardinality` attribute -- see `RequirementBasis`), and by whether the
#: facet states a bound at all.
_REQUIRED_WITH_BOUND = _("The %(name)s shall be %(bound)s.")
_REQUIRED_NO_BOUND = _("The %(name)s shall be provided.")
_PROHIBITED_WITH_BOUND = _("The %(name)s shall not be %(bound)s.")
_PROHIBITED_NO_BOUND = _("The %(name)s shall not be provided.")
_OPTIONAL_WITH_BOUND = _("The %(name)s may be %(bound)s.")
_OPTIONAL_NO_BOUND = _("The %(name)s may be provided.")

#: Joins more than one *conjunctive* comparison on the same facet -- a range with both a
#: minimum and a maximum, both of which must hold at once.
_JOINER = _(" and ")

#: Joins the members of an `xs:enumeration` restriction. IDS `enumeration` is a
#: *disjunction* -- the value must be *one of* the listed members, never all of them at
#: once -- so it cannot share `_JOINER` with a range. Which joiner applies is decided by the
#: operator (`enumeration` vs. everything else `_COMPARISON_TEMPLATES` knows), never by how
#: many comparisons there are: a range with one bound and an enumeration with one member
#: must not be told apart by counting, and an enumeration with several members must not be
#: told apart from a range by counting either.
_ENUMERATION_JOINER = _(" or ")


def _recognised(comparisons: list[dict[str, Any]]) -> bool:
    """Whether every comparison's operator is one `_COMPARISON_TEMPLATES` can render.

    A single comparison this table does not recognise makes the whole bound unrenderable:
    partially stating a multi-part restriction (e.g. a range's minimum but not its
    `totalDigits` digit limit) would be as misleading as stating the wrong one.
    """
    return all(
        comparison["operator"] in _COMPARISON_TEMPLATES for comparison in comparisons
    )


def _bound(comparisons: list[dict[str, Any]]) -> str | None:
    """The bound as a sentence fragment, or `None` when there is no comparison to state.

    Callers check `_recognised(comparisons)` first -- every operator here is assumed to be a
    key in `_COMPARISON_TEMPLATES`. `enumeration` members are grouped and joined with
    `_ENUMERATION_JOINER` (a disjunction); every other comparison joins the rest with
    `_JOINER` (a conjunction) -- see the two joiners' own docstrings for why that split is
    keyed on the operator rather than on the count of comparisons.
    """
    if not comparisons:
        return None

    enumeration_values = [c["value"] for c in comparisons if c["operator"] == "enumeration"]
    other = [c for c in comparisons if c["operator"] != "enumeration"]

    phrases = []
    if enumeration_values:
        phrases.append(
            str(_ENUMERATION_JOINER).join(
                str(_COMPARISON_TEMPLATES["enumeration"]) % {"value": value}
                for value in enumeration_values
            )
        )
    phrases.extend(
        str(_COMPARISON_TEMPLATES[c["operator"]]) % {"value": c["value"]} for c in other
    )
    return str(_JOINER).join(phrases)


def requirement_text(basis: dict[str, Any] | None, fallback: str) -> str:
    """The requirement's citation, in the reader's language, or `fallback` when it can't be.

    `fallback` is `RequirementOutcome.description` -- `ifctester`'s own sentence. `basis` is
    `None` for a report stored before `REPORT_SCHEMA_VERSION` 2 (the field did not exist
    yet); this table only renders the `"attribute"` facet type; and a comparison whose
    operator `_recognised` does not know is refused rather than guessed at (see the module
    docstring). All three degrade the same way: to the sentence the engine already wrote,
    never to a confident sentence for the wrong rule.
    """
    if not basis or basis.get("facet_type") != "attribute" or not basis.get("name"):
        return fallback

    comparisons = basis.get("comparisons") or []
    if not _recognised(comparisons):
        return fallback

    name = basis["name"]
    bound = _bound(comparisons)
    cardinality = basis.get("cardinality")

    if cardinality == "prohibited":
        template = _PROHIBITED_WITH_BOUND if bound else _PROHIBITED_NO_BOUND
    elif cardinality == "optional":
        template = _OPTIONAL_WITH_BOUND if bound else _OPTIONAL_NO_BOUND
    else:
        template = _REQUIRED_WITH_BOUND if bound else _REQUIRED_NO_BOUND

    if bound:
        return str(template) % {"name": name, "bound": bound}
    return str(template) % {"name": name}
