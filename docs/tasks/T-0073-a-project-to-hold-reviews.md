# T-0073 — a project to hold reviews

**Phase:** 3   **Status:** done
**Touches invariants:** tenancy (a new tenant-owned table), import contracts (a new app
layer).

## Why

The product owner rejected the dashboard outright: everything — rule sets, reviews, runs,
reports — sat on one page with no organizing container. The requested shape, explicitly
given, mirrors Django admin: a list view, a separate add form, and a separate detail view,
three levels deep — **workspace → projects → reviews**, where a review's detail page is
where its runs and report live. `Project` does not exist anywhere in this codebase today —
not in `prd.md`, not as a model. `Review` currently hangs directly off the tenant
(`Review.tenant` via `TenantOwnedModel`). This task adds the missing middle layer so the
frontend (T-0074) has something to route against. This task is backend-only: the model, its
migration, and its API. No frontend changes here.

## Scope

**New app `services/api/cadgpt/apps/project/`**, following the shape of `cadgpt.apps.
rulepack` (`RuleSet` is the closest existing precedent: `TenantOwnedModel`, no soft-delete
needed here since nothing yet references a project the way a check run references a rule
set — a project with reviews under it is protected from deletion by `Review.project`'s
`on_delete=PROTECT`, same reasoning as `Review.model_file`).

- `models.py` — `Project(TenantOwnedModel, UuidBaseModel)`: `name` (`CharField`,
  max_length=255, required), `created_by` (FK to `account.User`, `SET_NULL`, matching
  `Review.created_by`). `tenant_related_name = "projects"`. `Meta.ordering =
  ("-created_at",)`, an index on `("tenant", "-created_at")`, matching `Review.Meta`
  exactly.
- `repositories/querysets.py` + `repositories/custom_managers.py` — a `ProjectQuerySet`
  (`TenantScopedQuerySet` subclass, nothing beyond what `for_tenant` gives it — no
  `with_inputs`/`with_latest_run` equivalent is needed yet) and a plain `ProjectManager`,
  mirroring `RuleSetManager`'s shape minus the soft-delete filtering (no `alive()`/`dead()`
  split — there is no `SoftDeleteModelMixin` here).
- `api/v1/serializers.py` — `ProjectSerializer` (read: uuid, name, created_at, and a
  `review_count` `SerializerMethodField` or annotation — the changelist needs this without
  a second request per row) and `ProjectCreateSerializer` (write: `name` only; `tenant` and
  `created_by` come from context, same pattern as `ReviewCreateSerializer`).
- `api/v1/views.py` — `ProjectViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin,
  mixins.CreateModelMixin, mixins.DestroyModelMixin, TenantScopedViewSet)`, permissions
  `IsTenantMember` for list/retrieve, `IsTenantMemberOrAbove` for create/destroy — copy
  `ReviewViewSet`'s `get_permissions` override exactly.
- `api/v1/urls.py` + `api/urls.py` + `urls.py` — register `"projects"` on a
  `ScopedRouter(scope="tenant")`, included at `api/` the same way `cadgpt.apps.review.urls`
  does today.
