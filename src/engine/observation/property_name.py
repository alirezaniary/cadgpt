"""A property name that carries its measurement convention, or does not exist.

``docs/ddd/06-property-vocabulary.md`` is the closed vocabulary this module encodes: 27
``prd.md`` §5.3 names, each either a base quantity plus a measurement-convention segment
(``NetFloorArea_InsideFace``) or a convention-free base on its own (``StallCount``).
``CLAUDE.md`` §2 states the rule this module exists to enforce: "every quantity names its
measurement convention, in its name." ``PropertyName.parse`` is the single place that rule
is checked, at construction, so a name that denotes a measurement and carries no convention
cannot be built at all.
"""

from __future__ import annotations

from dataclasses import dataclass

CONVENTIONS: frozenset[str] = frozenset(
    {
        "FootprintGross",
        "North",
        "South",
        "East",
        "West",
        "Narrowest",
        "BetweenHandrails",
        "Minimum",
        "InsideFace",
        "Centreline",
        "Structural",
        "Net",
        "AtWalkingLine",
    }
)
"""The closed set of measurement-convention segments, from
docs/ddd/06-property-vocabulary.md (13 members, after DEC-0031 adds ``AtWalkingLine`` for
``TreadLength_AtWalkingLine`` and reuses ``Narrowest`` for ``ExitWidth_Narrowest``)."""

CONVENTION_FREE_BASES: frozenset[str] = frozenset(
    {
        "FloorAreaRatio",
        "RiserHeight",
        "NumberOfRiser",
        "MinPlanDimension",
        "ServedHeight",
        "ProportionRatio",
        "StallLength",
        "StallWidth",
        "ManeuveringClearance",
        "StallCount",
        "TravelDistance",
        "DeadEndLength",
    }
)
"""Base quantities that legitimately carry no convention — counts, ratios, and the
single-reading dimensions docs/ddd/06-property-vocabulary.md justifies individually
(12 members). ``TreadLength`` and ``ExitWidth`` are deliberately absent: DEC-0031 resolved
both to carry a convention segment, so their bare bases no longer belong here."""


class ConventionMissing(ValueError):
    """A name with no underscore whose base denotes a measurement, not a convention-free
    quantity, so a measurement convention must be stated as a suffix."""


class UnknownConvention(ValueError):
    """A name's convention segment is not a member of ``CONVENTIONS``."""


@dataclass(frozen=True)
class PropertyName:
    """A §5.3 property name, split into its base quantity and its measurement convention.

    Not ``Observation``. Not a quantity, a value, or a unit — it is the name and nothing
    else. Carries no bare number and offers no constructor that would take one.
    """

    base: str
    convention: str | None

    @classmethod
    def parse(cls, raw: str) -> PropertyName:
        """Split ``raw`` on its first underscore into a base and a convention.

        Raises ``ConventionMissing`` when ``raw`` has no underscore and its base is not in
        ``CONVENTION_FREE_BASES``. Raises ``UnknownConvention`` when a convention segment is
        present but not in ``CONVENTIONS``.
        """
        base, separator, convention = raw.partition("_")
        if not separator:
            if base in CONVENTION_FREE_BASES:
                return cls(base=base, convention=None)
            raise ConventionMissing(
                f"{base!r} denotes a measurement and must state its measurement "
                f"convention as a suffix (e.g. {base}_<Convention>); it is not in "
                "CONVENTION_FREE_BASES. A convention-free base is added by amending "
                "docs/ddd/06-property-vocabulary.md and CONVENTION_FREE_BASES together."
            )
        if convention not in CONVENTIONS:
            raise UnknownConvention(
                f"{convention!r} is not a known measurement convention. Known: "
                f"{sorted(CONVENTIONS)}. A convention is added by amending "
                "docs/ddd/06-property-vocabulary.md and CONVENTIONS together."
            )
        return cls(base=base, convention=convention)

    def __str__(self) -> str:
        if self.convention is None:
            return self.base
        return f"{self.base}_{self.convention}"
