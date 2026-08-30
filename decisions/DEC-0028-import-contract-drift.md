# DEC-0028 — The layers contract names `packs` and `observation`, and drops the dangling generator module

**Status:** DECIDED
**Date:** 2026-08-30
**Raised by:** Lead, reading `docs/ddd/05-import-contracts.md` before specifying S1.1.2
**Decided by:** Lead
**Affects:** `docs/ddd/05-import-contracts.md`, gate 3, S1.1.2

## Problem
`docs/ddd/05-import-contracts.md` carries the `import-linter` contracts gate 3 will run. It has
never been executed — gate 3 ships at C1.1, and `src/` does not exist — and three of its module
names do not resolve against `docs/architecture/module-map.md`:

1. **`compilation` is not a module.** The layers contract reads
   `["presentation", "findings", "evaluation", "resolution", "compilation", "derivation", "ingest"]`.
   `module-map.md` puts context 4 on disk at `src/engine/packs/`. `import-linter` resolves
   *modules*, not contexts, so this contract would fail to load rather than fail to pass.
2. **`observation` is absent from the layers list entirely.** `module-map.md`'s own ordering is
   `presentation → findings → evaluation → resolution → packs → derivation → observation → ingest`,
   and it explains at length why `observation` sits low: it is the shared kernel, produced by
   derivation and consumed by evaluation, and neither may own it. The layer that C1.1 exists to
   build is the one layer the layering contract does not constrain.
3. **`generators.internals` does not exist and is not planned at O1.** The I2 contract forbids
   `assistance` from importing it. A `forbidden_modules` entry naming an unresolvable module is
   an `import-linter` error, not a satisfied contract.

Each is the same class of defect: a contract that looks like enforcement and would not run.

## Constraints
- `docs/ddd/05-import-contracts.md` §Changing a contract: a contract is loosened only by a
  decision record naming what replaces the guarantee. Two of these three are corrections rather
  than loosenings, and the third is a loosening that must say so.
- `CLAUDE.md` §6: ubiquitous language is binding, a synonym is a bug.
- A context and a module need not share a name. `module-map.md` already treats them separately
  and `prd.md` §6 rejected a folder-per-context hierarchy explicitly.

## Decision

**1. The layer is `packs`.** The *context* keeps its name, Rule Compilation
(`docs/ddd/03-bounded-contexts.md` §4). The *module* is `engine.packs`, and the layers contract
names the module. No renaming of the context, no renaming of the directory.

The collision with the top-level `packs/` directory — rule pack *content*, data, not code — is
noted and accepted: `import-linter` sees `engine.packs` and nothing else, and `module-map.md`
already made this choice. Not reopened here.

**2. `observation` is inserted between `derivation` and `ingest`**, making the contract's order
identical to `module-map.md`'s. This is a correction of an omission, and it *tightens* the
contract.

**3. `generators.internals` is removed from the I2 contract.** The `engine.derivation` half
stays, so `assistance` still cannot reach the derivation layer.

This is a **loosening**, and what replaces the guarantee is this: there is no geometry-authoring
module at O1, so there is nothing for the entry to protect. The typed-generator boundary I2
describes becomes real at O9 (authoring, v3), and the entry is restored **in the task that
creates the generator module**, under DEC-0022 — a guard ships with the artefact type it guards.
Until then the contract must resolve, and an unresolvable name means gate 3 does not run at all,
which protects nothing while appearing to protect something.

## Expected result
Gate 3's contracts load and run the first time S1.1.2 registers them, against
`src/engine/observation` — the layer that C1.1 builds and that item 2 restores to the contract.
`docs/ddd/05-import-contracts.md` and `docs/architecture/module-map.md` state one layering, not
two.

## Reopens if
The generator module arrives and its task does **not** restore the I2 entry. That is the failure
this record's §3 is a promissory note against, and it is why the removal is logged rather than
quietly edited.

## Consequences accepted
Between now and O9 there is no import contract preventing an `assistance` module from importing a
geometry generator, because there is no geometry generator. The exposure is zero today and grows
the moment one exists — which is exactly when DEC-0022 requires the guard back.
