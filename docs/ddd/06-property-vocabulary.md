# Property vocabulary audit

S1.1.1. Before any name in `prd.md` §5.3 is written as code, this document resolves each one
against IFC's own offline property and quantity templates (`ifcopenshell.util.pset.PsetQto`,
schema `IFC4`) and records, for every row, either the exact IFC template it inherits or a
one-sentence statement of what nothing existing covers. DEC-0019 and I3 apply: ours is the
residue, not the whole vocabulary.

## Method

```
uv run --group engine python -c "
from ifcopenshell.util.pset import PsetQto
q = PsetQto('IFC4')
f = q.templates[0]
psets = f.by_type('IfcPropertySetTemplate')
index = {}
for p in psets:
    for prop in p.HasPropertyTemplates:
        index.setdefault(prop.Name, []).append(p.Name)
print(index.get('<candidate base name>'))
"
```

`PsetQto('IFC4').templates` is a one-element list holding the loaded `Pset_IFC4_ADD2.ifc`
template file; `by_type('IfcPropertySetTemplate')` returns all 513 IFC4 pset/qto templates
(`Pset_*` and `Qto_*`), each carrying its `HasPropertyTemplates`. Every base-name candidate below
— the part of a §5.3 name before its first underscore, or the whole name if it has none — was
looked up in the resulting `{property name → [pset names]}` index for an **exact** string match.
A row is marked inherited only where that exact match exists; everything else is authored, named
here as authored, with the query result quoted.

## The table

One row per §5.3 name, 27 rows.

| Name | Pset | Base quantity | Inherited from | Convention | Why authored |
| --- | --- | --- | --- | --- | --- |
| `CoveredArea_FootprintGross` | Pset_ACC_Site | — | authored | `FootprintGross` | No IFC template names a building's footprint area on its site. `Qto_SiteBaseQuantities` has `GrossArea`, but its definition is the site parcel's own area, not a building's footprint on it — a different measured thing, not a respelling candidate. |
| `FloorAreaRatio` | Pset_ACC_Site | `FloorAreaRatio` | `Pset_SiteCommon` | — | |
| `Setback_North` | Pset_ACC_Site | — | authored | `North` | No IFC property or quantity template represents a building-to-boundary setback. The only near-namesake, `SetbackDistance` (`Pset_AnnotationLineOfSight`), is a 2D drafting annotation property, not a site or building quantity. |
| `Setback_South` | Pset_ACC_Site | — | authored | `South` | Same search, same result as `Setback_North`. |
| `Setback_East` | Pset_ACC_Site | — | authored | `East` | Same search, same result as `Setback_North`. |
| `Setback_West` | Pset_ACC_Site | — | authored | `West` | Same search, same result as `Setback_North`. |
| `ClearWidth_Narrowest` | Pset_ACC_Stair | `ClearWidth` | `Pset_RampFlightCommon` (also: `Pset_TransportElementElevator`, `Pset_DistributionChamberElementTypeFormedDuct`) | `Narrowest` | |
| `ClearWidth_BetweenHandrails` | Pset_ACC_Stair | `ClearWidth` | `Pset_RampFlightCommon` (also: `Pset_TransportElementElevator`, `Pset_DistributionChamberElementTypeFormedDuct`) | `BetweenHandrails` | |
| `Headroom_Minimum` | Pset_ACC_Stair | `Headroom` | `Pset_StairFlightCommon` (also: `Pset_RampFlightCommon`) | `Minimum` | |
| `RiserHeight` | Pset_ACC_Stair | `RiserHeight` | `Pset_StairCommon` (also: `Pset_StairFlightCommon`) | — | |
| `TreadLength` | Pset_ACC_Stair | `TreadLength` | `Pset_StairCommon` (also: `Pset_StairFlightCommon`) | — | |
| `NumberOfRiser` | Pset_ACC_Stair | `NumberOfRiser` | `Pset_StairCommon` (also: `Pset_StairFlightCommon`) | — | No IFC template uses the compound `RiserCount`. The nearest concept, `NumberOfRiser` (`Pset_StairCommon` / `Pset_StairFlightCommon`), is spelled differently — see proposed respellings below. |
| `NetFloorArea_InsideFace` | Pset_ACC_Space | `NetFloorArea` | `Qto_SpaceBaseQuantities` (also: `Qto_BuildingBaseQuantities`, `Qto_BuildingStoreyBaseQuantities`) | `InsideFace` | |
| `NetFloorArea_Centreline` | Pset_ACC_Space | `NetFloorArea` | `Qto_SpaceBaseQuantities` (also: `Qto_BuildingBaseQuantities`, `Qto_BuildingStoreyBaseQuantities`) | `Centreline` | |
| `ClearHeight_Structural` | Pset_ACC_Space | `ClearHeight` | `Pset_TransportElementElevator` — the only IFC template using this exact name, and for an elevator car interior, not a space under structure; flagged, not a semantic match, only a spelling one | `Structural` | |
| `ClearWidth_Narrowest` (Space) | Pset_ACC_Space | `ClearWidth` | `Pset_RampFlightCommon` | `Narrowest` | No IFC template prefixes `ClearWidth` with `Min`; IFC's own `ClearWidth` carries no min/max qualifier, and this document's own Stair row above already spells the identical measurement `ClearWidth_Narrowest` without the prefix — see proposed respellings below. |
| `PlanArea_Net` | Pset_ACC_Shaft | — | authored | `Net` | No IFC quantity template names a vertical void's horizontal cross-sectional area. `Qto_SpaceBaseQuantities.NetFloorArea` presumes an occupiable floor, not a shaft void, so it is not treated as the same quantity. |
| `MinPlanDimension` | Pset_ACC_Shaft | — | authored | — | No IFC quantity template represents the minimum in-plan dimension of a void; IFC's `Width`/`Depth` quantities are single axis-aligned dimensions, not a minimum-across-any-direction measure. |
| `ServedHeight` | Pset_ACC_Shaft | — | authored | — | No IFC quantity template names the vertical extent of storeys a shaft serves; IFC's various `Height` quantities measure a single element's own height, not a shaft's span across storeys. |
| `ProportionRatio` | Pset_ACC_Shaft | — | authored | — | No IFC quantity template expresses a plan-dimension proportion ratio for any element. |
| `StallLength` | Pset_ACC_Parking | — | authored | — | No IFC property or quantity template names a parking stall's length. The one parking-specific template, `Pset_SpaceParking`, carries only `ParkingUse`, `ParkingUnits`, `IsAisle` and `IsOneWay` — no dimensions. |
| `StallWidth` | Pset_ACC_Parking | — | authored | — | Same search, same result as `StallLength`. |
| `ManeuveringClearance` | Pset_ACC_Parking | — | authored | — | No IFC template represents vehicle maneuvering clearance; nothing in `Pset_SpaceParking` or any `Qto_*` template addresses circulation clearance around a stall. |
| `StallCount` | Pset_ACC_Parking | — | authored | — | No IFC property or quantity template counts parking stalls; `Pset_SpaceParking` has no count property. |
| `TravelDistance` | Pset_ACC_Route | — | authored | — | IFC has no notion of an egress travel path; no property or quantity template measures distance along a route to an exit. |
| `ExitWidth` | Pset_ACC_Route | — | authored | — | No IFC template names an egress route's clear width at an exit. IFC's per-element `Width` quantities (e.g. `Qto_DoorBaseQuantities.Width`) measure the element, not the route — see the flag under convention-free names below. |
| `DeadEndLength` | Pset_ACC_Route | — | authored | — | No IFC template measures the length of a dead-end segment of a circulation path; IFC has no route/path concept at all. |

