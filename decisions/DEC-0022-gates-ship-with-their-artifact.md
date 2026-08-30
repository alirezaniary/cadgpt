# DEC-0022 — A gate ships with the artifact type it guards, not all at P0

**Status:** DECIDED
**Date:** 2026-08-30
**Decided by:** Lead — correction to DEC-0016, found while decomposing P0
**Affects:** P0, `docs/architecture/harness.md`, every task that introduces an artifact type

## Problem
DEC-0016 says `make verify` runs **all sixteen** gates over an empty repository and passes.
Decomposing P0 shows that is not buildable, and the reason is DEC-0013.

Seven of the sixteen guard artefacts whose schema does not exist yet:

| Gate | Guards | Needs first |
| --- | --- | --- |
| 3 · import contracts | modules under `src/` | any `src/` package (C1.1) |
| 8 · quote linter | clause records | the record schema (O2) |
| 9 · IDS audit | compiled `.ids` | the compiler (O2) |
| 10 · compile drift | generated artefacts | the compiler (O2) |
| 11 · fixture gate | pack fixtures | the pack format (O2) |
| 12 · missing derivation | the observation manifest | the manifest (C1.5) |
| 13 · derivation promotion | the derivation registry | derivations (C1.3) |

Writing them now means inventing the schema they parse, which is writing against an assumption
about unbuilt code — precisely what DEC-0013 forbids. Building them later, separately, means a
window in which the artefact exists unguarded — which is what DEC-0016 exists to prevent.

## Constraints
- DEC-0013: no part starts while anything it depends on is unbuilt. Absolute.
- DEC-0016: guards exist before the code they guard, and a guard without a proof it fails is
  not merged.
- A gate that runs over nothing and reports success is the failure mode DEC-0016 names
  explicitly: indistinguishable from a gate that is misconfigured.

## Decision
The harness is a **gate registry**, not a fixed list. P0 builds the registry mechanism plus the
**nine gates whose inputs already exist** — ruff, mypy, isolation probe, jurisdiction guard,
placeholder scan, module contract, pytest, test balance, determinism.

Every remaining gate is added **by the task that introduces the artefact type it guards, in that
same task**, with its failure proof. Adding it is a delivery condition of that task, not
follow-up work.

Registering a gate is one entry in the registry, one module, one failure proof. That cost is
deliberately small so no task is tempted to defer it.

This satisfies both rules: no gate is written against an imagined schema, and no artefact type
exists for even one commit without its guard.

## Expected result
`make verify` reports how many gates are registered and runs all of them. The count grows from
nine as artefact types appear. A task that introduces an artefact type without its gate fails
review.

Gates 5, 6 and 7 scan `src/`, which is empty at P0 — so each is proven by a deliberately bad
fixture, not by its scan target. That is the whole reason DEC-0016 requires the failure proof.

## Reopens if
Never. This is DEC-0016 corrected, not reversed: guards still precede the code they guard, and
"before" is now measured per artefact type rather than per repository.

## Consequences accepted
The gate count is not fixed, so "make verify passes" means less on day one than it will later.
Mitigated by the runner printing the registered count, making the harness's own coverage visible
rather than assumed.
