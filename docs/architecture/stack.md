# Stack

Every choice below is either forced by `prd.md` or decided here with a reason. Forced
choices are marked; they are not open for reconsideration by a task.

## Forced by the PRD

The inherited inventory (`prd.md` §6) is almost entirely Python, and the two components the
whole architecture rests on — `ifcopenshell`/`ifcpatch` and `ifctester` — are Python.

| Concern | Component | Forced by |
| --- | --- | --- |
| IFC parse, geometry, takeoff, transform | `ifcopenshell`, `ifcpatch`, `ifc5d.qto` | §6 |
| Topology, adjacency, routes | `topologicpy` | §6 |
| Rule format | buildingSMART IDS 1.0 | §5.5, never forked |
| Rule runner | `ifctester` | §5.6 |
| IDS validation | IDS-Audit-tool | §5.5 |
| YAML→IDS compiler base | `ids-light-editor` schema | §5.5 |
| Ingest gate | buildingSMART validate, `ifc-gherkin-rules` | §5.2, §6 |
| 2D drawings | `ifcopenshell.draw` / IfcConvert SVG | §5.8, no Blender |
| GIS / parcel | GDAL/OGR, Shapely, GeoPandas | §6 |
| Envelope, georeferencing | `IFC_BuildingEnvExtractor`, `ifcgref` | §6 |
| RTL and complex script | `arabic-reshaper`, `python-bidi`, HarfBuzz, WeasyPrint | §5.8 |
| Connector protocol | MCP over localhost | §5.10 |
| Structural (v4) | `sectionproperties`, `concreteproperties`, PyNite/anaStruct, OpenSeesPy | §5.11 |

## Decided here

| Concern | Choice | Reason | Decision |
| --- | --- | --- | --- |
| Language / runtime | **Python 3.12+** | Forced in practice by the above. 3.12 for the typing features the strict boundaries rely on. | DEC-0003 |
| Dependency & env manager | **uv**, single lockfile, per-distribution dependency groups | Reproducible resolution, and — the reason it matters here — it makes *dependency isolation between distributions* cheap, which is how I1 is enforced at tier 1. | DEC-0003 |
| Repo layout | **One repo, several distributions** with disjoint dependency sets | The engine distribution must be installable without any inference SDK present, so I1 is unresolvable rather than merely forbidden. | DEC-0004 |
| Import enforcement | **import-linter** + ruff + `mypy --strict` | import-linter contracts are declarative TOML, readable by a non-programmer, and produce the contract file §3 says a customer or regulator can be shown. | DEC-0005 |
| API | **FastAPI + Pydantic v2** | Typed boundaries throughout, and the schema is the API contract rather than a document describing one. | DEC-0007 |
| Persistence | **PostgreSQL 16 + PostGIS**, SQLAlchemy 2.0, Alembic | PostGIS is not optional: the parcel channel joins cadastral boundary and zoning envelope geometry to a georeferenced model. Doing that outside the database means loading every parcel into process memory. | DEC-0006 |
| Long jobs | **Celery + Redis** | A check run is minutes of CPU-bound geometry work. Celery is the boring, observable, retryable choice, and the on-prem deployment target rules out a managed queue. | DEC-0007 |
| Object storage | **S3-compatible, MinIO on-prem** | Model files are large and must be able to stay inside a customer's network (§5.9, §5.10). | DEC-0007 |
| Web overlay | **ThatOpen Engine (web-ifc)** | §5.8 leaves it open between ThatOpen and xeokit. ThatOpen: actively developed, TypeScript-native, loads IFC directly without a conversion step, BCF viewpoint round-trip, 2D-in-3D markers. Choosing now avoids a fork in the presentation contract. | DEC-0008 |
| Frontend | TypeScript, React, Vite | Only where the overlay needs it. There is no application shell in v0. | DEC-0008 |
| Inference | **Two planes**, one interface | See below. | DEC-0009 |
| Containers | Docker Compose for development; the same images on-prem | The deployment target is a customer's own network. Dev and prod running different substrates would hide exactly the failures that matter. | DEC-0007 |
| Docs | Markdown in-repo, Mermaid diagrams | Reviewable in a diff. A documentation site is not a v0 need. | — |

## The two inference planes

`prd.md` §5.9 requires self-hosted open-weight inference "for latency, cost, and keeping
client drawings inside the deployment's own network." `prd.md` §8 requires an LLM API call
over regulatory text.

These are different workloads with different data and different constraints, and treating
them as one produces a bad answer for both.

```
                    Codification plane          Assistance plane
                    ──────────────────          ────────────────
Reads               public regulatory text      client drawings, findings
Runs                offline, batch, rare        online, per request
Output reviewed by  a named human ratifier      nobody — it reaches the user
Quality bar         extraction accuracy over    latency and cost
                    Persian legal prose
Choice              hosted frontier API         self-hosted open-weight (vLLM)
```

The privacy constraint in §5.9 attaches to *client drawings*. Regulatory text is public —
§8 notes this is a materially better position than markets needing a data licence. So a
hosted frontier model is permissible for codification and is the right call, because
extraction quality over legal prose in a non-Latin script is the binding constraint on
corpus quality, and every draft passes a human ratifier anyway.

Both sit behind **one OpenAI-compatible port**, so the backend is a configuration value and
neither plane's choice is embedded anywhere. Neither is importable from `engine` (I1).

## Deliberately not chosen

| Rejected | Why |
| --- | --- |
| A custom internal schema with an IFC mapping | Large custom surface, contradicts I3. `prd.md` §6, settled. |
| BIMserver | Java 8 on a Jetty 9 base that reached end of life; its checking plugins are weaker than `ifctester` against IDS. `prd.md` §6. |
| Headless Blender / Bonsai for drawings | `ifcopenshell.draw` does the job without the dependency. Option only if sheet furniture becomes a shipping requirement. |
| RDF/BOT + SHACL/SPARQL for rules | Genuinely dissolves the IDS limitation, but it is a second full stack with no non-programmer authoring tools, against IDS's twenty-plus implementing products. Revisit only if the custom derivation set outgrows a handful. `prd.md` §5.4. |
| Any vendor cloud, marketplace, partner programme or first-party AI service | I6. Permanent. |
| A managed queue or managed Postgres as the only path | On-prem deployment is a requirement, not a variant. |

## Adding a dependency

Adding one is a decision record, not a task-level choice. The question asked first is always
`prd.md` §6's: **is this already inherited, and are we about to write something the ecosystem
ships?** Replacing our code with an inherited component is always the preferred direction of
change.
