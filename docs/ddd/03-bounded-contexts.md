# Bounded contexts and the context map

## The tension this document resolves

`prd.md` §6 **rejects** six bounded contexts as the source-code layout: "Sized for a custom
engine this document does not build. The import-contract idea (I1, I2) survives and applies
to whatever modules exist."

That rejection is correct and it stands. But it rejects a *folder layout*, not the analysis.
Bounded contexts remain the right tool for the thing that actually matters here: a term
means different things on either side of a boundary, and the boundaries are where the
product's guarantees live.

**Resolution: contexts are real, named, and machine-enforced as import contracts — not as
a ports-and-adapters directory hierarchy.** A context is a *contract*, not a folder. One
context may be a single module of two hundred lines. `docs/architecture/module-map.md` is
what this becomes on disk, and it is flat.

This is DEC-0002.

## The ten contexts

Ordered by data flow.

### 1. Model Ingest
Model file in; gated; nothing derived yet.
**Language:** model file, entity, base quantity, georeference, gate finding, export preset.
**Ours?** Almost nothing. The gate is inherited (buildingSMART validate + ifc-gherkin-rules).
**Guarantee:** never guesses, never repairs. Missing input is named, not filled.

### 2. Derivation
Geometry → observations, written back onto the model as conventionally-named properties.
**Language:** observation, convention, measured/related/derived, provenance, confidence,
recipe, manifest, required-vs-produced.
**Ours?** Five or six recipes. Everything else is a library call.
**Guarantee:** the only place geometric reasoning lives. Measure, never invent.

### 3. Codification  ← the one context permitted an inference client
Regulatory text → ratified clause records, as committed files.
**Language:** source text, clause, draft, ratifier, quote, extraction, classification.
**Ours?** All of it. The harness, not the content.
**Guarantee:** artifact-mediated and never in the request path. Its output is a diff in
version control. A bad codification run is a bad diff — reviewable and revertable — rather
than a bad answer already delivered to a customer.

### 4. Rule Compilation
Clause record → IDS specification. Deterministic, mechanical, reviewable.
**Language:** spec, facet, restriction, applicability predicate, derivation dependency,
compiled artefact, drift.
**Guarantee:** the *only* path from record to running check. No generated code, ever.

### 5. Basis Resolution
Project + timeline + jurisdiction → the effective rule set, and the basis behind each rule.
**Language:** adoption, edition, overlay, conflict policy, entitlement, departure, closure,
resolution order, effective rule set.
**Guarantee:** resolution order is fixed — base adoption, then overlays outermost to
innermost, then parcel entitlement, then project departure. An unresolvable conflict is
reported as unresolvable, never guessed.

### 6. Evaluation
Effective rule set × derived model → raw verdicts. A thin wrapper over `ifctester`.
**Language:** run, specification result, verdict, reproducibility.
**Guarantee:** deterministic and reproducible from input model hash and pack versions alone.
The one place our code sits between the inherited runner and the user.

### 7. Findings & Adjudication  ← the core
Verdicts + manifests + resolution → findings and a coverage manifest.
**Language:** finding, status, applicability, basis, attribution, margin, tolerance, near-miss,
route, provenance, coverage manifest, disposition, stable identity.
**Guarantee:** I7 lives here entirely. Three-valued in, three-valued out, never collapsed.

### 8. Presentation
Findings → report, web overlay, marked sheets, BCF.
**Language:** report, overlay, marker, viewpoint, sheet, severity grouping, locale, reading direction.
**Guarantee:** presents coverage before findings. A renderer may not compute a verdict.

### 9. Assistance
Conversation and orchestration over findings.
**Language:** tool, query, summary, explanation, ranking, suggestion.
**Guarantee:** consumes results, never produces them. Sees extracted summaries and query
results, never raw model files. Structurally downstream of everything.

### 10. Host Connection
The user's authoring application. Pre-flight in v0, the full connector later.
**Language:** host, command, selection, marker placement, MCP tool.
**Guarantee:** public scripting interfaces only, local only, no vendor account or service (I6).
Read is built first and completely; write is an addition to the same component.

