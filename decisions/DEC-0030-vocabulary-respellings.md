# DEC-0030 — Two §5.3 names adopt IFC's spelling; two convention gaps go to S1.1.2

**Status:** DECIDED
**Date:** 2026-08-30
**Raised by:** T-0009, the property vocabulary audit
**Decided by:** Lead
**Affects:** `prd.md` §5.3, `docs/ddd/06-property-vocabulary.md`, S1.1.2

## Problem
T-0009 resolved every `prd.md` §5.3 property name against IFC's own templates and found four
places where §5.3 disagrees with the ecosystem it claims to inherit from. Verified directly:

```
NumberOfRiser          -> ['Pset_StairCommon', 'Pset_StairFlightCommon']
RiserCount             -> NOT IN IFC
TreadLength            -> ['Pset_StairCommon', 'Pset_StairFlightCommon']
TreadLengthAtOffset    -> ['Pset_StairCommon', 'Pset_StairFlightCommon']
TreadLengthAtInnerSide -> ['Pset_StairCommon', 'Pset_StairFlightCommon']
ExitWidth              -> NOT IN IFC
MinClearWidth          -> NOT IN IFC
ClearWidth             -> ['Pset_TransportElementElevator', 'Pset_RampFlightCommon', ...]
```

`RiserCount` is the sharp one. IFC already names that exact quantity, and §5.3 spells it
differently — so the product's own source of truth authors a name the ecosystem ships. That is
an I3 violation sitting in `prd.md`, and it is exactly what DEC-0019 says to look for before a
line of code exists.

## Constraints
- `prd.md` is the product source of truth. `CLAUDE.md` §1 closes §12 to re-argument; §5.3 is a
  vocabulary specification, not a §12 decision, and naming is a technical matter the Lead owns.
- I3 — do not build what the open ecosystem already ships, and that includes not respelling it.
- A name in `prd.md` that differs from the name in the code guarantees drift. Deciding this and
  not applying it is worse than not deciding.
- The stakeholder is asked for directions, never details. Two spellings of the same measured
  quantity do not produce two materially different products.

## Decision

**1. `RiserCount` becomes `NumberOfRiser`.** IFC's spelling, verbatim, in both `prd.md` §5.3 and
the audit. The row moves from authored to inherited: 10 of 27 names now inherit, 17 are authored
whole.

**2. `MinClearWidth_Narrowest` becomes `ClearWidth_Narrowest`.** The base quantity is IFC's
`ClearWidth`; the `Min` prefix is not inherited and duplicates what `_Narrowest` already says.
`Pset_ACC_Stair` and `Pset_ACC_Space` then both carry `ClearWidth_Narrowest`, which is correct —
the same measured quantity under the same convention, on two different physical kinds. A pset
qualifies the subject; it does not need the name to.

**3. `TreadLength` and `ExitWidth` keep their bare spelling for now, and S1.1.2 resolves them.**
Both are flagged by the audit as probably needing a convention segment, and the evidence for
`TreadLength` is strong — IFC distinguishes three tread-length readings for one element, which
is the ecosystem itself saying the measurement point matters.

They are **not** decided here because the question is not "what is this name" but "what is the
closed set of convention segments", and that set is S1.1.2's deliverable. Choosing a suffix now,
before the scheme exists, is how a vocabulary acquires one-off names. S1.1.2 must resolve both
explicitly and may not quietly ship them bare.

## Expected result
`prd.md` §5.3 and `docs/ddd/06-property-vocabulary.md` agree, and every inherited name in both
is spelled exactly as IFC spells it. S1.1.2 inherits two named, open questions rather than two
silent inconsistencies.

## Reopens if
S1.1.2 finds that a convention segment on `TreadLength` cannot be stated without naming a
jurisdiction's reading of it. That would make it a role rather than a convention
(`CLAUDE.md` §2's test: if two authorities could disagree about it, it is a role) and the answer
would be to drop the quantity, not to name it badly.

## Consequences accepted
`prd.md` is edited by the Lead on a naming matter. The edit is confined to two identifiers in the
§5.3 vocabulary block, is recorded here with the queries that justify it, and changes no
requirement, no scope and no invariant. Any further §5.3 change is a fresh record.
