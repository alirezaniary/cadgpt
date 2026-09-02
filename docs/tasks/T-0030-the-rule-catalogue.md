# T-0030 — The rule catalogue: rules we ship, belonging to no tenant

**Phase:** 3 — What the first real user needs   **Status:** done
**Touches invariants:** **tenancy**, and the import contracts. **Reviewer-gated**, without
exception — this is the one invariant this repository enforces structurally rather than by
memory, and this task is the first thing that does not fit it.

## Why

Scope settled 2026-09-02 (`docs/decisions.md`, `prd.md` §12): **rules are a catalogue we ship,
not a file the architect uploads.** The user selects by jurisdiction, region and version, and
that selection becomes part of the job record. User-uploaded rule sets already work, are not
being removed, and are simply no longer the primary path.

Today the only way rules enter the system is `RuleSet` — a `TenantOwnedModel` holding one
uploaded IDS file. That is the right model for a rule set an office authored. It is the wrong
model for a pack we publish to everyone, and the reason is structural, not stylistic.

## The structural constraint — read this before writing any code

`CLAUDE.md`: *every tenant-owned table carries `tenant`, every read goes through `for_tenant`,
and a structural test fails the build if a viewset escapes the scoped base class. There is no
row-level security behind it.* That test is the whole enforcement mechanism.

A shipped pack belongs to **no tenant**. The tempting move — make `RuleSet.tenant` nullable —
puts a nullable column at the centre of that invariant and turns every `for_tenant` call site
into something a reader has to reason about instead of trust. **It is refused** (`docs/plan.md`,
Phase 3). The catalogue is a **separate model**, so `for_tenant` stays total and there is no
exception to hold in your head.

That decision creates the real problem this task has to solve honestly: **a global catalogue
needs a viewset that is deliberately not tenant-scoped**, and the structural test exists
precisely to fail that. Do not weaken the test, do not add a blanket exemption, and do not
special-case by class name in a way that would also let a genuinely tenant-owned viewset
through. What is needed is an explicit, narrow, *declared* category — a viewset that serves a
model owning no tenant data at all — such that the test still fails for anything holding tenant
rows. **If you cannot do that without weakening the guarantee, stop and say so in the task file
rather than shipping a hole.** That answer is an acceptable outcome of this task; a quiet bypass
is not.

## Scope

**Changes**

- `services/api/cadgpt/apps/rulepack/models.py` — a `RulePack` model beside `RuleSet`. **Not**
  `TenantOwnedModel`. It carries at minimum: a name, the IDS source file, jurisdiction, region,
  version, and a **source citation** — where this pack came from and who published it, because
  `prd.md` §5.7 requires every finding to carry attribution, and a pack we ship is asserting
  something under our name. Reuse `RuleSet`'s existing parsed-at-upload fields
  (`title`, `author`, `version`, `specification_count`) where they mean the same thing rather
  than inventing parallel names.
- A migration.
- Read-only API to list and retrieve packs, filterable by jurisdiction, region and version.
  Every tenant sees the same catalogue; no tenant can write to it.
- **A seeding path** — a management command that loads packs from IDS files on disk and is
  **idempotent**, so re-running it does not duplicate rows and does not silently overwrite a
  pack a run already cites. `CLAUDE.md`: every background task is idempotent; a seeder is held
  to the same standard.
- Tests, including a structural one asserting that no tenant can reach another tenant's data
  through the new surface, and that the catalogue is readable by all.

**What explicitly does not change**

- `RuleSet` — it stays exactly as it is, tenant-owned, and user upload keeps working. This task
  adds a path beside it; it does not migrate, deprecate or touch the existing one.
- **No rule content.** This loop builds the store, the metadata, the selection surface and the
  seeding path. The product owner authors the packs — Iranian building code first, then EU and
  US — in a separate thread. Seed with whatever public IDS is already in the repository's
  fixtures so the path is exercised; **do not author building code**, and do not invent
  jurisdictions, region codes or version strings for packs that do not exist.
