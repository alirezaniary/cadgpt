# Stack

What we use, and why. Adding a dependency is a decision — log it in `docs/decisions.md`.

## Layout

```
packages/engine/     cadgpt_engine   Deterministic checking. No framework. No network.
packages/regulations/ cadgpt_regulations  Corpus inventory, provenance, and publication gates.
services/api/        cadgpt          Django + DRF + Celery, six apps.
services/web/        @cadgpt/web     React + Vite + TanStack Query, TypeScript.
deploy/                              Dockerfiles and the compose stack.
```

One uv workspace, one lockfile. The service depends on the engine as a workspace member,
so it resolves locally and is never published.

## Regulation corpus

| Concern | Choice |
| --- | --- |
| Contract validation | JSON Schema Draft 2020-12 through `jsonschema>=4.23,<5.0` |
| Official HTTP acquisition | `httpx>=0.28.1,<0.29`; streamed bodies, manual redirects, monotonic total deadlines, no environment proxies |
| PDF identity | SHA-256 over the immutable source bytes, pinned in the curated catalog |
| Media detection | Content signatures; filename extensions are not trusted |
| PDF page count | Poppler `pdfinfo`, invoked directly without a shell |
| Failure policy | Complete acquisition/inventory with terminal quarantine; publication fails closed |

The package contains no OCR, inference, database, or service integration. Acquisition is
limited to exact catalogued origins, validates every redirect before following it, disables
proxy environment variables, and stores raw metadata, projections, rejected bodies, and PDFs
under attested paths. Its catalog, receipt, and manifest schemas reject unknown fields, and
generated JSON contains no wall-clock value, so identical inputs produce byte-identical data.

## Evaluation — inherited, pinned, proven working

| Concern | Component |
| --- | --- |
| IFC parse and query | `ifcopenshell==0.8.5` |
| IDS rule evaluation | `ifctester==0.8.5` |
| Report generation | `ifctester.reporter` — `Html`, `Json`, `Bcf`, `Ods`, `Console`, `Txt` |
| Rule format | buildingSMART IDS 1.0 — never forked, never hand-extended |

The reporters matter: the report this product returns is generated upstream. We normalize
its output into three-valued results and present it; we do not author it.

## Service

| Concern | Choice |
| --- | --- |
| Framework | Django 5 + Django REST Framework |
| Database | PostgreSQL 17 |
| Background work | Celery over Redis, one worker per queue group |
| Authentication | `djangorestframework-simplejwt`; refresh token in an httpOnly cookie |
| Filtering | `django-filter`, always through a `FilterSet` |
| API schema | `drf-spectacular`; the frontend's types are generated from it |
| File storage | `FileField` on local disk; `django-storages` S3 in production |
| Logging | `structlog`, JSON in production, with request, tenant and user on every line |
| Config | `django-environ`, split settings per environment, no secret defaults |

## Frontend

| Concern | Choice |
| --- | --- |
| Build | Vite 6, TypeScript in strict mode with `noUncheckedIndexedAccess` |
| Server state | TanStack Query — polling stops when a run reaches a terminal state |
| Client state | React state and one context. No Redux; there is very little client state |
| Localization | i18next, with `dir` driven by the active language |
| Styling | Plain CSS in logical properties, so the whole layout mirrors under RTL |
| Types | Generated from the server's OpenAPI document (`make schema`) |

No SSR: everything sits behind a login, and the web overlay this grows into
(`prd.md` 5.8) is a WASM and WebGL viewer that has to run client-side anyway.

## Enforcement

| Concern | Tool |
| --- | --- |
| Lint and format | `ruff` |
| Types | `mypy --strict`, with `django-stubs` and `djangorestframework-stubs` |
| Tests | `pytest` + `pytest-django` |
| Architecture | `import-linter` — five contracts in `pyproject.toml` |
| Frontend | `eslint` + `tsc --noEmit` + a production build |

One command: `make verify`.

The import contracts are the load-bearing ones:

1. **I1** — no inference client, web framework or network reaches `cadgpt_engine`.
2. The engine knows nothing about the service that hosts it.
3. Django apps are layered: `review > rulepack > media > tenancy > account > base`.
4. Services never import the transport layer that called them.
5. Models never import services.

## Test data

Real IFC models and real IDS rule files are freely available and should be used instead of
synthetic fixtures wherever possible:

- **IDS rules** — `buildingSMART/IDS` (branch `development`). `Documentation/Examples/` has
  12 real-world sets including national standards; `Documentation/.../TestCases/` has 346
  more covering every facet type.
- **IFC models** — `buildingsmart-community/Community-Sample-Test-Files`. Files are Git LFS
  pointers; fetch through `media.githubusercontent.com/media/...`, not `raw.`.
  `Duplex_A_20110907.ifc` (2.3MB) is a good fast fixture; `IFC Schependomlaan.ifc` (47MB) is
  the realistic load case.

Schependomlaan pinned, for when this becomes a fetched CI fixture rather than a manual
download: upstream `jakob-beetz/DataSetSchependomlaan` commit
`8e3f95ec7157004d906afbaf3cf2566bba65016f`, path `Design model IFC/IFC Schependomlaan.ifc`,
SHA-256 `2c3565ca1904f2aa61adab92024cf3755b2c5b21a498144d3094d7cb58cebec7`, 49,286,967 bytes.
It is IFC2X3 — useful, because rule sets written for IFC4 behave differently against it.

## Deliberately not chosen

| Rejected | Why |
| --- | --- |
| A custom internal schema with an IFC mapping | Large custom surface for no gain; IFC is the interchange format. |
| BIMserver | Its IDS checking is weaker than `ifctester` and it adds a service. |
| PostgreSQL row-level security | One migration set and a structural test instead. Reopens on a compliance requirement — see `docs/decisions.md`. |
| Schema-per-tenant | Per-tenant migrations and connection routing, for isolation a scoped queryset already gives. |
| Next.js | A second server tier in front of an API-only backend, for SSR nothing here needs. |
| Redux | There is almost no client state; server state belongs to TanStack Query. |
| Poetry | The workspace was already on uv, which is what a local-package monorepo wants. |
| Findings as database rows | 3,623 findings in one specification is a document, not a table. Returns with dispositions. |
| Any vendor cloud, marketplace, or partner programme | Permanent (I6). Public scripting interfaces and local install only. |
| A managed-only database or queue | On-prem deployment is a requirement, not a variant. |
