# CADGPT

Upload an IFC model and an IDS rule set; get back what passes, what fails, and **what could
not be determined**.

That third value is the point. `ifctester` reports "the attribute is missing" and "the
attribute violates the rule" both as a failure. On a real model and a real rule set that is
the difference between telling an architect they have 113 code violations and telling them
they have 12 violations and 101 unknowns. `INDETERMINATE` is never counted as a pass — not
in a summary, a filter, or an API response.

The rules are data. No building code is compiled into the engine, so a jurisdiction is a set
of loaded IDS files and nothing else.

`prd.md` is the product. `CLAUDE.md` is the engineering rules. `docs/plan.md` is the route,
`docs/decisions.md` is why things are the way they are, `docs/stack.md` is what we use.

## Layout

```
packages/engine/     cadgpt_engine   Deterministic checking. No framework, no network.
services/api/        cadgpt          Django + DRF + Celery. Six apps, layered.
services/web/        @cadgpt/web     React + Vite + TanStack Query. RTL-native.
deploy/                              Dockerfiles and the compose stack.
```

The boundaries between these are import contracts checked by `make verify`, not
conventions. Most importantly: nothing in the engine may import Django, an HTTP client, or
an inference client. A model never decides whether a building complies.

## Run it

```sh
make up          # Postgres, Redis, the API, a worker, and the SPA behind nginx
```

- SPA — http://localhost:8080
- API — http://localhost:8000/api/v1/
- API docs — http://localhost:8000/api/docs/
- Readiness — http://localhost:8000/readyz

Postgres is published on **5433** and Redis on **6380**, so the stack does not collide with
either service already installed on your machine.

## Develop

```sh
make install     # uv sync + pnpm install
make migrate
make run         # API on :8000
make worker      # a Celery worker on the checks queue
cd services/web && pnpm dev   # SPA on :5173, proxying /api to :8000
```

Copy `.env.example` to `.env` first.

## Verify

```sh
make verify      # ruff, mypy --strict, import contracts, pytest, and the frontend build
```

`make help` lists everything.

## The engine on its own

The checking engine has no dependency on any of the above and runs from a terminal:

```sh
uv run cadgpt-check model.ifc rules.ids
uv run cadgpt-check model.ifc rules.ids --json > report.json
```
