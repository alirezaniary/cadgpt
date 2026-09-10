# T-0077 — a review that doesn't say whose project it is

**Phase:** 3   **Status:** built
**Touches invariants:** none.

## Why

Found by T-0073's review. `Review.project` is now required, but `ReviewSerializer`
(`cadgpt/apps/review/api/v1/serializers.py`) never gained a `project` field — confirmed
live, the 201 body from a review creation carries `model_file`, `rule_set`, `latest_run`,
no `project`. The only way to learn which project a review belongs to is to already know
it, by having filtered `/api/v1/reviews/?project=<uuid>` to find it. T-0074's
`/projects/:uuid/reviews/:uuid` detail route can get away with trusting the URL's own
`:uuid` segment, but any other consumer of `GET /api/v1/reviews/<uuid>/` — a future admin
view, a script, a second frontend surface — cannot tell a review's project from the
resource itself.

## Scope

- `cadgpt/apps/review/api/v1/serializers.py`, `ReviewSerializer` — add a `project` field.
  Match the existing pattern for a related-object reference on this serializer (check
  whether `rule_set` is a bare uuid, a nested object, or a `SerializerMethodField` today,
  and follow that shape rather than inventing a new convention for one field).
- Confirm `ReviewFilterSet`'s existing `project` filter and this new output field agree on
  what they call the value (uuid vs nested), so a client can round-trip
  `?project=<value>` using the value it just read off a review.

## How to prove it ran

Real path: `GET /api/v1/reviews/<uuid>/` against the compose stack, showing the response
body now includes the review's project. `make verify` with any serializer test this
touches updated.

## Evidence

**Change.** `ReviewSerializer` (`services/api/cadgpt/apps/review/api/v1/serializers.py`)
gained `project = ProjectSerializer(read_only=True)`, in `Meta.fields` right after `name`.
`rule_set` was already `RuleSetSerializer(read_only=True)` (a full nested object, not a
bare uuid or a `SerializerMethodField`), so `project` follows the same shape rather than
inventing a fourth convention for one field. `ReviewQuerySet.with_inputs()`
(`services/api/cadgpt/apps/review/repositories/querysets.py`) gained `"project"` in its
`select_related`, alongside the existing `model_file`/`rule_set` entries, so fetching the
field this adds does not cost a query per row the way it would have without it.

`ReviewFilterSet.project` (`services/api/cadgpt/apps/review/api/v1/filters.py:11`) was
already `django_filters.UUIDFilter(field_name="project__uuid")` — takes a bare uuid. The
new output field is nested (`{"uuid": ..., "name": ..., "review_count": ..., "created_at":
...}`), so a client reads `.project.uuid` off a review and passes it straight to
`?project=<uuid>`. Verified live below: the uuid read off the GET response round-trips
through the list filter and returns exactly that review. This is the same asymmetry
`rule_set` already has (nested output, bare-uuid filter) — not a new inconsistency
introduced here.

**`make verify`:** all gates pass — ruff, `mypy --strict` (170 source files, no issues),
all 5 import-linter contracts kept, 246 pytest tests passed, frontend lint/typecheck/build
and the Storybook workbench build all succeeded. (The sandbox's `services/api` venv had no
`msgfmt` on `PATH` for `compile-messages`; used a previously-extracted local gettext
binary — `LD_LIBRARY_PATH`/`PATH` pointed at it for this run only, nothing in the repo or
CI config changed.) Full run:

```
uv run ruff check .            -> All checks passed!
uv run ruff format --check .   -> 187 files already formatted
uv run mypy packages/engine/src services/api/cadgpt
                                -> Success: no issues found in 170 source files
uv run lint-imports --no-cache -> Contracts: 5 kept, 0 broken.
manage.py compilemessages      -> already compiled and up to date
uv run pytest                  -> 246 passed, 32 warnings in 4.77s
pnpm run lint / typecheck / build / build-workbench
                                -> all succeeded (vite build + storybook build clean)
```