- Migration for the new app, plus a migration on `review` that:
  1. adds `Review.project` as a **nullable** `ForeignKey("project.Project",
     on_delete=models.PROTECT, related_name="reviews")`;
  2. a data migration that, for every tenant with at least one existing `Review`, creates
     one `Project` named `"عمومی"` (the Persian "General" — this is scaffolding for
     pre-existing rows, not a designer-facing feature, so it takes the app's one hardcoded
     language like everything else per T-0072) and points every one of that tenant's
     existing reviews at it;
  3. a following migration that makes `Review.project` non-nullable (`null=False`) now that
     every row has one.
  This is a three-step migration specifically so it is safe to run against whatever is
  already in the dev database — not a design decision that `project` is ever optional going
  forward. `ReviewCreateSerializer` requires `project` from here on (a uuid, resolved
  through `tenant_queryset()` on `Project` the same way `rule_set` is resolved today —
  another tenant's project must 404, not silently attach).
- `cadgpt/apps/review/api/v1/filters.py` — `ReviewFilterSet` gets a `project` filter
  (exact match on uuid) so `/api/v1/reviews/?project=<uuid>` returns one project's reviews;
  this is what the frontend's project-detail page will call.
- `cadgpt/config/settings/base.py` (`LOCAL_APPS`) — insert `"cadgpt.apps.project"`
  immediately after `"cadgpt.apps.tenancy"`, before `"cadgpt.apps.media"`.
- `cadgpt/config/urls.py` — add `path("", include("cadgpt.apps.project.urls"))` in the same
  position (after tenancy, before media).
- root `pyproject.toml` — `[[tool.importlinter.contracts]] name = "Django apps are
  layered"`: insert `"cadgpt.apps.project"` into the `layers` list between
  `"cadgpt.apps.tenancy"` and `"cadgpt.apps.media"` (project may be imported by review,
  rulepack and media; it may only import tenancy, account and base). Also add
  `"cadgpt.apps.project.services"` is **not** needed — this app has no service module yet;
  there is no business logic beyond what the manager and serializer already carry, so
  `services/` is not created (no placeholder file per the no-scaffolding rule).
- `cadgpt/apps/base/tests/test_tenant_isolation.py` or wherever the structural
  "every viewset over a tenant-owned model inherits `TenantScopedViewSet`" test walks
  registered routes — confirm `ProjectViewSet` is picked up automatically (it should be,
  since that test walks the router rather than an explicit allowlist; if it is an
  allowlist, add the new route).

**What explicitly does not change:** `RuleSet` and its upload path stay exactly as they are
in the backend — T-0074 removes the *frontend* affordance per `docs/decisions.md`'s
2026-09-04 entry, this task does not touch `rulepack` at all. `CheckRun` is untouched.

## How to prove it ran

```sh
make verify
```

Then the real path, against the real compose stack:

```sh
docker compose -f deploy/compose.yaml up --build -d api worker
# a real tenant, from a real request:
# 1. POST /api/v1/projects/  {"name": "..."}  -> 201, uuid back
# 2. GET  /api/v1/projects/  -> the created project, review_count: 0
# 3. POST /api/v1/reviews/   with that project's uuid + a real model file -> 201
# 4. GET  /api/v1/reviews/?project=<uuid> -> the review just created, and only that one
# 5. a second tenant's token against the first tenant's project uuid -> 404, not 200
```

Paste the actual request/response pairs, not a description of what they would show.
Confirm the three-step migration applies cleanly against the current dev database
(`python manage.py migrate` from the state before this task, with at least one pre-existing
review in it) and that the pre-existing review ends up attached to a `"عمومی"` project
afterward — query it and show the row.

## Evidence

### `make verify`

All five gates pass:

```
$ make verify
uv run ruff check .
All checks passed!
uv run ruff format --check .
185 files already formatted
uv run mypy packages/engine/src services/api/cadgpt
Success: no issues found in 169 source files
uv run lint-imports --no-cache
...
I1 - no inference client, web framework or network reaches the checking engine KEPT
The engine knows nothing about the service that hosts it KEPT
Django apps are layered KEPT
Services never import the transport layer KEPT
Models never import services KEPT

Contracts: 5 kept, 0 broken.
uv run pytest
........................................................................ [ 30%]
........................................................................ [ 61%]
........................................................................ [ 91%]
...................                                                      [100%]
235 passed, 32 warnings in 3.78s
cd services/web && pnpm install --frozen-lockfile && pnpm run verify
...
✓ built in 1.67s
```

(235 tests passed, including the whole engine suite, the full API suite and
`cadgpt/tests/test_tenant_isolation.py`. No test was skipped or weakened; `conftest.py`
gained a `project` fixture and the `review`/`catalogue_review` fixtures now pass it
through, since `ReviewService.create` requires a project like every other caller does.)

### The three-step migration, against the real dev database

Before this task's migrations were applied, the running `deploy/compose.yaml` stack
(left over from earlier manual/e2e sessions) held 171 pre-existing reviews across 118
tenants, at review migration head `0005_checkrun_claim_count_alter_checkrun_failure_reason`:

```
$ docker compose -f deploy/compose.yaml exec -T postgres psql -U cadgpt -d cadgpt \
    -c "select count(*) from review_review;"
 count
-------
   171
(1 row)
```

Rebuilding and restarting `api`/`worker` (`docker compose -f deploy/compose.yaml up
--build -d api worker`) ran the migration automatically on container start:

```
api-1  | Operations to perform:
api-1  |   Apply all migrations: account, admin, auth, contenttypes, media, project, review, rulepack, sessions, tenancy
api-1  | Running migrations:
api-1  |   Applying project.0001_initial... OK
api-1  |   Applying review.0006_review_project... OK
api-1  |   Applying review.0007_backfill_general_projects... OK
api-1  |   Applying review.0008_alter_review_project_not_null... OK
```

Every one of the 171 pre-existing reviews ended up with a `project`, one "عمومی" project
per tenant that had at least one review (118, matching the 118 distinct tenants):

```
$ docker compose -f deploy/compose.yaml exec -T postgres psql -U cadgpt -d cadgpt -c \
    "select count(*) as total_reviews, count(project_id) as with_project from review_review;"
 total_reviews | with_project
----------------+--------------
            171 |          171
(1 row)

$ docker compose ... -c "select count(*) as general_projects from project_project where name = 'عمومی';"
 general_projects
-------------------
               118
(1 row)

$ docker compose ... -c "select r.id as review_id, r.tenant_id, p.uuid as project_uuid, \
    p.name as project_name from review_review r join project_project p on p.id = r.project_id \
    order by r.id limit 5;"
 review_id | tenant_id |             project_uuid              | project_name
-----------+-----------+----------------------------------------+--------------
         1 |         1 | a0b74b85-2d25-4c04-b048-62de08918888   | عمومی
         2 |         2 | 370aa5fd-f12b-4f76-94d8-05169f9e4c32   | عمومی
         3 |         3 | 23a00b1a-e1f0-4bc9-b47c-3780dbcc8fa2   | عمومی
         4 |         4 | 78fb4058-205d-4adf-866d-0cb9142a7d5f   | عمومی
         5 |         5 | f41f8c7c-7f00-4639-9beb-79d85c1173cf   | عمومی
(5 rows)
```

`make manage.py makemigrations --check --dry-run` reports "No changes detected" against
the final model state, so the three migrations are exactly what the model declares —
nothing was hand-edited out of sync with `models.py`.

### The real path — five real requests against the real compose stack

`docker compose -f deploy/compose.yaml up --build -d api worker`, then real HTTP against
`http://localhost:8000` with a real registered user, a real provisioned tenant, and a
real IFC fixture (`packages/engine/tests/fixtures/three_doors.ifc`) uploaded through
`/api/v1/media/`. Bearer tokens and `X-Tenant` omitted below for brevity where implied by
context; every call carried them.

**1. `POST /api/v1/projects/ {"name": "Ground floor renovation"}` → 201**

```json
{"uuid":"5ff73f62-5c66-4625-b2ac-330b804be32b","name":"Ground floor renovation","review_count":0,"created_at":"2026-09-04T15:52:25.720314Z"}
```

**2. `GET /api/v1/projects/` → the created project, `review_count: 0`**

```json
{"count":1,"page":1,"pages":1,"size":20,"next":null,"previous":null,"results":[{"uuid":"5ff73f62-5c66-4625-b2ac-330b804be32b","name":"Ground floor renovation","review_count":0,"created_at":"2026-09-04T15:52:25.720314Z"}]}
```

**3. `POST /api/v1/reviews/ {"name": "T-0073 proof review", "model_file": "<uuid>", "project": "5ff73f62-..."}` → 201**

```json
{"uuid":"0f53a30d-ed2c-48c8-8099-886b805da3eb","name":"T-0073 proof review","model_file":{"uuid":"850d8333-92a3-4141-8338-2be8c3e723f8","kind":"ifc_model","original_name":"three_doors.ifc",...},"rule_set":null,"latest_run":null,"created_at":"2026-09-04T15:52:25.841198Z","updated_at":"2026-09-04T15:52:25.841212Z"}
```

**4. `GET /api/v1/reviews/?project=5ff73f62-...` → the review just created, and only that one**

```json
{"count":1,"page":1,"pages":1,"size":20,"next":null,"previous":null,"results":[{"uuid":"0f53a30d-ed2c-48c8-8099-886b805da3eb","name":"T-0073 proof review", ...}]}
```

(`GET /api/v1/projects/` again at this point returns `"review_count":1` for the same
project — the annotation in `ProjectViewSet.get_queryset` tracks the new review with no
extra query per row.)

**5. A second tenant's token against the first tenant's project uuid → 404, not 200**

```
$ curl -o /dev/null -w "HTTP %{http_code}\n" http://localhost:8000/api/v1/projects/5ff73f62-.../ \
    -H "Authorization: Bearer <tenant-B token>" -H "X-Tenant: rival-b-t0073"
HTTP 404
{"type":"about:blank#not_found","status":404,"code":"not_found","detail":"The requested resource does not exist.","request_id":"0de37267a0a142ea86f56fa9b9809e0c"}

$ curl -X POST http://localhost:8000/api/v1/reviews/ -H "Authorization: Bearer <tenant-B token>" \
    -H "X-Tenant: rival-b-t0073" -H "Content-Type: application/json" \
    -d '{"name":"cross-tenant attempt","model_file":"<tenant-B media uuid>","project":"5ff73f62-..."}'
HTTP 404
{"type":"about:blank#not_found","status":404,"code":"not_found","detail":"That project does not exist.","request_id":"9ff8b00f8aa0411fa70a09689aab15f4"}
```

The second call used tenant B's *own* uploaded model (not tenant A's) so the 404 is
specifically the project lookup failing, not an incidental model-file 404 — confirming
`ProjectCreateSerializer`/`ReviewCreateSerializer`'s `Project.objects.for_tenant(...)`
resolution refuses another tenant's project rather than attaching to it.