## The counts

- **9 of 27 names inherit a base quantity** from an existing IFC property or quantity template,
  under IFC's exact spelling: `FloorAreaRatio`, `ClearWidth_Narrowest`,
  `ClearWidth_BetweenHandrails`, `Headroom_Minimum`, `RiserHeight`, `TreadLength`,
  `NetFloorArea_InsideFace`, `NetFloorArea_Centreline`, `ClearHeight_Structural`.
- **18 of 27 names are authored whole** — no IFC template, under any spelling, names the
  quantity: `CoveredArea_FootprintGross`, `Setback_North/South/East/West` (4), `RiserCount`,
  `MinClearWidth_Narrowest`, `PlanArea_Net`, `MinPlanDimension`, `ServedHeight`,
  `ProportionRatio`, `StallLength`, `StallWidth`, `ManeuveringClearance`, `StallCount`,
  `TravelDistance`, `ExitWidth`, `DeadEndLength`.
- **13 convention segments are authored** — every convention suffix in the table, because IFC
  ships base quantity kinds as bare names and has no concept of a convention segment at all (see
  Method in `prd.md` §5.3 and the task's Method note). This is true whether the base quantity
  next to it is inherited or authored: `FootprintGross`, `North`, `South`, `East`, `West`,
  `Narrowest` (stair), `BetweenHandrails`, `Minimum`, `InsideFace`, `Centreline`, `Structural`,
  `Narrowest` (space), `Net`.

9 + 18 = 27; the residue (18 authored whole, plus all 13 convention segments) is exactly what
DEC-0019 predicted: convention-suffixed names a general vocabulary does not carry, plus a small
set of domain quantities — setbacks, stall geometry, egress path metrics — no general-purpose
BIM schema has reason to model.

## Proposed respellings

Not applied here — `prd.md` is the product source of truth and is not edited by this task. Both
are decision requests if adopted.

1. **`RiserCount` → `NumberOfRiser`.** IFC's own stair templates (`Pset_StairCommon`,
   `Pset_StairFlightCommon`) already carry this exact quantity, spelled `NumberOfRiser`, not
   `RiserCount`. Adopting IFC's spelling turns this row from authored to inherited.
