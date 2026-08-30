# DEC-0020 — Rules are versioned data records loaded at check time; the engine is jurisdiction-blind

**Status:** DECIDED
**Date:** 2026-08-30
**Decided by:** Lead, under I4; question raised by Stakeholder
**Affects:** `packs/`, `src/engine`, `make verify` gate 5

## Problem
Are rules and their format hard-coded into the software, or are they records the system loads?

The question is worth a record because both answers produce a working demo, and only one
produces a product. Compiling a jurisdiction into the engine is the specific failure I4 exists
to prevent, and it happens gradually — one hard rule that is easier as an `if`, one property
name that carries a code reference.

## Constraints
- **I4:** the engine cannot tell which country it is running in. A jurisdiction is a set of
  loaded rule packs and nothing else, and adding a country is authoring work, not engineering
  work.
- `prd.md` §5.5: rule packs are the modular compliance unit and the only place a jurisdiction
  exists. A national code, a municipal rule set and an office QA checklist are the same object
  type and load identically.
- `prd.md` §5.3: one model must be checkable under several codes at once, receiving different
  role assignments for the same element.
- Packs are versioned against code cycles and effective dates; a project is checked against the
  code in force for its permit date.

## Decision

Three layers, and only the middle one is ours:

| Layer | What it is | Where it lives | Changes when |
| --- | --- | --- | --- |
| **Format** | IDS 1.0 | External standard | buildingSMART revises it. Not our decision, ever. |
| **Rules** | Clause records → compiled IDS | `packs/` — **data, not code** | A code is amended, an edition supersedes, a jurisdiction is added |
| **Engine** | Generic evaluation | `src/` — jurisdiction-blind | Never, for a new jurisdiction |

A pack is a directory of files: authored YAML clause records, compiled `.ids`, a clause index,
declared derivation dependencies, and fixtures. It is loaded at check time. **Nothing about any
jurisdiction ever enters `src/`.**

Enforced, not trusted: harness gate 5 fails the build if a country, code, jurisdiction or clause
reference appears in any identifier under `src/`.

## Expected result
- Adding a jurisdiction is dropping files into `packs/`. Zero lines of `src/` change. If a new
  jurisdiction ever requires a code change, either I4 was violated earlier or the rule format
  has a gap — and a gap in the format is fixed **in the format**, never with a special case.
- One model can be checked against two jurisdictions in one run, producing different role
  assignments for the same element.
- Rolling a code cycle forward is publishing a new pack version, and old runs stay explainable
  because each run records the pack versions and resolved adoption closure it used.
- Swapping the entire corpus for a different country is a configuration change.

## Reopens if
Never. This is I4, and I4 does not reopen. A regulation that cannot be expressed as pack content
is a gap in the rule format, to be fixed in the format (`prd.md` §10).

## Consequences accepted
More indirection than hard-coding: a rule cannot be read by opening a source file, and debugging
a wrong finding means tracing record → compiled spec → observation → verdict. That trace is
required output anyway — every finding carries its basis and attribution — so the cost is
already paid.