- Selection at check time is **T-0031**, not this task. Build the store; do not wire it into
  the run yet.
- No clause records, no YAML compilation, no ratification pipeline — those are Phase 4
  (`prd.md` §5.5).

## How to prove it ran

`make verify` — and the **5 import contracts must still be kept**; a new model reaching across
a layer is exactly what they are there to catch.

Then the real path, against the running stack, not a test client:

```sh
make up
# seed, twice, to prove idempotence
docker compose -f deploy/compose.yaml exec api python manage.py <the seed command>
docker compose -f deploy/compose.yaml exec api python manage.py <the seed command>
```

The evidence must show:

1. Both seed runs' output, and a row count after each proving the second created nothing.
2. A real HTTP request against the running API listing the catalogue, with the response body
   pasted, and the same request filtered by jurisdiction.
3. **Two tenants, one catalogue**: the same request authenticated as two different tenants
   returning the same packs — and a write attempt against the catalogue being refused.
4. **Wiring**: the migration at head (`showmigrations` output), the route registered in the
   router quoted from the file, and the management command discoverable by `manage.py help`.
5. How you satisfied the structural viewset test without weakening it — quote the test and the
   declaration that makes the catalogue viewset legal under it.

## Evidence

### `make verify` — green, all 5 import contracts kept

```
$ make verify
uv run ruff check .
All checks passed!
uv run ruff format --check .
161 files already formatted
uv run mypy packages/engine/src services/api/cadgpt
Success: no issues found in 147 source files
uv run lint-imports --no-cache
---------
Contracts
---------
Analyzed 189 files, 559 dependencies.
-------------------------------------
I1 - no inference client, web framework or network reaches the checking engine KEPT
The engine knows nothing about the service that hosts it KEPT
Django apps are layered KEPT
Services never import the transport layer KEPT
Models never import services KEPT
Contracts: 5 kept, 0 broken.
uv run pytest
........................................................................ [ 36%]
........................................................................ [ 72%]
.......................................................                  [100%]
199 passed, 20 warnings in 3.04s
cd services/web && pnpm install --frozen-lockfile && pnpm run verify
...
✓ 105 modules transformed.
dist/index.html                   0.40 kB │ gzip:  0.27 kB
dist/assets/index-LZ_wtuT6.css    4.33 kB │ gzip:  1.44 kB
dist/assets/index-C-U3fmoR.js   305.44 kB │ gzip: 95.40 kB │ map: 1,292.06 kB
✓ built in 1.79s
```

### 1. Both seed runs, and a row count after each

Against the running stack (`make up`, then `docker compose -f deploy/compose.yaml up -d --build api worker` to
bake in the new code — no bind mount on `api`/`worker`, so a rebuild is required for the container to see it).

```
$ docker compose -f deploy/compose.yaml exec api python manage.py seed_rule_packs
[info] rule_pack_seeded  jurisdiction=sample name='Accessible door width' region= rule_pack_id=cc0b0297-0ffb-4f6e-b4a1-4b538ece6457 service=RulePackService specifications=1 version=0.1
created: Accessible door width (sample)
[info] rule_pack_seeded  jurisdiction=sample name='Door name recorded' region= rule_pack_id=93d79ffa-cf3e-47c9-a05d-90a6791db0c1 service=RulePackService specifications=1 version=0.1
created: Door name recorded (sample)
[info] rule_pack_seeded  jurisdiction=sample name='No doors permitted' region= rule_pack_id=e92e8690-7d9a-4a28-8e54-ee129dee4885 service=RulePackService specifications=1 version=0.1
created: No doors permitted (sample)
done: 3 created, 0 skipped, 3 rule packs in the catalogue

$ docker compose -f deploy/compose.yaml exec api python manage.py shell -c \
  "from cadgpt.apps.rulepack.models import RulePack; print(RulePack.objects.count())"
3
```

