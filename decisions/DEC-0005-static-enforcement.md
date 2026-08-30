# DEC-0005 — import-linter, ruff, and mypy --strict as the static enforcement layer

**Status:** DECIDED
**Date:** 2026-08-30
**Decided by:** Lead
**Affects:** `pyproject.toml`, `make verify`

## Problem
Which tools enforce the layering, the forbidden edges, and the typed boundaries — and can the
enforcement be shown to someone who does not read Python?

## Constraints
- `prd.md` §3 wants CI enforcement that *"turns an abstract claim into a contract file a
  customer or a regulator can be shown."*
- Boundaries are invisible in the flat source layout (DEC-0002), so static tooling is the only
  thing that makes them real.
- The harness must be fast enough to run on every task, or agents will stop running it.

## Options
1. Code review. Fails against generated code by construction — nobody reads every diff, which
   is the premise of the whole method.
2. Custom AST checks. Full control, and a bespoke tool nobody else can read or audit.
3. `import-linter` for contracts, `ruff` for lint and format, `mypy --strict` for types.

## Decision
Option 3. Contracts live in `pyproject.toml` as declarative TOML with human-readable names —
`"I1 — no inference client reaches the checking engine"` — so the contract block *is* the
showable artefact.

Custom guards stay in `tools/` and are limited to the domain-specific checks no general tool
can do: jurisdiction guard, quote linter, compile drift, fixture gate, missing derivation,
derivation promotion, test balance.

## Expected result
Every forbidden edge in `docs/ddd/05-import-contracts.md` has a named contract that fails the
build when violated, and each ships with a test proving it fails on a deliberately bad input —
because a guard that has never failed may be finding nothing.

## Reopens if
`import-linter` cannot express a needed contract. Then that one contract moves to `tools/`,
with a record; the rest stay declarative.

## Consequences accepted
`mypy --strict` over `ifcopenshell`, which is loosely typed, will need stub work or targeted
ignores at that boundary. Confined to the ingest edge and documented there.