2. **`MinClearWidth_Narrowest` → `ClearWidth_Narrowest`.** IFC's `ClearWidth`
   (`Pset_RampFlightCommon`) carries no min/max qualifier, and `prd.md` §5.3's own Stair row uses
   the bare form — `ClearWidth_Narrowest` — for the identical measurement. The `Min` prefix here
   is both non-inherited and inconsistent with the same document's other use of the same base
   quantity.

## Names that carry no convention segment

14 of 27 names have no `_convention` suffix at all: `FloorAreaRatio`, `RiserHeight`,
`TreadLength`, `RiserCount`, `MinPlanDimension`, `ServedHeight`, `ProportionRatio`, `StallLength`,
`StallWidth`, `ManeuveringClearance`, `StallCount`, `TravelDistance`, `ExitWidth`,
`DeadEndLength`. S1.1.2 enforces "every quantity names its convention" at construction, so each
is judged here rather than assumed exempt.

**Legitimately convention-free — no plausible second reading exists:**

- `FloorAreaRatio`, `ProportionRatio` — ratios of two same-unit quantities. A dimensionless ratio
  carries no spatial reading of its own; whichever convention its inputs used is a property of
  those inputs, not of the ratio.
- `RiserCount`, `StallCount` — counts. An integer count has no inside-face, centreline or
  narrowest-point reading to disambiguate.
- `RiserHeight` — a single unambiguous vertical rise between two tread nosings; no competing
  physical definition exists the way "clear width" or "floor area" have several.
- `StallLength`, `StallWidth` — the dimensions of a drawn rectangle; unlike a corridor's clear
  width, a stall has one designed length and one designed width, not several candidate readings.
- `ManeuveringClearance` — a single designed clearance distance in front of or beside a stall,
  not a quantity with alternative measurement points in ordinary use.
- `MinPlanDimension` — already a stated extremum ("the smallest of the shaft's plan dimensions");
  the word "minimum" is doing the job a convention segment would do elsewhere, over a
  well-defined geometric set (the shaft's plan dimensions), not an ambiguous one.
- `ServedHeight` — the vertical span of storeys a shaft passes through, read once, top to bottom;
  no alternative face or offset reading applies to "which storeys this shaft serves."
- `TravelDistance`, `DeadEndLength` — lengths measured along a path, not across a footprint or
  opening. Area and width conventions (inside face, centreline, narrowest point) answer "measured
  across what boundary"; a path length has no boundary to choose between, only start and end
  points, which applicability logic fixes elsewhere, not a convention segment.

**Flagged, not fully legitimate — worth the ratifier's attention before S1.1.2, not changed
here:**

- `TreadLength` — IFC's own stair templates list three tread-length variants for the same
  element: `TreadLength`, `TreadLengthAtOffset`, `TreadLengthAtInnerSide`. That IFC itself
  distinguishes where along the tread the length is taken is evidence a convention segment
  belongs on this name, not evidence it is exempt. `prd.md` §5.3 lists it bare; this document
  does not resolve that, only names it.
- `ExitWidth` — conceptually the same kind of measurement as `ClearWidth_Narrowest` /
  `ClearWidth_BetweenHandrails` two rows above it in the same table, which are given convention
  segments precisely because a route's width can be read at its narrowest point or between
  handrails. `ExitWidth` bare is inconsistent with that precedent inside the same vocabulary.

## Invariant check

No name, base quantity, pset, or sentence in this document contains a jurisdiction, country, code
body or clause reference (I4). Every `authored` row states what was searched, and every
`inherited` row's IFC source was confirmed by the query in Method above before it was written —
run again per row while drafting this table.


---

## Amended by DEC-0030

Two rows above were changed after this audit was written, by the decision it prompted:

- **`RiserCount` → `NumberOfRiser`**, now inherited from `Pset_StairCommon`. The audit found
  §5.3 respelling a quantity IFC already ships — an I3 violation in the product's own source of
  truth — and `prd.md` §5.3 was amended to IFC's spelling.
- **`MinClearWidth_Narrowest` → `ClearWidth_Narrowest`**, now inherited from `ClearWidth`. Both
  `Pset_ACC_Stair` and `Pset_ACC_Space` carry that name; the pset qualifies the subject, so the
  name does not need to.

The counts above are therefore superseded: **10 of 27 names inherit a base quantity, 17 are
authored whole.** The 13 authored convention segments are unchanged.

`TreadLength` and `ExitWidth` remain bare and remain flagged. DEC-0030 §3 sends both to S1.1.2,
which owns the closed set of convention segments — naming a suffix before that set exists is how
a vocabulary acquires one-off names. S1.1.2 must resolve both explicitly and may not ship them
bare by omission.
