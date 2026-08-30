# DEC-0002 — DDD as analysis and import contracts, not a bounded-context source layout

**Status:** DECIDED
**Date:** 2026-08-30
**Decided by:** Lead, under `prd.md` §6
**Affects:** `docs/ddd/`, `docs/architecture/module-map.md`

## Problem
The stakeholder asked for a DDD analysis. `prd.md` §6 explicitly **rejects** six bounded
contexts as the source-code layout: *"Sized for a custom engine this document does not build.
The import-contract idea (I1, I2) survives and applies to whatever modules exist."*

Delivering a conventional DDD structure would contradict a settled decision. Delivering no
DDD analysis would ignore the request and lose the thing DDD is actually good for here.

## Constraints
- `prd.md` §6 is settled and its Reopens condition — *"only if the custom surface of section 7
  grows enough to need one"* — is not met. §7 is six derivation recipes, a rule format, a
  compiler, a harness, a resolver, a findings wrapper and some templating.
- I3: the custom surface must stay small. A layout sized for a large engine invites one.
- I1 and I2 must be machine-enforced, and the enforcement must be showable to a customer or a
  regulator as a contract file.
- The real risks in this domain are semantic: a term meaning two things across a boundary, a
  convention lost in transit, an `INDETERMINATE` collapsed on the way to a report.

## Options
1. **Six-context ports-and-adapters layout.** Contradicts §6. Produces interface-per-class
   ceremony over a codebase whose largest context is a few hundred lines.
2. **No DDD.** Loses the vocabulary discipline and the invariant ownership map, which are the
   parts that actually prevent this product's failure modes.
3. **Contexts as contracts.** Full strategic analysis — subdomains, ubiquitous language,
   context map, aggregates, invariants — enforced by `import-linter` and dependency isolation
   rather than by directory structure. Source layout stays flat.

## Decision
Option 3. `docs/ddd/` carries the complete analysis and is normative. `docs/architecture/module-map.md`
is what it becomes on disk: flat, small, one directory per context, several of them a single
module. **A context is a contract enforced in CI, not a folder tree.**

## Expected result
- The DDD analysis catches semantic defects at review, because the vocabulary and the invariant
  ownership map are written down and single-sourced.
- The custom surface stays roughly the size `prd.md` §7 predicts. If `src/` grows past that
  while the inherited inventory has not shrunk, this decision was wrong.
- `import-linter`'s contract block is readable by someone who does not read Python.

## Reopens if
The custom surface of `prd.md` §7 grows enough to need a real hierarchy — the same condition
§6 printed. That is a §12 reopen, taken to the stakeholder with the growth as evidence.

## Consequences accepted
Boundaries are invisible in the directory tree. An agent that reads only the file layout will
not see them, which is why every module carries a `readme.ai.md` naming its context and its
forbidden edges, and why gate 7 makes that file mandatory.