Run again, unchanged:

```
$ docker compose -f deploy/compose.yaml exec api python manage.py seed_rule_packs
[info] rule_pack_seed_skipped  jurisdiction=sample name='Accessible door width' region= rule_pack_id=cc0b0297-0ffb-4f6e-b4a1-4b538ece6457 service=RulePackService version=0.1
skipped (already seeded): Accessible door width (sample)
[info] rule_pack_seed_skipped  jurisdiction=sample name='Door name recorded' region= rule_pack_id=93d79ffa-cf3e-47c9-a05d-90a6791db0c1 service=RulePackService version=0.1
skipped (already seeded): Door name recorded (sample)
[info] rule_pack_seed_skipped  jurisdiction=sample name='No doors permitted' region= rule_pack_id=e92e8690-7d9a-4a28-8e54-ee129dee4885 service=RulePackService version=0.1
skipped (already seeded): No doors permitted (sample)
done: 0 created, 3 skipped, 3 rule packs in the catalogue

$ docker compose -f deploy/compose.yaml exec api python manage.py shell -c \
  "from cadgpt.apps.rulepack.models import RulePack; print(RulePack.objects.count())"
3
```

Same `rule_pack_id` UUIDs both times, row count unchanged at 3: the second run created nothing.
The catalogue is seeded honestly, per T-0030's "do not invent jurisdictions" instruction: the
three packs are `packages/engine/tests/fixtures/*.ids` (development fixtures, not regulation),
seeded under `jurisdiction="sample"` — a placeholder that says plainly what it is rather than
claiming to be a real code. See `docs/decisions.md` for the reasoning.

### 2. A real HTTP request listing the catalogue, and the same request filtered by jurisdiction

Against `http://localhost:8000`, authenticated with a real JWT from `/api/v1/auth/login/`:

```
$ curl -s http://localhost:8000/api/v1/rule-packs/ \
    -H "Authorization: Bearer $TOKEN_A" -H "X-Tenant: t0030-atelier-a"
{
    "count": 3,
    "page": 1, "pages": 1, "size": 20, "next": null, "previous": null,
    "results": [
        {
            "uuid": "cc0b0297-0ffb-4f6e-b4a1-4b538ece6457",
            "name": "Accessible door width",
            "description": "A numeric building-code style rule: every door leaf is at least 900 mm wide.",
            "jurisdiction": "sample", "region": "", "version": "0.1",
            "title": "Accessible door width", "author": "", "specification_count": 1,
            "source_citation": "cadgpt engine test fixture (packages/engine/tests/fixtures/door_width.ids in this repository). Not an authored regulation -- seeded to exercise the rule pack catalogue's storage and selection path ahead of the product owner's authored packs (docs/plan.md, Phase 3: Iranian building code first, then EU and US).",
            "source_file": "http://localhost:8000/media/rule-packs/sample/a0eeb46c-a69e-4948-84c3-5ccec8a7c6c5.ids",
            "created_at": "2026-09-02T18:06:29.427592Z"
        },
        { "uuid": "93d79ffa-cf3e-47c9-a05d-90a6791db0c1", "name": "Door name recorded", "jurisdiction": "sample", "version": "0.1", "specification_count": 1, "...": "..." },
        { "uuid": "e92e8690-7d9a-4a28-8e54-ee129dee4885", "name": "No doors permitted", "jurisdiction": "sample", "version": "0.1", "specification_count": 1, "...": "..." }
    ]
}
```

Filtered by jurisdiction — a real match returns all 3, a jurisdiction with no packs returns
none rather than something invented for it:

