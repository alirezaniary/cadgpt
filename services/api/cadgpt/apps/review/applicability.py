"""Translate the engine's structured applicability facets.

The engine names each applicability facet a specification carries as data
(`cadgpt_engine.ApplicabilityFacet`, stored on the report as
`specifications[].applicability_facets`); this module supplies the sentence, in the
reader's language, the same way `reasons.label_for` supplies wording for a `ReasonCode` and
`requirements.requirement_text` supplies wording for a requirement's own basis. Mirrors
both modules' design on purpose: the stored document holds no prose for this line either,
only the pieces to build one, so the same run reads in Persian and in English from one
document.

Only the `"entity"` facet type is rendered into a sentence here -- the one applicability
facet the shipped fixtures exercise, matching `requirements.py`'s own scope decision for
the requirement side. Every other facet type, an `Entity` whose own `name` is itself a
restriction rather than a literal IFC class, and a report stored before
`applicability_facets` existed at all, falls back to `description` -- each facet's own
`to_string("applicability")` rendering, upstream's English sentence, joined by this
module's own `_JOINER` rather than the engine's hardcoded `" and "` (T-0039's second
finding: a two-facet applicability read English-joined even when every facet inside it
happened to translate).
"""

from __future__ import annotations

from typing import Any

from django.utils.translation import gettext_lazy as _

#: The `Entity` facet's own sentence, by whether the IDS also restricts `predefinedType`.
#: Mirrors `ifctester.facet.Entity.applicability_templates` ("All {name} data[ of type
#: {predefinedType}]") -- the inherited wording, re-authored through gettext rather than
#: read back out of `to_string`'s output, which would be parsing a string this same code
#: could have built structured in the first place.
_ENTITY_WITH_TYPE = _("All %(name)s data of type %(predefined_type)s")
_ENTITY_NO_TYPE = _("All %(name)s data")

#: Joins more than one applicability facet. `ifctester` ANDs applicability facets together
#: -- an element is in scope only if it satisfies *every* facet -- so, unlike
#: `requirements.py`'s bound (which needs both a conjunctive and a disjunctive joiner),
#: there is only ever the one here.
_JOINER = _(" and ")


def _facet_text(facet: dict[str, Any]) -> str:
    """One applicability facet, in the reader's language, or its own `description` when
    this table does not render its type or shape.

    `facet.get("name")` is `None` both for a facet type that carries no such attribute and
    for an `Entity` whose `name` is itself a restriction rather than a literal IFC class
    (`cadgpt_engine.check._applicability_facet` already collapses both to `None`) -- either
    way, there is nothing this table can put in the template, and `description` is the
    only safe degrade, the same one `requirements.requirement_text` makes for a comparison
    operator it does not recognise.
    """
    if facet.get("facet_type") != "entity" or not facet.get("name"):
        return str(facet.get("description") or "")

    if facet.get("predefined_type"):
        return str(_ENTITY_WITH_TYPE) % {
            "name": facet["name"],
            "predefined_type": facet["predefined_type"],
        }
    return str(_ENTITY_NO_TYPE) % {"name": facet["name"]}


def applicability_text(facets: list[dict[str, Any]] | None, fallback: str) -> str:
    """The specification's applicability, in the reader's language, or `fallback` when it
    cannot be built.

    `fallback` is `SpecificationOutcome.applicability_description` -- `ifctester`'s own
    sentence, its facets already joined by the engine's hardcoded `" and "`. `facets` is
    `None` for a report stored before `REPORT_SCHEMA_VERSION` 4, the only case this
    degrades to `fallback` rather than rendering: an empty (but present) list joins to `""`
    through `_JOINER` exactly as `fallback` itself would for a specification whose own
    applicability is empty, so the two only ever diverge when there is something to
    render differently.
    """
    if facets is None:
        return fallback
    return str(_JOINER).join(_facet_text(facet) for facet in facets)