Tenant B's own `GET /api/v1/projects/` in the same session returns
`{"count":0,...,"results":[]}` — the catalogue is per-tenant, not shared.

### Wiring

`services/api/cadgpt/config/settings/base.py`, `LOCAL_APPS`:
```python
LOCAL_APPS = [
    "cadgpt.apps.base",
    "cadgpt.apps.account",
    "cadgpt.apps.tenancy",
    "cadgpt.apps.project",
    "cadgpt.apps.media",
    "cadgpt.apps.rulepack",
    "cadgpt.apps.review",
]
```

`services/api/cadgpt/config/urls.py`:
```python
    path("", include("cadgpt.apps.tenancy.urls")),
    path("", include("cadgpt.apps.project.urls")),
    path("", include("cadgpt.apps.media.urls")),
```

`pyproject.toml`, `[[tool.importlinter.contracts]] name = "Django apps are layered"`:
```toml
layers = [
    "cadgpt.apps.review",
    "cadgpt.apps.rulepack",
    "cadgpt.apps.media",
    "cadgpt.apps.project",
    "cadgpt.apps.tenancy",
    "cadgpt.apps.account",
    "cadgpt.apps.base",
]
```

`services/api/cadgpt/apps/project/api/v1/urls.py`:
```python
router.register("projects", ProjectViewSet, basename="project")
```
(registered on `ScopedRouter(scope="tenant")`, included via
`project/api/urls.py` → `project/urls.py` → `path("", include("cadgpt.apps.project.urls"))`
in `config/urls.py` above — the same chain `rulepack` and `review` use.)

