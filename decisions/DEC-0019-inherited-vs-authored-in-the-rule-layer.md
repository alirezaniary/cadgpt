# DEC-0019 — What is inherited in the rule layer, and what cannot be

**Status:** DECIDED
**Date:** 2026-08-30
**Decided by:** Lead, prompted by a stakeholder challenge
**Affects:** `engine/packs`, `codification`, C1.1, O2

## Problem
The stakeholder asked, correctly in spirit: the rule schema is fixed, the open-source packages
ship templates for rules, and open source was chosen precisely so the contracts at the
boundaries could be inherited — so why are we authoring rules at all?

The question conflates two things that look like one, and the answer decides how much work O2
actually is.

## Constraints
- I3: we do not build what the open ecosystem already ships. The burden is on us to prove
  something is *not* available before writing it.
- I4: jurisdiction lives only in rule packs; the engine cannot tell which country it is in.
- `prd.md` §5.5: IDS is never extended and never forked.
- First target market is Iran (`prd.md` §8).

## What was checked
- **IDS 1.0** was approved as a final buildingSMART standard in June 2024. The schema is fixed,
  published, and has many implementing products.
- **buildingSMART's "Regulatory Information Requirements" project** publishes regulatory
  property definitions in the bSDD plus an **outline IDS explicitly described as a basis for
  localisation** — a template to be filled per jurisdiction, not filled content.
- **Encoded national rule sets** exist as research prototypes (e.g. escape-route rule sets
  against the Austrian building code) and as digital-building-permit research output. There is
  no established open collection of national codes as ready IDS packs, and nothing for Iran.
- Published research on digital building permits is about **extending** IDS to reach permit
  requirements — the same limitation `prd.md` §5.4 records: roughly two checks in twelve survive
  as native IDS, the rest need derivation.

## Decision

**Inherited, and not written by us:**

| | Source |
| --- | --- |
| The rule schema | buildingSMART IDS 1.0 |
| Schema validation | IDS-Audit-tool |
| The rule runner | `ifctester` |
| The YAML→IDS compiler base | `ids-light-editor` |
| Regulatory property definitions, where they exist | bSDD Regulatory Information Requirements |
| The localisation outline IDS, as our pack template | bSDD Regulatory Information Requirements |

**Cannot be inherited, and is therefore ours:**

The *content* — which clause sets which limit, on which subject, under which convention, with
which exceptions and which applicability. No such artefact exists for the first target market,
and if it did it would be a reading of that market's law by someone else, which is not a thing
one inherits.

**The distinction that answers the original question:** a fixed schema guarantees a rule is
**well-formed**. Nothing in a schema can guarantee a rule is **true**. A rule encoding 1.10 m
where the code says 1.20 m is perfectly valid IDS, passes IDS-Audit-tool, runs correctly in
`ifctester`, and produces a cited, deterministic, reproducible, wrong PASS. That is exactly the
failure `docs/architecture/harness.md` gate 8 exists for, and it is why a human reads the
source text — not because the format is unsettled.

## Consequence for C1.1 — a real scope reduction

`prd.md` §5.3 lists a `Pset_ACC_*` property vocabulary as ours to define. Before authoring it,
C1.1's first move is to check it against bSDD's regulatory property definitions and adopt every
term that already exists there, under I3. Ours becomes only the residue — principally the
convention-suffixed names (`NetFloorArea_InsideFace`) that `prd.md` §5.3 requires and that a
general vocabulary is unlikely to carry.

Same for the pack layout: it starts from the buildingSMART localisation outline rather than
from a blank schema.

## Expected result
O2's engineering shrinks to the codification harness and the compiler. Zero schema work, zero
runner work, zero validator work. What remains is content production, and content production is
where the human sits — for a reason that has nothing to do with format.

C1.1 authors fewer property names than `prd.md` §5.3 lists. If it authors more, I3 was violated
and the review should catch it.

## Reopens if
A public IDS pack for the first target market's code appears. Then it is evaluated for adoption
on merit — and it still needs a ratifier, because adopting someone else's reading of the law
under our product's name is the same assertion, made by someone we cannot name.

## Consequences accepted
A dependency on bSDD's regulatory vocabulary keeping pace. Mitigated because IDS matches on
property *name*: an unmapped term costs us a name we define ourselves, not a redesign.

## Sources
- buildingSMART, Information Delivery Specification (IDS) standard page
- buildingSMART Use Case Management, "Regulatory Information Requirements" (3378)
- "Extending Information Delivery Specifications for digital building permit requirements", ScienceDirect
