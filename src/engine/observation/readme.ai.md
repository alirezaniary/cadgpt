# readme.ai.md — src/engine/observation/

## Purpose
The shared kernel (`docs/architecture/module-map.md`): the atom every derivation produces
and every evaluation consumes. Today this module holds exactly one thing —
`PropertyName`, which parses a `prd.md` §5.3 property name into a base quantity and a
measurement convention, and **refuses to construct** a name that denotes a measurement and
carries no convention. This is `CLAUDE.md` §2's rule — "every quantity names its
measurement convention, in its name" — enforced as a constructor precondition, not a
validator run over data that already exists.

It is **not** `Observation` (the quantity plus its numeric value and its unit — a later
slice), not a quantity, not a value, and not a unit. It is the *name* and nothing else. It
carries no convenience constructor that accepts a bare number: `docs/roadmap/L3-C11-slices.md`
names that shortcut as the beginning of the end of I4, and this module offers no way to take
it.

## Context
Bounded context: the shared kernel that sits beneath `derivation` and `evaluation`
(`docs/ddd/03-bounded-contexts.md`). Subdomain: **core** — this is where the vocabulary
`docs/ddd/06-property-vocabulary.md` audited becomes an enforced type.

## Contract
- `CONVENTIONS: frozenset[str]` — the closed set of measurement-convention segments, from
  `docs/ddd/06-property-vocabulary.md`. 13 members: `FootprintGross`, `North`, `South`,
  `East`, `West`, `Narrowest`, `BetweenHandrails`, `Minimum`, `InsideFace`, `Centreline`,
  `Structural`, `Net`, `AtWalkingLine`.
- `CONVENTION_FREE_BASES: frozenset[str]` — base quantities that legitimately carry no
  convention: counts, ratios, and the single-reading dimensions
  `docs/ddd/06-property-vocabulary.md` justifies individually. 12 members:
  `FloorAreaRatio`, `RiserHeight`, `NumberOfRiser`, `MinPlanDimension`, `ServedHeight`,
  `ProportionRatio`, `StallLength`, `StallWidth`, `ManeuveringClearance`, `StallCount`,
  `TravelDistance`, `DeadEndLength`.
- `PropertyName(base: str, convention: str | None)` — frozen dataclass.
  - `PropertyName.parse(raw: str) -> PropertyName` — splits `raw` on its **first**
    underscore. Raises `ConventionMissing` when there is no underscore and `base` is not in
    `CONVENTION_FREE_BASES`. Raises `UnknownConvention` when a convention segment is present
    but not in `CONVENTIONS`.
  - `__str__() -> str` — `str(PropertyName.parse(n)) == n` for every one of the 27 names in
    `docs/ddd/06-property-vocabulary.md`.
- `ConventionMissing(ValueError)` — a bare name denoting a measurement with no stated
  convention.
- `UnknownConvention(ValueError)` — a convention segment outside the closed set.

Everything above is exported from `engine.observation` (`__init__.py`'s `__all__`);
nothing else in this module is part of its public surface.

## Invariants enforced here
- **"Every quantity names its measurement convention, in its name"** (`CLAUDE.md` §2).
  Enforced in `PropertyName.parse` (`property_name.py`): a name whose base is not in
  `CONVENTION_FREE_BASES` cannot be constructed without a convention segment, and the
  segment itself must be a member of `CONVENTIONS`. This is a *construction* precondition —
  there is no path to a `PropertyName` instance that skips it — not a validator run
  afterwards over data that already exists.
- **Immutability.** `PropertyName` is `@dataclass(frozen=True)`. No setter, no
  `with_convention`; a different name is a different `PropertyName`.

## Depends on
The standard library only: `dataclasses` (the frozen value object). No third-party import.

## Must not depend on
- **`engine.derivation`, `engine.packs`, `engine.resolution`, `engine.evaluation`,
  `engine.findings`.** `observation` sits at the bottom of the engine's layering
  (`docs/architecture/module-map.md`): `derivation` produces the atom this module types,
  `evaluation` consumes it, and neither owns it — a dependency in either direction would
  make the two stop being independently testable.
- **Any inference client or model SDK** (I1) — as for every module under `src/engine`.
- **A convenience constructor that accepts a bare number.** `docs/roadmap/L3-C11-slices.md`
  names this as the beginning of the end of I4; this module offers no such path on purpose.

## Tests
`src/engine/observation/tests/test_property_name.py`, beside the module
(`docs/architecture/module-map.md`). 5 unit / 4 integration (44% integration, in band —
gate 15).

- Unit, over literal names, no filesystem: each rejection path has its own test
  (`ConventionMissing` for a bare measurement, `UnknownConvention` for an unrecognised
  segment), `convention=None` for a convention-free base, and the round-trip
  (`str(parse(n)) == n`) for one convention-bearing and one convention-free name.
- Integration, entering at the real `docs/ddd/06-property-vocabulary.md` on disk and
  exiting at real `PropertyName` construction: the document's own table is parsed (not
  retyped) into the 27 names it lists, with the two DEC-0031 supersessions
  (`TreadLength`→`TreadLength_AtWalkingLine`, `ExitWidth`→`ExitWidth_Narrowest`) applied from
  the same document's own prose — every one of the 27 parses, every one round-trips, and
  the conventions/free-bases the 27 names actually use are exactly `CONVENTIONS` and
  `CONVENTION_FREE_BASES`, member for member.

**Mocking: none.** The integration tests read the real vocabulary document from disk; no
part of `engine.observation` or the filesystem is faked.

## How to run it
```
$ uv run --group dev python -c "
from engine.observation.property_name import PropertyName
print(PropertyName.parse('NetFloorArea_InsideFace'))
print(PropertyName.parse('StallCount'))
try: PropertyName.parse('Area')
except Exception as e: print(type(e).__name__, e)"
NetFloorArea_InsideFace
StallCount
ConventionMissing 'Area' denotes a measurement and must state its measurement convention as a suffix (e.g. Area_<Convention>); it is not in CONVENTION_FREE_BASES. A convention-free base is added by amending docs/ddd/06-property-vocabulary.md and CONVENTION_FREE_BASES together.
```

## Open questions
None.