```
$ curl -s "http://localhost:8000/api/v1/rule-packs/?jurisdiction=sample" -H "Authorization: Bearer $TOKEN_A" -H "X-Tenant: t0030-atelier-a"
{"count": 3, "...": "same 3 rows as above"}

$ curl -s "http://localhost:8000/api/v1/rule-packs/?jurisdiction=ir" -H "Authorization: Bearer $TOKEN_A" -H "X-Tenant: t0030-atelier-a"
{"count": 0, "page": 1, "pages": 1, "size": 20, "next": null, "previous": null, "results": []}
```

### 3. Two tenants, one catalogue — and a write refused

Two independently registered owners, two independently created tenants
(`t0030-atelier-a`, `t0030-atelier-b`), same catalogue:

```
$ curl -s http://localhost:8000/api/v1/rule-packs/ -H "Authorization: Bearer $TOKEN_A" -H "X-Tenant: t0030-atelier-a" | python3 -c "..."
count: 3
uuids: ['93d79ffa-...', 'cc0b0297-...', 'e92e8690-...']

$ curl -s http://localhost:8000/api/v1/rule-packs/ -H "Authorization: Bearer $TOKEN_B" -H "X-Tenant: t0030-atelier-b" | python3 -c "..."
count: 3
uuids: ['93d79ffa-...', 'cc0b0297-...', 'e92e8690-...']
```

Identical UUID sets. It also works with no `X-Tenant` header at all — a user browsing the
catalogue before choosing a workspace, same as `TenantViewSet`:

```
$ curl -s http://localhost:8000/api/v1/rule-packs/ -H "Authorization: Bearer $TOKEN_A" | python3 -c "..."
count: 3
```

Every write refused, 405 regardless of role or tenant — the viewset mixes in only
`ListModelMixin`/`RetrieveModelMixin`, so create/update/delete are never wired at all:

```
$ curl -s -o /dev/null -w "%{http_code}\n" -X POST http://localhost:8000/api/v1/rule-packs/ -H "Authorization: Bearer $TOKEN_A" -H "X-Tenant: t0030-atelier-a" -d '{"name":"hijacked"}'
405
$ curl -s -o /dev/null -w "%{http_code}\n" -X PATCH http://localhost:8000/api/v1/rule-packs/cc0b0297.../ -H "Authorization: Bearer $TOKEN_A" -H "X-Tenant: t0030-atelier-a" -d '{"name":"hijacked"}'
405
$ curl -s -o /dev/null -w "%{http_code}\n" -X DELETE http://localhost:8000/api/v1/rule-packs/cc0b0297.../ -H "Authorization: Bearer $TOKEN_A" -H "X-Tenant: t0030-atelier-a"
405
$ curl -s -X POST http://localhost:8000/api/v1/rule-packs/ -H "Authorization: Bearer $TOKEN_A" -H "X-Tenant: t0030-atelier-a" -d '{"name":"hijacked"}'
{"type":"about:blank#method_not_allowed","status":405,"code":"method_not_allowed","detail":"Method \"POST\" not allowed.","request_id":"1f69d426c4e444c180622dd92b4b2f48"}
```

### 4. Wiring

Migration at head:

```
$ docker compose -f deploy/compose.yaml exec api python manage.py showmigrations rulepack
rulepack
 [X] 0001_initial
 [X] 0002_rulepack
```

Route, quoted from `services/api/cadgpt/apps/rulepack/api/v1/urls.py`:

```python
router = ScopedRouter(scope="tenant")
router.register("rule-sets", RuleSetViewSet, basename="rule-set")
router.register("rule-packs", RulePackViewSet, basename="rule-pack")
```

Management command discoverable:

```
$ docker compose -f deploy/compose.yaml exec api python manage.py help | grep -A2 '\[rulepack\]'
[rulepack]
    seed_rule_packs
```

### 5. The structural viewset test, unweakened

`test_every_viewset_over_a_tenant_owned_model_is_tenant_scoped`
(`services/api/cadgpt/tests/test_tenant_isolation.py`) is untouched — not one line of it
changed. Its own scope already excludes `RulePackViewSet`, because that scope is "every
viewset **over a tenant-owned model**", not "every viewset":

