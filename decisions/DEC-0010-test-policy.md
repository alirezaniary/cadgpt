# DEC-0010 — 50/50 unit and integration, near-zero mocking, behaviour proven across layers

**Status:** DECIDED
**Date:** 2026-08-30
**Decided by:** Stakeholder, detailed by Lead
**Affects:** every module, `make verify` gate 15

## Problem
How to test a system that generates its own code, in a domain where a wrong answer looks
exactly like a right one. The failure this must prevent has already happened in this
workspace: full suites passing while the system was broken, because tests mocked and seeded
around the gaps.

## Constraints
- Stakeholder direction: 50/50 unit and integration, mocking as little as possible, all
  behaviours tested across the layers.
- The correctness risks live at boundaries — a convention lost between derivation and
  evaluation, an `INDETERMINATE` collapsed on the way to a report, a rule that compiled but
  requires an observation nothing produces.
- `prd.md` §8: a rule and its proof of correctness may not come from the same generator. That
  applies to our code as directly as to the corpus.
- Deterministic and reproducible is a product property (`prd.md` §5.6), so it must be a test
  property.

## Options
1. Test-pyramid default, heavy unit. Fast, and it proves every piece while missing every
   boundary defect — which is where this system's defects are.
2. Integration-only. Catches boundary defects; a failure points at the whole pipeline and
   localizing it costs a session.
3. 50/50, enforced per module, with mocking permitted only at a genuine external boundary.

## Decision
Option 3, enforced at 40–60% per module by harness gate 15. Mocking permitted for exactly two
things: a hosted inference API and a vendor authoring application. Never our own code, never
`ifcopenshell`, never the filesystem, never the database, never time, never an IFC file.

Every behaviour has at least one test entering at the outermost real entry point and exiting at
the real output. Every slice proves five things: happy path, missing-input path, boundary and
tolerance, citation, and the negative.

Fixture models are generator scripts, never committed binaries (DEC-0017).

## Expected result
A green suite means the real path ran over real inputs. The missing-input test in particular —
input absent, result `INDETERMINATE` with a specific reason — is present for every behaviour,
because its absence is invisible and is how a system silently passes unchecked buildings.

## Reopens if
The ratio distorts a specific module's testing — a pure value object may have little to
integrate. Then that module records an exception here, with its reason. The default does not
move.

## Consequences accepted
A slower suite than a unit-heavy one, and a real PostGIS container plus real IFC files in CI.
Both are cheap next to shipping a green suite over a broken system.
