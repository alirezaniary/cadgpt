# Decision index

Two logs, one copy of each decision.

| Log | Holds | Status |
| --- | --- | --- |
| **`prd.md` §12** | Product decisions — what the system is, what it refuses to do, what a finding is | **Closed.** Do not re-open, re-argue or quietly improve one. Each carries its own Reopens condition. |
| **This directory** | Engineering and process decisions — how it is built, decomposed, proved and recorded | Open. Grows as work proceeds. |

A decision here may *reference* a `prd.md` §12 entry and add an engineering consequence. It
never restates one. Copying a decision creates a second copy that will drift, and a divergent
decision log is worse than none because it is consulted.

Format: `TEMPLATE.md` — Problem → Constraints → Options → Decision → Expected result →
Reopens if → Consequences accepted.

## Foundational

| # | Decision | Decided by | Status |
| --- | --- | --- | --- |
| [0001](DEC-0001-framework-before-code.md) | Framework before code; this log holds engineering decisions only | Stakeholder | DECIDED |
| [0002](DEC-0002-ddd-as-contracts.md) | DDD as analysis and import contracts, not a bounded-context source layout | Lead | DECIDED |

## Stack and architecture

| # | Decision | Decided by | Status |
| --- | --- | --- | --- |
| [0003](DEC-0003-python-and-uv.md) | Python 3.12+, managed by uv | Lead | DECIDED |
| [0004](DEC-0004-distributions-enforce-i1.md) | One repo, several distributions with disjoint dependency sets — I1 as a fact, not a policy | Lead | DECIDED |
| [0005](DEC-0005-static-enforcement.md) | import-linter, ruff, mypy --strict as the static enforcement layer | Lead | DECIDED |
| [0006](DEC-0006-postgis.md) | PostgreSQL 16 with PostGIS | Lead | DECIDED |
| [0007](DEC-0007-runtime-services.md) | FastAPI, Celery + Redis, S3-compatible storage, Docker Compose | Lead | DECIDED |
| [0008](DEC-0008-thatopen-overlay.md) | ThatOpen Engine (web-ifc) for the web overlay | Lead | DECIDED |
| [0009](DEC-0009-two-inference-planes.md) | Two inference planes behind one OpenAI-compatible port | Lead | DECIDED |
| [0019](DEC-0019-inherited-vs-authored-in-the-rule-layer.md) | What is inherited in the rule layer, and what cannot be | Lead | DECIDED |
| [0020](DEC-0020-rules-are-data.md) | Rules are versioned data records loaded at check time; the engine is jurisdiction-blind | Lead | DECIDED |
| [0023](DEC-0023-engine-group-transitive-http-client.md) | What "no HTTP client in the engine" means when an inherited component brings one | Lead | DECIDED |

## Process

| # | Decision | Decided by | Status |
| --- | --- | --- | --- |
| [0010](DEC-0010-test-policy.md) | 50/50 unit and integration, near-zero mocking, behaviour across layers | Stakeholder | DECIDED |
| [0011](DEC-0011-readme-ai-as-contract.md) | `readme.ai.md` is the module contract, and it is mandatory | Stakeholder | DECIDED |
| [0012](DEC-0012-five-levels.md) | Five decomposition levels, expanded breadth-first | Stakeholder | DECIDED |
| [0013](DEC-0013-prerequisite-order.md) | Prerequisite order is absolute; no part starts against an unbuilt dependency | Stakeholder | DECIDED |
| [0016](DEC-0016-harness-before-code.md) | The harness is built before the code it guards; every guard ships with a proof it fails | Lead | DECIDED |
| [0017](DEC-0017-fixtures-as-code.md) | Fixture models are generator scripts, never committed binaries | Lead | DECIDED |
| [0018](DEC-0018-escalation-is-a-file.md) | A subagent never decides; escalation is a file and a stop | Lead | DECIDED |
| [0021](DEC-0021-licence-not-tracked.md) | Licence and legal questions are out of engineering scope | Stakeholder | DECIDED |
| [0022](DEC-0022-gates-ship-with-their-artifact.md) | A gate ships with the artifact type it guards, not all at P0 | Lead | DECIDED |

## Direction

| # | Decision | Decided by | Status |
| --- | --- | --- | --- |
| [0014](DEC-0014-first-judgeable-outcome.md) | The first judgeable outcome is a coverage report on a real model | Stakeholder | DECIDED |
| [0015](DEC-0015-codification-harness-ratifier-open.md) | We build the codification harness; real corpus content is loaded last | Stakeholder | DECIDED |

## Open

None.

`DEC-0015` was previously listed here and is closed: real regulatory content is loaded last, by
stakeholder direction, and the entire pipeline is built and proven against sample and synthetic
packs. Who signs off on real clauses is answered before content is loaded, with a measured
review-time number from the harness.