```python
def test_every_viewset_over_a_tenant_owned_model_is_tenant_scoped() -> None:
    """The contract: routes touching tenant data inherit the base class that filters."""
    tenant_owned = set(_tenant_owned_models())
    offenders = []

    for name, cls in _registered_viewsets().items():
        model = getattr(cls.queryset, "model", None)
        if model not in tenant_owned:
            continue
        if name in SCOPED_BY_MEMBERSHIP:
            continue
        if not issubclass(cls, TenantScopedViewSet):
            offenders.append(f"{name} (model {model.__name__})")

    assert offenders == [], (...)
```

`RulePack` does not inherit `TenantOwnedModel`, so it is never a member of
`_tenant_owned_models()`, and `RulePackViewSet` is skipped by the `if model not in
tenant_owned: continue` line before its base class is even inspected — no entry was added to
`SCOPED_BY_MEMBERSHIP` (that set is for a different case: a tenant-owned model scoped by
something other than `TenantScopedViewSet`, which `RulePack` is not). This is the coordinator's
own read, verified independently, and it is correct.

What was added is a second, narrower thing: a declaration that makes the exemption
self-invalidating instead of merely true by accident of what `RulePack` currently inherits:

```python
GLOBAL_CATALOGUE_VIEWSETS = {
    "RulePackViewSet",
}

def test_the_global_catalogue_declaration_names_no_tenant_owned_model() -> None:
    """The other half of the T-0030 exemption: it stays legal only as long as it is true. [...]"""
    viewsets = _registered_viewsets()
    for name in GLOBAL_CATALOGUE_VIEWSETS:
        cls = viewsets.get(name)
        assert cls is not None, (...)
        model = cls.queryset.model
        assert not issubclass(model, TenantOwnedModel), (
            f"{name} is declared as a global catalogue viewset because {model.__name__} "
            "was said to hold no tenant data, but it now inherits TenantOwnedModel. "
            "Remove it from GLOBAL_CATALOGUE_VIEWSETS and make the viewset inherit "
            "TenantScopedViewSet instead -- this model holds tenant data now."
        )
```

`GLOBAL_CATALOGUE_VIEWSETS` is **never consulted** by the original test — it has no `continue`
or exemption branch that reads it. It exists only so a second, independent test can watch the
one fact the exemption depends on (`RulePack` is not `TenantOwnedModel`) and fail the moment
that stops being true. This narrows what the exemption is allowed to keep meaning; it does not
widen what escapes the original test.

### 6. Mutation proof

`RulePack(UuidBaseModel)` changed to `RulePack(TenantOwnedModel, UuidBaseModel)` (models.py
line 91), `RulePackViewSet` left untouched (still not `TenantScopedViewSet`):

```
$ uv run pytest services/api/cadgpt/tests/test_tenant_isolation.py \
    -k "tenant_owned_model_is_tenant_scoped or global_catalogue_declaration" -v
FAILED test_every_viewset_over_a_tenant_owned_model_is_tenant_scoped
E   AssertionError: these viewsets serve tenant-owned models without inheriting TenantScopedViewSet, so nothing narrows their queryset to the requesting tenant: RulePackViewSet (model RulePack)
E   assert ['RulePackVie...el RulePack)'] == []

FAILED test_the_global_catalogue_declaration_names_no_tenant_owned_model
E   AssertionError: RulePackViewSet is declared as a global catalogue viewset because RulePack was said to hold no tenant data, but it now inherits TenantOwnedModel. Remove it from GLOBAL_CATALOGUE_VIEWSETS and make the viewset inherit TenantScopedViewSet instead -- this model holds tenant data now.
E   assert not True
E    +  where True = issubclass(<class 'cadgpt.apps.rulepack.models.RulePack'>, TenantOwnedModel)

2 failed, 8 deselected in 0.30s
```

