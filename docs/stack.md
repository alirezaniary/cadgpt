# Stack

What we use, and why. Adding a dependency is a decision — log it in `docs/decisions.md`.

## Evaluation — inherited, pinned, proven working

| Concern | Component |
| --- | --- |
| IFC parse and query | `ifcopenshell==0.8.5` |
| IDS rule evaluation | `ifctester==0.8.5` |
| Report generation | `ifctester.reporter` — `Html`, `Json`, `Bcf`, `Ods`, `Console`, `Txt` |
| Rule format | buildingSMART IDS 1.0 — never forked, never hand-extended |

The reporters matter: the report the product returns is generated upstream. We normalize its
output into three-valued results and present it; we do not author it.

## Web

| Concern | Choice |
| --- | --- |
| Backend | Django + Django REST Framework |
| Templates | Server-rendered first; React/Vite only when templates genuinely fall short |
| Database | SQLite for the MVP, PostgreSQL when there is real concurrency |
| File storage | Local disk via Django `FileField`; S3-compatible only at deployment |
| Evaluation | Synchronous in-request — 47MB completes in 9.9s |

## Enforcement

| Concern | Tool |
| --- | --- |
| Lint and format | `ruff` |
| Types | `mypy --strict` |
| Tests | `pytest` |
| I1 — no inference in the engine | `import-linter` contract in `pyproject.toml` |

One command: `make verify`.

## Test data

Real IFC models and real IDS rule files are freely available and should be used instead of
synthetic fixtures wherever possible:

- **IDS rules** — `buildingSMART/IDS` (branch `development`). `Documentation/Examples/` has 12
  real-world sets including national standards; `Documentation/.../TestCases/` has 346 more
  covering every facet type.
- **IFC models** — `buildingsmart-community/Community-Sample-Test-Files`. Files are Git LFS
  pointers; fetch through `media.githubusercontent.com/media/...`, not `raw.`.
  `Duplex_A_20110907.ifc` (2.3MB) is a good fast fixture; `IFC Schependomlaan.ifc` (47MB) is the
  realistic load case.

## Deliberately not chosen

| Rejected | Why |
| --- | --- |
| A custom internal schema with an IFC mapping | Large custom surface for no gain; IFC is the interchange format. |
| BIMserver | Its IDS checking is weaker than `ifctester` and it adds a service. |
| Celery / RabbitMQ / Redis in the MVP | Measurement says evaluation fits in a request. Revisit with numbers, not anticipation. |
| Any vendor cloud, marketplace, or partner programme | Permanent (I6). Public scripting interfaces and local install only. |
| A managed-only database or queue | On-prem deployment is a requirement, not a variant. |
