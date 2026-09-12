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

`requirement_text` is total, the same property `reasons.label_for` has over `ReasonCode`:
it returns a string for *any* `basis`, not only a well-formed one. `basis` is read from a
stored document `requirement_text` did not write -- a report from a newer engine, a
restored dump, a hand-edited row -- so every read below probes a shape rather than
subscripting one: `basis` itself may be `None`, a bare string, a list, or anything else
that is not a mapping; `"comparisons"` or `"name_comparisons"` may be missing, `None`, or
some other shape than a list; and any one comparison in either may be missing `"operator"`
or `"value"`, or not be a mapping at all. None of that raises -- each unreadable shape
degrades to the same `fallback` an unrecognised operator already falls back to (T-0040).
`tests/test_requirements.py` exercises every one of these shapes directly.
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


def _as_list(value: Any) -> list[Any]:
    """`value` if it actually is a list, else `[]`.

    `"comparisons"` and `"name_comparisons"` are each supposed to be a list, but this reads
    a document `requirement_text` did not necessarily write, so the field might be
    anything: absent (already `None` before either field existed, handled the same way),
    a scalar, a dict standing in for what should have been a list of them. Treating
    anything other than an actual list as "nothing stated" -- the same degrade `None`
    already received -- keeps every read below this point an iteration over a list, never
    a subscript into whatever shape actually showed up.
    """
    return value if isinstance(value, list) else []


def _recognised(comparisons: list[Any]) -> bool:
    """Whether every entry in `comparisons` is a mapping stating both an `"operator"` this
    table can render and a `"value"` to render it with.

    A single comparison this table cannot fully read -- an unrecognised operator, a
    missing `"value"`, or an entry that is not even a mapping (a document this table did
    not write may hold anything there) -- makes the whole bound unrenderable: partially
    stating a multi-part restriction (e.g. a range's minimum but not its `totalDigits`
    digit limit) would be as misleading as stating the wrong one.
    """
    return all(
        isinstance(comparison, dict)
        and comparison.get("operator") in _COMPARISON_TEMPLATES
        and "value" in comparison
        for comparison in comparisons
    )


def _subject_name(comparisons: list[Any], value_comparisons: list[Any]) -> str | None:
    """The attribute or property *name* itself, when the IDS restricted which name applies
    rather than stating one literally (`basis.name_comparisons`, T-0039) -- `None` when
    there is nothing to state.

    Only `enumeration` and `literal` name a *name*: a closed set of acceptable attribute
    names, or (degenerately) exactly one. Every other restriction (`pattern`, `minLength`,
    a numeric bound, ...) constrains what characters or shape a name may take, not which
    attribute is meant, and has no natural rendering as a sentence's subject -- callers
    fall back to `description` for that case, the same safe degrade
    `_recognised`/`_bound` already make for an unrecognised *value* comparison. Multiple
    members join with `_ENUMERATION_JOINER`: `xs:enumeration` is a disjunction here exactly
    as it is for a value (T-0039's own fixture: "one of these attributes must be
    provided", not all of them at once) -- *provided* the facet states no value bound of
    its own.

    T-0039 review (F1): the moment the same facet *also* carries a value bound
    (`value_comparisons` non-empty), that disjunction stops being true. `ifctester`'s own
    `Attribute.__call__` evaluates every attribute matching a restricted name
    conjunctively against that bound -- "the OverallWidth *and* the OverallHeight must each
    satisfy it", not "one of them must" -- so joining several names with `_ENUMERATION_
    JOINER` in that case would print an "or" over what is actually an "and", a sentence a
    FAILing entity can satisfy while the citation beside it reads FAIL (I5). A multi-member
    restricted name is therefore rendered only when `value_comparisons` is empty (a pure
    existence check, where "or" is genuinely correct); with a value bound present, this
    returns `None` and the caller falls back to `description` rather than asserting a
    joiner that could describe the wrong rule. A single-member name has no joiner to get
    wrong either way, so it keeps rendering regardless of `value_comparisons`.
    """
    if not comparisons:
        return None
    if any(
        not isinstance(c, dict)
        or c.get("operator") not in ("literal", "enumeration")
        or "value" not in c
        for c in comparisons
    ):
        return None
    if len(comparisons) > 1 and value_comparisons:
        return None
    return str(_ENUMERATION_JOINER).join(c["value"] for c in comparisons)


def _bound(comparisons: list[Any]) -> str | None:
    """The bound as a sentence fragment, or `None` when there is no comparison to state.

    Callers check `_recognised(comparisons)` first -- every entry here is assumed to be a
    mapping whose operator is a key in `_COMPARISON_TEMPLATES` and which carries a
    `"value"`. `enumeration` members are grouped and joined with
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

    The type annotation states the shape `basis` is *supposed* to have; it is read here as
    though it might not, because the document underneath it may not be one this table wrote
    (T-0040): `basis` itself may be a bare string or a list rather than a mapping, and
    `"comparisons"` / `"name_comparisons"` may be missing, `None`, or some other shape than
    a list, down to an individual comparison missing `"operator"` or `"value"`. Every one of
    those degrades to `fallback` the same way an unsupported facet type or an unrecognised
    operator already does -- never a `KeyError`, `TypeError`, or `AttributeError` reaching
    the caller. `isinstance(basis, dict)` below is that guard, not a redundant check against
    the annotation: the annotation is the contract, the `isinstance` is what holds when a
    caller's document violates it.

    `basis["name"]` is `None` both for a facet type this table names nothing for *and*
    (T-0039) for an attribute whose own name is itself a restriction rather than a literal
    string (`<xs:restriction>` under `<ids:name>`) -- `_subject_name` on
    `basis["name_comparisons"]` is what tells those two apart: still nothing to say for the
    first, "OverallWidth or OverallHeight" for the second. A document stored before
    `name_comparisons` existed has no such key, and `_as_list(...)` degrades it to the
    same "nothing to say" as a facet type with no name at all.

    `comparisons` (the facet's *value* bound) is read before `name` and passed into
    `_subject_name` (T-0039 review, F1): a multi-member restricted name renders as a
    disjunction only when there is no value bound to satisfy alongside it, since
    `ifctester` evaluates a restricted name conjunctively the moment a bound is also
    present -- see `_subject_name`'s own docstring. The single-member case is unaffected.
    """
    if not isinstance(basis, dict) or basis.get("facet_type") != "attribute":
        return fallback

    comparisons = _as_list(basis.get("comparisons"))
    name = basis.get("name") or _subject_name(
        _as_list(basis.get("name_comparisons")), comparisons
    )
    if not name:
        return fallback

    if not _recognised(comparisons):
        return fallback

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
