# Domain and subdomains

## The domain

**Establishing whether a building design satisfies the regulations in force for it, and
being exact about what was not established.**

The second clause is not a caveat. It is half the domain. A system that verifies well but
is vague about its own gaps produces the most dangerous artefact in this field: a clean
report over an unchecked building (`prd.md` I7, §5.7).

## The oracle problem

Coding agents work because compilation and tests are a free, instant, unambiguous oracle.
Building design has none. A wrong seismic factor, a stair 15 cm too narrow, a light well
below the required proportion — the model opens fine and the drawing looks correct.

This shapes the subdomain split more than anything else. **The core domain is the
manufacture of an oracle.** Everything the product eventually becomes — authoring,
generation, calculation — is downstream of an oracle existing, which is why `prd.md` §9
orders the phases by that dependency rather than by ambition.

It also shapes engineering practice here. Our own test suite has the same weakness the
product exists to eliminate: it can pass over a broken system. Hence `CLAUDE.md` §9 —
executed real path, shown wiring — rather than trust in green output.

## Subdomain classification

Classification decides investment. Core gets our attention and our best work. Supporting
gets competent, boring work. Generic gets inherited and never written (I3).

### Core — our actual asset

| Subdomain | Why core |
| --- | --- |
| **Findings & adjudication** | Three-valued status and applicability, coverage manifest, compliance routes, tolerance and margin, attribution, provenance. `prd.md` §7.7: "small in code, and most of what the product actually is." This is what the customer is buying, and no inherited component produces it. |
| **Basis resolution** | Which packs apply, at which edition, under which of four dates, with jurisdiction overlays, parcel entitlements and project departures layered in. The reason a finding can cite something resolvable (I5). Nothing in the ecosystem does this. |
| **Codification** | The harness that turns regulatory text into ratified, compiled, fixtured clause records. The corpus is the asset; this is the machine that produces it. |
| **Rule pack format & compiler** | The YAML clause record schema and its deterministic compilation to IDS. The place a domain expert who is not a programmer can work. |
| **Custom derivations** | The five or six geometric quantities nobody has written: stair clear width, shaft proportion, parking stall and maneuvering clearance, setback against zoning envelope, clear and floor-to-floor height. |
| **Parcel channel** | Cadastral and zoning ingest and its join to the model. Two of the highest-frequency rejection categories in real plan review cannot be checked without it. |

### Supporting — necessary, ours, not differentiating

| Subdomain | Note |
| --- | --- |
| **Pre-flight** | Read-only model inspection inside the host application. Ships in v0 because without it the MVP's failure mode is refusing a file and leaving the user stuck. First slice of the connector. |
| **Presentation** | Report templating, findings-marker compositing, marked sheets. Renderers and typography are inherited; the composition is ours. |
| **Assistance** | The agent: orchestration and conversation over findings. Strictly a consumer. Genuinely useful, structurally downstream, and forbidden from producing a verdict. |
| **Host connection** | MCP glue per host, beyond what pyRevit / Tapir / existing MCP servers already give. |

### Generic — inherited, never written (I3)

IFC parse and query, geometry kernel, quantity takeoff, model transformation, topology and
adjacency, clash, rule format, rule runner, IDS validation, ingest gate, findings
serialization, 2D drawing generation, web viewer, envelope extraction, georeferencing, GIS
handling, complex-script shaping, structural sections and solvers.

`prd.md` §6 is the standing inventory. Writing anything on it is a decision request, never
a task.

## The shape this produces

```
                  ┌─────────────────────────────────────────┐
   inherited      │  parse · geometry · topology · takeoff   │
   (generic)      │  IDS runner · gate · viewers · solvers   │
                  └────────────────┬────────────────────────┘
                                   │
                  ┌────────────────▼────────────────────────┐
   ours           │  custom derivations · parcel channel    │
   (core)         │  rule format & compiler · codification  │
                  │  basis resolution · findings            │
                  └────────────────┬────────────────────────┘
                                   │
                  ┌────────────────▼────────────────────────┐
   ours           │  presentation · assistance · pre-flight │
   (supporting)   │  host connection                        │
                  └─────────────────────────────────────────┘
```

The core is a thin band in the middle. That is the intended shape and the reason the
custom surface stays small enough for a small team to hold. Growth in the core is the
signal to watch: `prd.md` §5.5 tracks rules-per-derivation continuously because the
failure mode of this entire strategy is a derivation set that grows one-per-rule.
