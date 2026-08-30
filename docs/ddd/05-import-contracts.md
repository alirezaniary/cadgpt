# Import contracts

I1 and I2 are not documented principles. They are machine-checked contracts, and the
contract file is an artefact a customer or a regulator can be shown.

## Why they need enforcement at all

Both erode the same way — one hard rule that is tedious to express declaratively, one
geometry case a model could just handle. Each concession is locally defensible and
collectively fatal, because **a checker that is deterministic ninety-five percent of the
time gives no guarantee at all**: the user cannot tell which five percent they are looking
at.

A principle that depends on remembering it will be violated by a well-meaning agent in a
hurry. So it is enforced twice, at two different strengths.

## Enforcement tier 1 — the dependency graph

The strongest form. **The checking engine's distribution does not depend on any inference
client**, so the import is not merely forbidden, it is unresolvable: the package is not
installed in that environment, and the import fails at runtime as an `ImportError` even if
every lint were disabled.

```
distribution                depends on inference SDK?
────────────                ─────────────────────────
engine                      NO   — parse, derive, compile, resolve, evaluate, findings
codification                YES  — the single permitted inference client
assistance                  YES  — consumes findings, produces no verdict
presentation                NO
connector                   NO
```

`codification` may depend on `engine` (it emits records the engine's schema defines).
`engine` may never depend on `codification` or `assistance`. The edge from codification to
the engine is a **committed file**, never a call.

This is why the packaging decision (DEC-0004) is a correctness decision and not a
convenience one.

## Enforcement tier 2 — declarative contracts in CI

`import-linter` contracts in `pyproject.toml`, run by `make verify`. Readable by someone
who does not read Python, which is half the point.

```toml
[[tool.importlinter.contracts]]
name = "I1 — no inference client reaches the checking engine"
type = "forbidden"
source_modules = ["engine"]
forbidden_modules = ["anthropic", "openai", "httpx", "codification", "assistance"]

[[tool.importlinter.contracts]]
name = "I1 — codification emits files, never calls the engine at check time"
type = "forbidden"
source_modules = ["engine"]
forbidden_modules = ["codification"]

[[tool.importlinter.contracts]]
name = "Assistance is strictly downstream"
type = "forbidden"
source_modules = ["engine", "presentation"]
forbidden_modules = ["assistance"]

[[tool.importlinter.contracts]]
name = "Context layering"
type = "layers"
layers = ["presentation", "findings", "evaluation", "resolution", "compilation", "derivation", "ingest"]
containers = ["engine"]

[[tool.importlinter.contracts]]
name = "I2 — geometry is authored only by typed generators"
type = "forbidden"
source_modules = ["assistance"]
forbidden_modules = ["engine.derivation", "generators.internals"]
```

`httpx` appears in the engine's forbidden list deliberately. An inference client reached
over raw HTTP is still an inference client, and forbidding only the SDK names invites
exactly that workaround.

## What each contract actually prevents

| Contract | The concrete bad day it prevents |
| --- | --- |
| No inference client in `engine` | A hard rule is tedious to express in YAML, so someone asks a model to evaluate it "just for this one clause". The result is cited, confident and unreproducible. |
| Codification never called at check time | Under schedule pressure, a missing rule is generated on demand during a run. Reproducibility dies silently; two runs of the same model disagree. |
| Assistance strictly downstream | The agent, which is good at ranking and explaining, is given "just a small suggestion" that becomes an input to a verdict. |
| Layering | Findings reach back into geometry to re-measure something, and the observation atom stops being the single join. |
| I2 generators | The model writes geometry directly because the typed generator does not cover a case. Walls do not close, cores do not align between floors, and nothing in the system can detect it. |

## What the contracts deliberately permit

- Explaining a finding. Ranking findings by likely cost to fix. Summarizing a coverage manifest. Drafting a clause record for a human to ratify. Translating a report.
- **The boundary is production of a verdict, not proximity to one.** These consume results rather than produce them.

## The one hole an import contract cannot close

A human clicks "accept" on a value the assistance layer suggested. The value becomes a
project fact. The engine — which imports nothing forbidden — then evaluates deterministically
on a number a model produced. No import contract sees this.

It is closed in the data model instead: **every project fact carries provenance**, humans
may `identify` but may not `measure`, and every finding depending on a `declared` fact is
marked as such wherever it appears (`04-aggregates-and-invariants.md`, `Project`).

Import contracts close the call path. Provenance closes the data path. Both are needed.

## Changing a contract

A contract is loosened only by a decision record in `decisions/` that names what replaces
the guarantee. "It was inconvenient" is not a replacement. Contracts are versioned with the
repository so the enforcement in force for any past release is recoverable.