Both the original, untouched test and the new declaration test catch the violation
independently. Reverted (`class RulePack(UuidBaseModel):`), confirmed byte-identical to the
pre-mutation file (`diff` empty), re-run:

```
$ uv run pytest services/api/cadgpt/tests/test_tenant_isolation.py \
    -k "tenant_owned_model_is_tenant_scoped or global_catalogue_declaration" -v
services/api/cadgpt/tests/test_tenant_isolation.py ..                    [100%]
2 passed, 8 deselected in 0.22s
```

### What was not asked and was not built

Selection at check time (T-0031), clause records / YAML compilation / ratification (Phase 4),
and any real jurisdiction's rule content are all explicitly out of scope per the task and were
not touched.

## Review

**Verdict: FIX NOW — nothing.** Reviewed on opus, gated on tenancy. The review was dispatched as
the session was ending and landed before it closed; an earlier note in this file said it had been
lost, and that note was wrong and is removed.

No invariant is violated and no claim in the evidence block is false — the first time this
session that a review found neither. It did not take the evidence on trust: it re-registered
**two tenants of its own** on the running stack and re-ran evidence items 2, 3 and 4 from
scratch. Both tenants get `count: 3` and byte-identical UUID sets, matching what the database
holds. Unauthenticated list and detail both 401. It also tested writes the evidence had **not** —
`PUT`, and `POST` to the detail route — and got 405 on all of them.

The write refusal is **by construction rather than convention**: `RulePackViewSet`
(`api/v1/views.py:59`) mixes in only `ListModelMixin` and `RetrieveModelMixin` over
`BaseViewSet`, with no `@action` and no need for `http_method_names` — the handlers do not exist,
so no route, filter parameter or browsable-API form can reach a write. Evidence item 5's quoted
test body is verbatim against the file. `git diff --numstat` on `models.py` is **72 added, 0
deleted**: not one line of `RuleSet` changed, nothing under `apps/review/` touched, so selection
is not wired into the run, and there is no clause, YAML or ratification code.

Six suspicions were tested and dropped. The serializer leaks no internal id or uploader
(`read_only_fields = fields`, lookup by `uuid`, and `RulePack` has no `created_by` column at
all). Filter abuse fails: `jurisdiction__icontains`, `ordering=source_file` and `page_size=1000`
are all silently ignored, `ordering` is bounded by `ordering_fields`, page size is server-fixed.
A forged `X-Tenant` is inert because the viewset never reads it, and a user with **no tenant at
all** gets the same three rows — which is the intended "readable by all". Layering is clean:
nothing substantive outside `services.py`. And **`source_citation` is genuinely enforced** — the
reviewer probed `""`, `"   "` and `"\n\t "` and all three were refused with *This field cannot
be blank*, because the manager strips before `full_clean`, so whitespace cannot slip through.
The seeded citation is real and specific, naming the fixture path and stating plainly that it is
not regulation. `prd.md` §5.7 holds and there is no placeholder.

The `docs/decisions.md` entry was checked mechanically claim by claim and is accurate; it records
the reasoning — why the nullable column was refused, why a declaration beats a skip list — rather
than restating the outcome.

### QUEUED — T-0042, T-0043, T-0044

The findings are all about the surfaces *around* the catalogue, not the invariant it was gated
on. Finding 1 (the serializer hands out a raw storage URL that `curl` fetches with **no
Authorization header**, returning the IDS bytes — and which in production advertises a download
that returns the SPA's HTML, because nginx has no `/media/` location) became **T-0042**.
Findings 2, 3 and 6 (the seeder's idempotence is an unlocked pre-check that TOCTOUs across
processes into an unhandled `IntegrityError` and an orphaned file, and the manager raises
Django's `ValidationError` rather than the app's) became **T-0043**. Findings 4 and 5 (the seed
manifest is hardcoded Python, and a pack whose source file changed is skipped silently and
correctly but illegibly) became **T-0044**.
