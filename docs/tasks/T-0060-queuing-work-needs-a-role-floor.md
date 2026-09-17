# T-0060 — A viewer can queue work on the shared check queue

**Phase:** 3   **Status:** done
**Touches invariants:** tenancy — the role half, not the isolation half. **Reviewer-gated.**

## Why

Found by the T-0051 review. `CheckRunViewSet.permission_classes = (IsTenantMember,)`
(`views.py:102`) with no `get_permissions` override, while the analogous work-queuing action
`ReviewViewSet.check` requires `IsTenantMemberOrAbove` (`views.py:62-65`).

`IsTenantMember` only asserts that a membership exists (`tenancy/permissions.py:18-30`). So a
**VIEWER — documented as "May read the tenant's work but change nothing" — can enqueue
`generate_report_file`.** With `throttle_classes=[]` (`views.py:151`) and no dedupe, a POST loop
floods the `checks` queue that real model checks run on.

**Tenant isolation itself is intact.** The reviewer confirmed `get_object()` goes through
`tenant_queryset()`, so nobody reaches another tenant's run. This is a role gate, not a leak — the
structural tenancy invariant is unaffected, and the queued task should not be read as a hole in it.

The asymmetry is the tell: the two work-queuing POSTs in the product disagree about who may queue
work, and the newer one is the permissive one. That is how a role model erodes — not by a decision,
but by a new endpoint not inheriting one.

## Scope

**Changes**

- Queuing work requires the same role floor wherever it happens. Bring `generate_report` in line
  with `ReviewViewSet.check`, or state why the two genuinely differ.
- Decide whether a work-queuing POST should carry a throttle. `throttle_classes=[]` was a deliberate
  choice on the check action; whether it is right for an action any member can press repeatedly is a
  separate question. Say which and why.
- A test that fails if a work-queuing endpoint is added without a role floor. The defect here is not
  one endpoint's permission tuple — it is that nothing noticed the new endpoint disagreeing with the
  old one.

**What explicitly does not change**

- Tenant isolation, which is intact and structurally tested.
- The role model itself, or what VIEWER means.

## How to prove it ran

`make verify`, then over real HTTP: a VIEWER refused on both work-queuing endpoints, a member above
that floor accepted on both, responses pasted. Then the structural test demonstrated failing against
a deliberately unguarded new endpoint — a test that only asserts today's tuple would not have caught
this and will not catch the next one.

## Evidence

### 1. The fix

`CheckRunViewSet` (`services/api/cadgpt/apps/review/api/v1/views.py`) gained a
`get_permissions` override, the same shape `ReviewViewSet.get_permissions` already uses:

```python
def get_permissions(self) -> list[Any]:
    """Reading a run is `IsTenantMember`; queuing work on it is not.
    ...
    """
    if self.action == "generate_report":
        return [IsTenantMemberOrAbove()]
    return list(super().get_permissions())
```

Only `generate_report` is raised. `list`, `retrieve` and `report_file` (the download)
still fall through to `super().get_permissions()`, i.e. `IsTenantMember` — reading a run
and downloading an already-generated report are unchanged, as scoped.

### 2. The throttle decision: no throttle added

`generate_report` keeps `throttle_classes=[]`. Reasoning, also written into the action's
docstring:

- The flood concern in the Why section was "any VIEWER can hit this" — a *population*
  problem. The fix is the population: only `IsTenantMemberOrAbove` can reach it now.
- `generate`'s own contract (`ReportGenerationService.generate`,
  `services/review/services/report_generation.py`) is idempotent by row lock: a run that
  already has `report_file_id` set returns immediately, without rendering or storing
  anything. One real render happens per succeeded run; every repeat call after that is a
  cheap lock-and-return. This was confirmed live, not just read: the worker log below
  shows the *first* `generate_report_file` task (the automatic dispatch after the check
  succeeded) taking 0.36s, and the *second* one (my MEMBER's manual POST, on the same
  already-reported run) taking 0.05s — the no-op path, observed.
