# Module map

What the ten bounded contexts become on disk.

This layout is **flat and small on purpose**. `prd.md` §6 rejected a six-context source
hierarchy as oversized for the custom surface this product actually builds, and that
rejection governs here. A context is a contract enforced by import-linter, not a folder
tree with ports and adapters in it. Several contexts are a single module of a few hundred
lines, and that is the correct size for them.

**Nothing below exists yet.** A directory is created by the task that first needs it, with
its `readme.ai.md`, and never in advance (`CLAUDE.md` §6, no scaffolding).

```
cadgpt/
├── CLAUDE.md
├── prd.md
├── Makefile                     verify · test · run — the whole interface
├── pyproject.toml               distributions, dep groups, import-linter contracts
│
├── decisions/                   the decision log
├── docs/                        ddd · architecture · roadmap · process
│
├── src/
│   ├── engine/                  ✱ no inference dependency, ever (I1 tier 1)
│   │   ├── ingest/              context 1  — load, gate, report what is missing
│   │   ├── observation/         shared kernel — the Observation atom, conventions
│   │   ├── derivation/          context 2  — ifcpatch recipes + the manifest
│   │   ├── packs/               context 4  — clause record schema, YAML→IDS compiler
│   │   ├── resolution/          context 5  — timeline, adoptions, overlays, basis
│   │   ├── evaluation/          context 6  — the ifctester wrapper
│   │   └── findings/            context 7  — ✱ the core
│   │
│   ├── presentation/            context 8  — report, sheets, BCF, overlay payload
│   ├── codification/            context 3  — ✱ the only permitted inference client
│   ├── assistance/              context 9  — the agent; strictly downstream
│   ├── connector/               context 10 — pre-flight, MCP glue, per host
│   └── api/                     FastAPI surface + Celery tasks; no domain logic
│
├── packs/                       rule pack content — data, not code
│   └── <pack>/                  metadata · rules/ · specs/ · clauses/ · tests/
│
├── fixtures/                    fixture models as generator scripts (never binaries)
├── tools/                       build guards: quote linter, jurisdiction guard, drift
└── web/                         overlay only. No application shell in v0.
```

## Why the layering is this order

`import-linter`'s layers contract enforces top-to-bottom only:

```
presentation → findings → evaluation → resolution → packs → derivation → observation → ingest
```

`observation` sits low because it is the shared kernel: derivation produces the atom,
evaluation consumes it, and neither owns it. Putting it inside `derivation` would make
evaluation depend on derivation, and the two would stop being independently testable — which
matters because a structural-analysis producer of the same atom arrives in v4 (`prd.md` §5.11).

`packs` sits above `derivation` because a pack *declares* which derivations it requires. The
dependency runs pack → derivation, never the reverse; a derivation knows nothing about who
needs it. This is what lets required-versus-produced be computed statically.

`api` imports everything and is imported by nothing. It holds no domain logic — a rule
evaluated in a route handler is unreachable from a test and unrunnable from the CLI.

## Distributions and their dependency sets

The isolation that makes I1 a fact rather than a policy (`docs/ddd/05-import-contracts.md`).

| Distribution | Contains | May depend on |
| --- | --- | --- |
| `cadgpt-engine` | `src/engine` | ifcopenshell, ifcpatch, ifctester, topologicpy, shapely, pydantic. **No inference SDK, no HTTP client.** |
| `cadgpt-presentation` | `src/presentation` | engine, WeasyPrint, arabic-reshaper, python-bidi |
| `cadgpt-codification` | `src/codification` | engine, an inference SDK |
| `cadgpt-assistance` | `src/assistance` | engine, presentation, an inference SDK, MCP |
| `cadgpt-connector` | `src/connector` | MCP, host SDKs. The one distribution that ships to user machines rather than running on our servers. |
| `cadgpt-api` | `src/api` | all of the above |

An engine environment with no inference SDK installed is a deployable configuration and is
tested as one. That test is the proof of I1.

## Per-module obligations

Every directory under `src/` carries:

```
<module>/
├── readme.ai.md      the contract — what the next agent reads instead of the code
├── __init__.py       the public surface, explicit __all__
└── tests/            unit and integration, ~50/50, beside the code they prove
```

Tests live beside their module rather than in a mirrored top-level tree so that a subagent's
context file list — module + tests + `readme.ai.md` — is one contiguous directory. That is a
context-budget decision, and it is the reason it is worth stating.

## Where a new thing goes

| If it… | It belongs in | Watch for |
| --- | --- | --- |
| computes a quantity from geometry | `engine/derivation` | Is it already a library call? (I3) |
| names or types a quantity | `engine/observation` | Does the name carry its convention? |
| reads regulatory text | `codification` | Nothing else may. |
| decides which rule applies | `engine/resolution` | Never in `evaluation`. |
| decides what a finding says | `engine/findings` | Never in `presentation`. |
| renders anything | `presentation` | A renderer may not compute a verdict. |
| explains, ranks or summarizes | `assistance` | It must consume, never produce. |
| talks to a host application | `connector` | Public scripting interfaces only (I6). |
| is a fixture model | `fixtures/` | As a generator script, never a committed binary. |
| is a jurisdiction's rule | `packs/` | Content, not code. No jurisdiction name reaches `src/`. |