**Real path.** Rebuilt the `cadgpt-api` image (`docker build --network=host -f
deploy/docker/api.Dockerfile ...` — the sandbox's Docker build network could not reach the
loopback-bound host proxy the compose build normally uses, so `--network=host` was used
for this one rebuild only; nothing about the app or its config changed) and recreated
`api`, `worker`, `beat` from it via `docker compose -f deploy/compose.yaml up -d --no-build
api worker beat`. Logged in as an existing tenant member
(`t0081-1789039546@cadgpt.test`, tenant `t0081-1789039546`) to get a real JWT, then:

```
$ curl -s http://localhost:8000/api/v1/reviews/ff1a2e67-ed4b-4158-bde9-9ffa7aebe453/ \
    -H "Authorization: Bearer $TOKEN" -H "X-Tenant: t0081-1789039546"
{
    "uuid": "ff1a2e67-ed4b-4158-bde9-9ffa7aebe453",
    "name": "T0081 Review — RESOURCE_EXHAUSTED proof",
    "project": {
        "uuid": "1dca28bb-ce4c-47b8-9f77-911f875cb27a",
        "name": "T0081 Project",
        "review_count": 1,
        "created_at": "2026-09-10T11:26:06.413047Z"
    },
    "model_file": { "uuid": "098c895d-2b1b-4cad-9509-390f177a2fb1", ... },
    "rule_set": null,
    "latest_run": { "uuid": "fea044eb-4283-457a-bf4b-bcc3667ab9c4", ... },
    "created_at": "2026-09-10T11:26:18.237368Z",
    "updated_at": "2026-09-10T11:26:18.237419Z"
}
```

The 200 body now carries `project` — absent before this change per the task's own finding
(the `Why` section above, confirmed live at the time T-0077 was written). Round-trip
proof, same session, using the `uuid` just read off the response:

```
$ curl -s "http://localhost:8000/api/v1/reviews/?project=1dca28bb-ce4c-47b8-9f77-911f875cb27a" \
    -H "Authorization: Bearer $TOKEN" -H "X-Tenant: t0081-1789039546"
{ "count": 1, ..., "results": [ { "uuid": "ff1a2e67-ed4b-4158-bde9-9ffa7aebe453", "project": {"uuid": "1dca28bb-ce4c-47b8-9f77-911f875cb27a", ...}, ... } ] }
```

The filtered list returns exactly the one review the uuid was read off, confirming
`ReviewFilterSet.project` and `ReviewSerializer.project` agree on what they call the value.
(The test password set on the tenant member to obtain the JWT was cleared back to
unusable immediately after, via `set_unusable_password()` — no lasting change to that
account.)

**Wiring.** No new route — the field rides the existing registration in
`services/api/cadgpt/apps/review/api/v1/urls.py`:

```python
router.register("reviews", ReviewViewSet, basename="review")
```

which is the router actually mounted under `/api/v1/` and the one the GET above hit.

**NOT DONE:** nothing. Scope was exactly the serializer field and the filter-agreement
check; both are done and proven above. One thing noted but deliberately left alone as
out of scope: `ProjectSerializer.review_count` falls back to a live `COUNT` query per
instance when the `Project` wasn't annotated by `ProjectViewSet.get_queryset` — true for
every `Review.project` nested through this change, so a *list* of many reviews now costs
one extra query per row for that one field. The single-object real path above shows this
correctly (one extra query, harmless), but a large reviews list would not have a fixed
query count the way `with_inputs()`'s other fields do. Not fixed here because it is a
wider change than "add a project field" — it would mean either annotating review counts
onto `Review.project` via a subquery, or introducing a project field shape that isn't
`ProjectSerializer` for this one caller alone (contradicts the task's instruction to reuse
the existing shape rather than invent a new one). Flagging it for the coordinator/judge
rather than deciding it here.

## Review
