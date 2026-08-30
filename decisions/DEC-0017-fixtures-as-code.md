# DEC-0017 — Fixture models are generator scripts, never committed binaries

**Status:** DECIDED
**Date:** 2026-08-30
**Decided by:** Lead
**Affects:** `fixtures/`, every pack, every test

## Problem
`prd.md` §8 step 6 requires one passing and one failing model committed with every rule, and a
rule without both is not merged. The corpus is meant to become large, so this is thousands of
models. In what form do they exist?

## Constraints
- `prd.md` §5.5: rule packs must be readable and editable by a domain expert who is not a
  programmer, and every pack's fixtures run in CI.
- Compiled artefacts are committed and regenerated in CI with drift failing the build, on the
  stated principle that *"what runs must be reviewable, and a generated artefact nobody can read
  is not."* The same principle applies to fixtures.
- `prd.md` §8: a rule and its proof of correctness may not come from the same generator.

## Options
1. **Committed `.ifc` files.** Realistic, and unreviewable. Nobody can see in a diff that a
   fixture's stair width moved from 1.10 to 1.20 — so nobody can see that a passing test now
   passes for a different reason. Repository size grows without bound.
2. **Generator scripts producing models at test time.** Every change is a one-line diff. Models
   are minimal by construction, because writing irrelevant geometry is work.
3. Both, with the binary as a cache. Two sources of truth and a cache-invalidation problem
   between them.

## Decision
Option 2. `fixtures/` holds committed deterministic generator scripts using
`ifcopenshell.api`. No `.ifc` is committed anywhere in the repository.

Generators are minimal — the smallest model exhibiting the behaviour. A fixture carrying
irrelevant geometry makes every test using it slower and its failures harder to read.

Where a Task session writes an implementation, its **adversarial fixtures are specified in the
task spec by the Lead**, not invented by the implementer. An implementer's fixtures test what
they built; the spec's fixtures test what was asked for.

## Expected result
A fixture change is a readable line in a diff, and Review can see what a test now asserts.
Repository size stays flat as the corpus grows into the thousands.

## Reopens if
A real-world defect can only be reproduced by a model that is impractical to generate — a
genuine exporter quirk from a specific vendor version. Then that one file is committed, with a
record naming it and the defect it reproduces. It is an exception with a name, never a
practice.

## Consequences accepted
Fixture generation costs test time, and generator scripts are extra code. Both are small, and
they buy the property that matters: a test whose meaning is visible in a diff.
