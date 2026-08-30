# DEC-0031 — `TreadLength` and `ExitWidth` take convention segments, inherited from IFC's own distinction

**Status:** DECIDED
**Date:** 2026-08-30
**Raised by:** DEC-0030 §3, deferred to S1.1.2
**Decided by:** Lead
**Affects:** `prd.md` §5.3, `docs/ddd/06-property-vocabulary.md`, S1.1.2

## Problem
T-0009 flagged two §5.3 names as bare but not legitimately convention-free. DEC-0030 deferred
them to S1.1.2 on the grounds that the closed convention set had to exist first. It now has to be
settled, because S1.1.2's whole contract is "a name with no convention is rejected at
construction", and a rule with two known exceptions it cannot express is not a rule.

The evidence, verified against ifcopenshell's IFC4 templates:

```
TreadLength            -> ['Pset_StairCommon', 'Pset_StairFlightCommon']
TreadLengthAtOffset    -> ['Pset_StairCommon', 'Pset_StairFlightCommon']
TreadLengthAtInnerSide -> ['Pset_StairCommon', 'Pset_StairFlightCommon']
ExitWidth              -> NOT IN IFC
```

IFC ships **three** tread-length properties for one element. That is the ecosystem stating, in
its own schema, that where along the tread the length is taken changes the number. A bare
`TreadLength` in our vocabulary would be a quantity whose convention is decided by whoever
computes it — the precise defect `prd.md` §5.3 exists to prevent.

`ExitWidth` is the same kind of measurement as `ClearWidth_Narrowest` and
`ClearWidth_BetweenHandrails`, which sit two rows above it in the same table and carry conventions
for exactly this reason: a width can be read at more than one place.

## Constraints
- `CLAUDE.md` §2: every quantity names its measurement convention, in its name. The exceptions are
  counts and ratios, which have no spatial reading; neither of these is one.
- I3 / DEC-0019: where the ecosystem already distinguishes readings, inherit its distinction
  rather than inventing a parallel one.
- `CLAUDE.md` §2's role test: if two authorities could disagree about it, it is a role, not a
  convention. Both survive that test — where a length is measured is physical; which reading a
  code *requires* is the role, and stays in the rule pack.
- The convention segment must be jurisdiction-free (I4).

## Decision

**1. `TreadLength` becomes `TreadLength_AtWalkingLine`.** IFC's family is
`TreadLength` / `TreadLengthAtOffset` / `TreadLengthAtInnerSide`, so the distinguishing concept
is *where across the tread the going is measured*. The walking line — the offset path a person
actually travels, which is what IFC's `AtOffset` variant parameterises — is the reading a going
is normally specified against, and naming it makes the other two nameable later on the same
pattern (`TreadLength_AtInnerSide` if a pack ever needs it).

This inherits IFC's distinction rather than inventing one. It does not adopt IFC's spelling,
because IFC encodes the convention as three separate property names and we encode it as one base
plus a segment; that is our scheme applied to their concept, and it is the whole reason §5.3
exists.

**2. `ExitWidth` becomes `ExitWidth_Narrowest`.** The same convention segment already used by
`ClearWidth_Narrowest`, for the same reason, in the same vocabulary. Consistency inside our own
table is the point: two widths measured the same way must say so the same way.

**3. Neither is a role.** "Exit" and "tread" are physical kinds. Which openings *count* as egress
components, and which reading a code demands, are role assignments made by a selector inside a
rule pack at check time — never stored, never in a property name.

## Expected result
Every §5.3 name that denotes a measurement carries a convention segment, so S1.1.2's construction
rule has no exceptions it cannot express. The convention-free set reduces to counts, ratios, and
the single-reading dimensions T-0009 justified individually.

## Reopens if
A rule pack needs a tread going measured at the inner side, or an exit width between projections
rather than at the narrowest point. Neither reopens this record — both are *additions* to the
convention set on the pattern it establishes, which is what the pattern is for. This record
reopens only if `_AtWalkingLine` turns out to be unmeasurable from authored geometry, in which
case the quantity is dropped rather than renamed badly.

## Consequences accepted
`prd.md` §5.3 is edited a second time by the Lead on a naming matter, under the same terms as
DEC-0030: two identifiers, no requirement, scope or invariant changed, recorded with the evidence.
A third such edit should prompt asking whether §5.3 wants a full pass rather than another
increment.
