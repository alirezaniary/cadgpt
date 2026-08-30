# readme.ai.md — repository root

## Purpose
An agentic engineering system for buildings: verify a design against the regulations in force
for it, deterministically, citing a resolvable basis for every verdict and naming every gap in
coverage.

**No source code exists yet.** This repository currently holds the product specification and
the engineering framework built around it. The first code is P0, the verification harness.

## Contract — read in this order

| Read | For |
| --- | --- |
| `prd.md` | The product. Invariants I1–I7 in §3, the inherit-vs-write split in §6 and §7, the validation gates in §11, the closed product decision log in §12. |
| `CLAUDE.md` | The stable engineering rules. Every session loads this. |
| `docs/roadmap/dependency-order.md` | What happens next, and why nothing else may start. |
| `docs/ddd/` | The domain analysis. Normative: code disagreeing with it is wrong. |
| `docs/architecture/` | Stack, module map, and the sixteen gates behind `make verify`. |
| `docs/process/` | How work is decomposed, bounded, executed and proved. |
| `decisions/INDEX.md` | Every engineering decision, and the one that is still open. |

## Invariants upheld here
The seven product invariants (`prd.md` §3) govern everything. Two are machine-checked:
**I1** — no inference client reaches the checking engine; **I2** — the model fills parameters on
typed generators and never authors geometry. Enforced by the dependency graph first and by
declarative import contracts second (`docs/ddd/05-import-contracts.md`).

## Depends on
Almost everything is inherited (`prd.md` §6): `ifcopenshell`, `ifcpatch`, `ifctester`,
`topologicpy`, buildingSMART IDS and its validation tooling, ThatOpen Engine, GDAL/Shapely.
The custom surface is `prd.md` §7 and is deliberately small.

## Must not depend on
Any vendor relationship, account, marketplace, partner programme, certification or online
service (I6). Permanent. Public scripting interfaces only, local installation only.

## Tests
None yet. Policy is decided: 50/50 unit and integration, mocking only at a genuine external
boundary, every behaviour proven across layers, fixtures as generator scripts.
`docs/process/testing-strategy.md`.

## How to run it
Nothing runs yet. The first runnable artefact is `make verify` over an empty tree, which is P0.

## Open questions
- **Five real IFC models from five different offices** are needed to judge O1 (`prd.md` §11
  Gate 3). This is the only external dependency the first outcome has, and it is not a decision.
- **Gate 4 — parcel data.** Blocks the setback and site-coverage checks, not the resolver.
- **Gate 2 — market shape.** Decides which host the pre-flight tool targets.

Rules are data, never code (DEC-0020). Real regulatory content is loaded last (DEC-0015); the
whole pipeline is built and proven against sample and synthetic packs.