- `ReviewViewSet.check`, the action this task is told to match, dispatches a full,
  uncached model check on *every* call and already carries the identical
  `throttle_classes=[]`. Throttling `generate_report` more tightly than `check` would
  make the cheaper, idempotent action the stricter one, for no reason tied to cost, and
  would introduce a new asymmetry in the opposite direction from the one this task closes.
  If a real flood vector is ever found on one, it is the same vector on the other, and the
  fix belongs on both together — out of this task's scope, which is the role floor.

### 3. `make verify`

```
uv run ruff check .           -> All checks passed!
uv run ruff format --check .  -> 196 files already formatted
uv run mypy packages/engine/src services/api/cadgpt  -> Success: no issues found in 178 source files
uv run lint-imports --no-cache -> Contracts: 5 kept, 0 broken.
uv run pytest -m "not postgres" -> 328 passed, 1 deselected, 39 warnings in 10.00s
pnpm run verify (web)          -> lint (0 errors), typecheck, build, build-workbench,
                                   test-unit (6 passed), test-storybook (36 passed) — all green
```

Full `make verify` run, top to bottom, exits 0.

### 4. The structural regression test

New file: `services/api/cadgpt/tests/test_role_floor.py`.

It does not assert "`check` and `generate_report` require `IsTenantMemberOrAbove` today."
It walks every registered viewset (`_registered_viewsets`, mirroring
`test_tenant_isolation._registered_viewsets`'s URL-resolver walk — including
`CheckRunViewSet`'s hand-wired nested routes, not just router-registered ones), finds
every `@action`-decorated method that answers a write HTTP verb (`_write_extra_actions` —
this is DRF's own `get_extra_actions()`, independent of how a route was wired), builds the
permission instances DRF would actually construct for that action
(`_permissions_for_action`, which instantiates the viewset with the action's own
`@action(..., permission_classes=...)` kwargs the way `ViewSetMixin.as_view` does, and
sets `.action` the way `initialize_request` does, so a `get_permissions()` override that
branches on `self.action` — `ReviewViewSet`'s and `CheckRunViewSet`'s own pattern — is
exercised correctly), and fails if none of the resolved permissions is a `_MinimumRole`
of at least `MEMBER` rank.

**Proof it actually catches the regression it's meant to.** A deliberately unguarded
work-queuing action was added to `ProjectViewSet` (`services/api/cadgpt/apps/project/api/v1/views.py`):

```python
@action(detail=True, methods=["post"])
def rescan(self, request: Request, uuid: str) -> Response:
    return Response(status=status.HTTP_202_ACCEPTED)
```

(No entry in `get_permissions`'s `{"create", "destroy"}` set, so it falls through to the
class's plain `IsTenantMember`.) Running the new test against it:

```
$ uv run pytest services/api/cadgpt/tests/test_role_floor.py::test_every_work_queuing_action_requires_at_least_member -q
F
AssertionError: these actions dispatch work through a write HTTP verb but do not require at
least IsTenantMemberOrAbove, so a VIEWER could queue work through them:
ProjectViewSet.rescan (permissions resolved to: IsTenantMember)
1 failed in ...
```

`rescan` and its import were then reverted (`git diff --stat
services/api/cadgpt/apps/project/api/v1/views.py` shows no diff after reverting), and the
suite is green again:

```
$ uv run pytest services/api/cadgpt/tests/test_role_floor.py -q
...
3 passed in ...
```

### 5. The real path — over real HTTP against the live stack

Docker's build has no network egress in this sandbox (`uv sync` inside the build
container could not reach pypi.org even with the host's proxy vars forwarded), so
`make up`'s image could not be rebuilt with the fix baked in. Instead: the running
`api`/`worker`/`beat` containers (stale image) were stopped, and the **real**, already-
migrated Postgres (`localhost:5433`) and Redis (`localhost:6380`) from that same compose
stack were kept running; `manage.py runserver` and a real `celery -A cadgpt.config.celery
worker -Q checks,default` were started locally, against those same real services, running
the actual current source tree (`DJANGO_SETTINGS_MODULE=cadgpt.config.settings.local`).
This is the real path — real Postgres, real Redis, a real separate worker process, no
mocks — just not the containerized image, which the sandbox's network policy blocked from
rebuilding. Both containers were restarted back to their prior (pre-existing, stale-image)
state afterwards, so the environment was left as found.

Registered a fresh owner, viewer and member, a real tenant, real memberships at `viewer`
and `member` role, a real project, real `three_doors.ifc` / `door_width.ids` uploads, a
real rule set and a real review — then:

```
=== VIEWER POST /reviews/{uuid}/check/ ===
{"type":"about:blank#permission_denied","status":403,"code":"permission_denied",
 "detail":"نقش شما در این فضای کاری اجازهٔ این کار را نمی‌دهد.", ...}
HTTP_STATUS:403

=== MEMBER POST /reviews/{uuid}/check/ ===
{"uuid":"c0e3d248-2dd0-4b37-bf0a-96cbebd696ec","status":"pending", ...}
HTTP_STATUS:202
```

The run was polled to completion through the real worker (`status: succeeded`, `outcome:
FAIL`, `passed/failed/indeterminate = 1/1/1` — the known three-doors fixture result) and
its worker log shows the automatic `generate_report_file` dispatch already ran
(`c906bc29...` finished in 0.36s). Then, on that same succeeded run:

```
=== VIEWER POST report-file (expect 403) ===
{"type":"about:blank#permission_denied","status":403,"code":"permission_denied",
 "detail":"نقش شما در این فضای کاری اجازهٔ این کار را نمی‌دهد.", ...}
HTTP_STATUS:403

=== MEMBER POST report-file (expect 202) ===
{"uuid":"c0e3d248-2dd0-4b37-bf0a-96cbebd696ec","status":"succeeded", ...
 "report_file_url":"/api/v1/reviews/62e35fb1-.../runs/c0e3d248-.../report-file/", ...}
HTTP_STATUS:202
```

Worker log for that second call:

```
Task review.tasks.generate_report_file[604b104b-...] received
Task review.tasks.generate_report_file[604b104b-...] succeeded in 0.052395657054148614s: 'b7c66d0e-5766-4779-b25c-41c3af19148f'
```

— the same `Media` uuid (`b7c66d0e...`) both times: the idempotent no-op the throttle
decision above rests on, observed rather than assumed.

VIEWER refused (403) on both work-queuing endpoints; MEMBER accepted (202) on both.

### Wiring

The route through which `generate_report` is actually reachable, quoted from
`services/api/cadgpt/apps/review/api/v1/urls.py`:

```python
run_report_file = CheckRunViewSet.as_view({"get": "report_file", "post": "generate_report"})
...
path(
    "reviews/<uuid:review_uuid>/runs/<uuid:uuid>/report-file/",
    run_report_file,
    name="tenant-review-run-report-file",
),
```

And the permission override that now gates it, quoted from
`services/api/cadgpt/apps/review/api/v1/views.py`:

```python
def get_permissions(self) -> list[Any]:
    if self.action == "generate_report":
        return [IsTenantMemberOrAbove()]
    return list(super().get_permissions())
```

### NOT DONE

Nothing. Tenant isolation and the role model were not touched, per scope. `ReviewViewSet.
check`'s own `throttle_classes=[]` was read and reasoned about but deliberately left
unchanged — not this task's scope, and changing it alone (without also revisiting
`check`) would have been the wrong-shaped fix.

## Fix-now round: F1 — permission resolution ignored hand-wired routing

A review of the uncommitted diff found that `_permissions_for_action` in
`services/api/cadgpt/tests/test_role_floor.py` resolved an action's permissions from
`action_func.kwargs` — the `@action(...)` decorator's own kwargs — reproducing only
how DRF's `SimpleRouter` injects those kwargs into `as_view()` for a *router-registered*
action. `CheckRunViewSet.generate_report` is reached through a hand-wired
`CheckRunViewSet.as_view({"get": "report_file", "post": "generate_report"})`
(`review/api/v1/urls.py:21`), which DRF's `ViewSetMixin.as_view` builds with
`initkwargs = {}` — an `@action(..., permission_classes=...)` kwarg on that route would
never be forwarded, so the old test would have credited it anyway, false-passing exactly
the routing style of the endpoint the whole task exists to guard.

**The fix.** `services/api/cadgpt/tests/test_role_floor.py` now resolves permissions
from the actual URL routing, not the class plus an isolated `@action` kwarg:

- `_registered_viewsets` (class-keyed) was replaced by `_routed_views()`, which walks
  the URL resolver (same walk as before) but keeps each `as_view()` **callback** —
  `CheckRunViewSet` alone has three (`run_list`, `run_detail`, `run_report_file`), each
  with its own `.actions` method-map and its own `.initkwargs`.
- `_write_extra_actions` now returns action *names* (still from DRF's own
  `get_extra_actions()`, still the "answers a write verb" filter).
- `_permissions_for_action` was replaced by `_permissions_for_route(callback,
  action_name)`, which builds `callback.cls(**callback.initkwargs)` — reproducing
  `ViewSetMixin.as_view`'s own `self = cls(**initkwargs)` for the *specific route*
  resolved, not an assumed router registration — sets `.action`, and calls
  `get_permissions()`.
- `test_every_work_queuing_action_requires_at_least_member` now iterates
  `_routed_views()` and, for each callback's `{http_method: action_name}` map, checks
  only entries that are both a write verb and a write extra action, deduplicated per
  `(id(callback), action_name)`.

This makes a hand-wired route resolve permissions from what it actually received
(nothing, for `run_report_file`), while a router-registered route
(`MembershipViewSet.invite`/`.revoke`, `ReviewViewSet.check`) still credits the
`@action` kwargs the router genuinely injects — confirmed by `MembershipViewSet`'s
routes being registered through `ScopedRouter` (`tenancy/api/v1/urls.py`), so its
`@action(..., permission_classes=(IsTenantAdmin,))` kwargs really do reach
`callback.initkwargs` there.

**Mutation proof 1 — the exact false-pass the reviewer demonstrated, now caught.**
`CheckRunViewSet.get_permissions`'s override was removed and `generate_report`'s
`@action` was changed to the "idiomatic" form the reviewer used:

```python
@action(
    detail=True,
    methods=["post"],
    url_path="report-file",
    throttle_classes=[],
    permission_classes=(IsTenantMemberOrAbove,),
)
def generate_report(self, request: Request, review_uuid: str, uuid: str) -> Response:
```

Structural test — this would have false-passed under the old resolver; with the fixed
resolver:

```
$ uv run pytest services/api/cadgpt/tests/test_role_floor.py::test_every_work_queuing_action_requires_at_least_member -q
E   AssertionError: these actions dispatch work through a write HTTP verb but do not require at
    least IsTenantMemberOrAbove, so a VIEWER could queue work through them:
    CheckRunViewSet.generate_report (permissions resolved to: IsTenantMember)
FAILED
```

Behavioural test on the same mutation, also fails as expected (a VIEWER really gets
through):

```
$ uv run pytest services/api/cadgpt/tests/test_role_floor.py::test_role_floor_on_generate_report -q
FAILED services/api/cadgpt/tests/test_role_floor.py::test_role_floor_on_generate_report
```

The mutation was then reverted (`git diff --stat
services/api/cadgpt/apps/review/api/v1/views.py` shows only the original,
pre-mutation `get_permissions` fix — 27 insertions, the same diff as before this
round), and the full file is green again:

```
$ uv run pytest services/api/cadgpt/tests/test_role_floor.py -q
...
3 passed
```

**Mutation proof 2 — the pre-existing `ProjectViewSet.rescan` coverage, re-run to
confirm the resolver change didn't regress it.** The same unguarded action from the
original round was re-added (router-registered this time, unlike `generate_report`):

```python
@action(detail=True, methods=["post"])
def rescan(self, request: Request, uuid: str) -> Response:
    return Response(status=status.HTTP_202_ACCEPTED)
```

```
$ uv run pytest services/api/cadgpt/tests/test_role_floor.py::test_every_work_queuing_action_requires_at_least_member -q
E   AssertionError: ... ProjectViewSet.rescan (permissions resolved to: IsTenantMember)
FAILED
```

Reverted; `git diff --stat services/api/cadgpt/apps/project/api/v1/views.py` shows no
diff, and the suite is green:

```
$ uv run pytest services/api/cadgpt/tests/test_role_floor.py -q
...
3 passed
```

**`make verify`, full run after the fix:**

```
uv run ruff check .            -> All checks passed!
uv run ruff format --check .   -> 196 files already formatted
uv run mypy packages/engine/src services/api/cadgpt -> Success: no issues found in 178 source files
uv run lint-imports --no-cache -> Contracts: 5 kept, 0 broken.
uv run pytest -m "not postgres" -> 328 passed, 1 deselected, 39 warnings in 8.19s
pnpm run verify (web)           -> lint (0 errors, 2 pre-existing fast-refresh warnings
                                    unrelated to this change), typecheck, build,
                                    build-workbench, test-unit (6 passed),
                                    test-storybook (36 passed) — all green
```

Full `make verify`, top to bottom, exits 0.

### Fix-now NOT DONE

Nothing in scope for F1. Q2–Q7 from the same review (an action-name mismatch under
`@x.mapping.post`, the no-throttle reasoning's scope, an unshown-twice `Media` uuid
match claim, `throttle_classes=[]` not being the operative mechanism on the hand-wired
route, no regression test pinning the GET download's permission, and CRUD writes being
outside the structural test's scope) are explicitly out of scope for this round, per
the fix-now instruction — queued separately by the coordinator.

## Review

**Verdict: correct, reviewer-gated on the tenancy role invariant, one fix-now round,
closed.** The reviewer independently re-derived DRF's `ViewSetMixin.as_view`/
`initialize_request` dispatch trace and confirmed the production fix's `self.action ==
"generate_report"` branch genuinely fires on the real request path; confirmed live over
real HTTP that `list`/`retrieve`/`report_file` (the GET download) are unaffected — a
VIEWER still gets 200 on the download; independently reproduced the `ProjectViewSet.rescan`
mutation proof; and re-ran `make verify` rather than trusting the paste.

**FIX NOW (1), closed same task:** F1 — the new structural guard's `_permissions_for_action`
resolved permissions from a viewset class plus an `@action` decorator's own kwargs, which
mirrors only how DRF's router injects those kwargs for a *router-registered* action.
`CheckRunViewSet.generate_report` — the very endpoint the task exists to guard — is reached
through a hand-wired `as_view({...})` route, where an `@action(permission_classes=...)`
kwarg is never forwarded; the old resolver would have credited it anyway, false-passing
exactly this routing style. Proven by the reviewer via mutation: the shipped
`get_permissions`-branch fix swapped for the "idiomatic" `@action(permission_classes=...)`
form made the structural test report "no offenders" while the behavioural test showed a
VIEWER genuinely getting through (202, not 403). Closed in the round above: permission
resolution now derives from the actual resolved route's callback (`cls`, `actions`,
`initkwargs` — what `ViewSetMixin.as_view()` really bakes in), not an assumed router
registration. Both the reviewer's original mutation proof and the reconstructed false-pass
mutation were re-run and now correctly fail; `make verify` re-run clean, 328 passed.

**QUEUED, not fixed here — T-0091 through T-0094:** the same guard can still misattribute
permissions under an `@action.mapping`-decorated verb sharing a route with a differently-
named sibling action, unused anywhere in this codebase today (**T-0091**); the no-throttle
reasoning bounds work-per-message, not messages enqueued on the shared queue, and
understates a narrow, worker-concurrency-bounded race in `generate`'s own dropped-lock
window (**T-0092**); the idempotence proof pasted one `Media` uuid where it claimed two
matched, and the docstring names `throttle_classes=[]` as an active mechanism on a
hand-wired route where it never actually applies (**T-0093**); and nothing pins a VIEWER's
continued ability to download a report, so a future widening of the permission branch could
silently lock them out with no test noticing (**T-0094**). None blocks this task's own
claim; none is a fix-now finding.