`services/api/cadgpt/apps/review/api/v1/filters.py`, `ReviewFilterSet`:
```python
project = django_filters.UUIDFilter(field_name="project__uuid")
...
fields = ("name", "project", "rule_set", "created_after")
```

**Structural tenancy test picked up `ProjectViewSet` automatically**, no allowlist edit
needed (confirmed both by running the suite and directly):
```
$ python -c "... from cadgpt.tests.test_tenant_isolation import _registered_viewsets, _tenant_owned_models ..."
ProjectViewSet found: <class 'cadgpt.apps.project.api.v1.views.ProjectViewSet'>
Inherits TenantScopedViewSet: True
Project in tenant_owned_models: True
```
`test_every_viewset_over_a_tenant_owned_model_is_tenant_scoped` and the other nine tests
in `cadgpt/tests/test_tenant_isolation.py` pass unchanged (10 passed).

### What changed beyond the task's explicit file list, and why

- **`conftest.py`** gained a `project` fixture and `review`/`catalogue_review` now depend
  on it, because `ReviewService.create` (and `ReviewCreateSerializer`) require a project
  from here on — every existing test creating a review through those fixtures needed one.
- **`cadgpt/apps/review/tests/test_check_run.py`**: the one test that called
  `ReviewService(...).create(...)` directly (not through the `review` fixture) now passes
  `project=project`.