## The context map

```
    ┌──────────────┐
    │ Codification │  ✱ only inference client
    └──────┬───────┘
           │  PUBLISHED LANGUAGE: committed YAML clause records in version control
           │  ✱ artifact-mediated — this edge is a git diff, never a call
           ▼
    ┌──────────────────┐        ┌───────────────────┐
    │ Rule Compilation │───────▶│ Basis Resolution  │
    └────────┬─────────┘  IDS   └─────────┬─────────┘
             │  CONFORMIST to buildingSMART IDS 1.0    │
             │                                          │ effective rule set
             ▼                                          ▼
    ┌──────────────┐   ┌──────────────┐        ┌────────────────┐
    │ Model Ingest │──▶│  Derivation  │───────▶│   Evaluation   │
    └──────────────┘   └──────┬───────┘ model  └────────┬───────┘
       CONFORMIST to IFC      │                          │ verdicts
                              │ SHARED KERNEL:           │
                              │   the Observation atom   │
                              └────────────┬─────────────┘
                                           ▼
                                 ┌──────────────────────┐
                                 │ Findings & Adjudic.  │  ← core
                                 └──────┬───────────────┘
                            OPEN HOST SERVICE: findings JSON / BCF
                        ┌───────────────┴───────────────┐
                        ▼                               ▼
                ┌──────────────┐               ┌──────────────┐
                │ Presentation │               │  Assistance  │
                └──────┬───────┘               └──────┬───────┘
                       └───────────┬──────────────────┘
                                   ▼
                          ┌──────────────────┐
                          │ Host Connection  │
                          └──────────────────┘
```

## Relationship types, and why each was chosen

| Edge | Pattern | Rationale |
| --- | --- | --- |
| Codification → Rule Compilation | **Published language, artifact-mediated** | The load-bearing property of the whole design. Because the edge is a committed file rather than a service call, the engine has no runtime dependency on a model, runs stay reproducible from records alone, and the codification service can be offline, rewritten or replaced without touching a single guarantee. This is how I1 survives contact with the one place a model is allowed. |
| Rule Compilation → Evaluation | **Conformist** (to IDS 1.0) | We bend to buildingSMART's format completely. The moment our IDS files stop being valid IDS, twenty-plus implementing products stop being inheritable. Never extended, never forked. |
| Model Ingest → Derivation | **Conformist** (to IFC) | Same logic. There is no internal schema and no anticorruption layer; a custom schema with a maintained IFC mapping was considered and rejected (`prd.md` §6). |
| Derivation ↔ Evaluation | **Shared kernel** — the Observation | Deliberately shared, deliberately tiny. Geometry input and structural-analysis input are two *producers of the same atom* consumed by one checker, which is why calculation extends this architecture instead of adding a second one. Where both describe the same building they corroborate; disagreement is itself a finding. |
| Evaluation → Findings | **Supplier / customer, with Findings wrapping** | `ifctester` is natively two-valued, which §5.7 forbids. The third value is produced *around* it: a rule whose required observations are absent is emitted as `INDETERMINATE` with a reason and never handed to `ifctester` at all. A wrapper, not a fork. |
| Findings → Presentation, Assistance | **Open host service** | One findings set, several consumers, published as JSON and BCF. Adding a consumer must never require changing Findings. |
| Assistance → everything | **Downstream only, contract-enforced** | Assistance may import Findings. Nothing may import Assistance. This is one direction of I1's import contract and it is checked in CI. |

## What being in a context obliges you to

1. A term means exactly one thing inside a context. Where it means something else across a boundary, the boundary translates — explicitly, in a named function, tested.
2. A context owns its invariants and enforces them at its edge. It does not re-check what a neighbour already guaranteed.
3. A context's public surface is its `readme.ai.md` contract. Reaching past that surface into a neighbour's internals is an import-contract violation.
4. New vocabulary entering a context goes into `02-ubiquitous-language.md` in the same task.
