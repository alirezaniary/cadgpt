# T-0076 — project isolation proven by a test, not a curl in a task file

**Phase:** 3   **Status:** open
**Touches invariants:** tenancy — this task adds the test coverage the invariant's own
rule requires ("a structural test fails the build if a viewset escapes the scoped base
class"), for a model that currently has none.

## Why

Found by T-0073's review. `cadgpt.apps.project` shipped with no `tests/` package at all —
the only app in this codebase without one. The structural isolation test
(`cadgpt/tests/test_tenant_isolation.py::test_every_viewset_over_a_tenant_owned_model_is_
tenant_scoped`) only asserts `issubclass(ProjectViewSet, TenantScopedViewSet)`; it does
not exercise `get_queryset`. `ProjectViewSet` overrides `get_queryset`
(`cadgpt/apps/project/api/v1/views.py:42-45`), and the reviewer confirmed by direct edit
that replacing `self.tenant_queryset()` with `Project.objects.all()` there still passes
all 235 tests, including every isolation test. Today's isolation is real — T-0073's
review reproduced the cross-tenant 404s live — but it is proven only by a curl sequence
quoted in a task file, which the next person to touch `project/api/v1/views.py` will
never see.

## Scope

- `cadgpt/apps/project/tests/__init__.py`, `test_project.py` (or whatever this repo's
  convention names it — match `cadgpt/apps/rulepack/tests/` or `cadgpt/apps/review/
  tests/test_check_run.py`'s naming): behavioural tests for `Project` —
  create/list/retrieve/destroy scoped to a tenant, `review_count` accuracy (coordinate
  with T-0075 if it lands first), and a cross-tenant test asserting another tenant's
  project 404s on retrieve and cannot be named on review creation.
- `cadgpt/tests/test_tenant_isolation.py::test_a_tenant_cannot_read_another_tenants_rows`
  (line ~152-168) iterates a fixed list of endpoints
  (`/api/v1/reviews/`, `/api/v1/rule-sets/`, `/api/v1/media/`) — add
  `/api/v1/projects/` to it, so the *general* cross-tenant sweep covers the new model
  the same way it covers every other tenant-owned one, not just a project-specific test.
- Confirm (or add, if missing) an assertion that `ProjectViewSet.get_queryset` actually
  calls `tenant_queryset()`/`for_tenant` — a query-count or mock-based test that would
  fail if a future edit swapped in an unscoped queryset, closing the exact gap the
  reviewer demonstrated.

## How to prove it ran

```sh
make verify
```

with the new tests included, and a demonstration that they actually catch the regression
they're meant to catch: temporarily revert `ProjectViewSet.get_queryset` to
`Project.objects.all()` (the reviewer's own repro), show the new test(s) fail, then
restore the real implementation and show them pass. Paste both runs.

## Evidence

## Review