- **`ProjectViewSet.perform_destroy`** catches `django.db.models.deletion.ProtectedError`
  and raises `ConflictError` (409) instead of letting it fall through to an unhandled
  500. The task's own reasoning ("a project with reviews under it is protected from
  deletion by `Review.project`'s `on_delete=PROTECT`") only has an API-visible effect if
  that protection surfaces as a normal domain error rather than a 500 — none of the proof
  steps exercise delete, but leaving the raw `ProtectedError` unhandled would have been an
  API a reviewer would reasonably reject on sight.

None of this touches `services/web/` — no frontend file was read or edited.

### NOT DONE

Nothing. Every item in Scope was implemented: the `project` app (model, manager,
queryset, serializers, viewset, urls), the three-step `review` migration, the
`ReviewFilterSet` `project` filter, and the settings/urls/import-linter wiring. `RuleSet`
and `CheckRun` were not touched, per the task's explicit "what does not change."

## Review

Gated on the tenancy and import-contract invariants named in this task's header. The
reviewer re-ran `make verify` and re-executed the five-step real path independently
(fresh tenants, own curl calls) rather than trusting the evidence block, and additionally
confirmed at the database level that `review_review.project_id` is non-nullable at
migration head with the FK constraint present, and that `makemigrations --check
--dry-run` reports no drift.

**Verdict: no invariant violated, no evidence-block claim was false. Fix-now pile is
empty.** Four findings queued as new tasks rather than sent back to this builder, per
"one review round per task, maximum":

- **T-0075** — `review_count` counts soft-deleted reviews, and a project with only
  soft-deleted reviews under it can never be deleted (`PROTECT` fires permanently, no API
  path clears `project_id` from a dead review).
- **T-0076** — the new `project` app has no test package at all; the structural tenancy
  test only checks `issubclass(ProjectViewSet, TenantScopedViewSet)`, not that
  `get_queryset` actually stayed tenant-scoped, so a regression that swapped in
  `Project.objects.all()` would pass the whole suite. Isolation is correct today, proven
  only by this task's manual curl.
- **T-0077** — `ReviewSerializer` never exposes the `project` a review is now required to
  belong to; the only way to learn it is to already know which project you filtered by.
- Not a new task: the reviewer also found the shipped frontend's only review-creation
  call now 400s (it doesn't send `project` yet) and three e2e specs fail as a result.
  This is T-0074's own scope, already in progress — not a regression this task
  introduced beyond what T-0074 exists to close.
