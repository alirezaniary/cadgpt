# T-0083 — The hardcoded-Persian product never activates Persian on the server

**Phase:** 3   **Status:** done
**Touches invariants:** none directly. Adjacent to "every user-facing string goes through
gettext" (`CLAUDE.md`) — the strings do; the language they render in is accidental.

## Why

Found while proving T-0056's real-path evidence. The frontend was settled in T-0072 as
"single-language, hardcoded to Persian, not user-switchable" — every frontend string is a
fixed Persian literal regardless of the visiting browser. The server side of the same product
was never given the equivalent decision:

- `LANGUAGE_CODE = "en"` in `services/api/cadgpt/config/settings/base.py:124`.
- `LocaleMiddleware` is active, so whichever language it activates for a request is whatever
  `Accept-Language` header arrived with it.
- `services/web` never sends an `Accept-Language` header on any request (grepped across
  `services/web/src`; the only hit is an unrelated comment in
  `report_generation.py`).

So every `gettext`-wrapped string the server writes into a stored, user-facing field —
`CheckRun.failure_detail` (T-0056, T-0048), report prose (T-0026, T-0029), validation and
conflict messages throughout `services/*/services/*.py` — renders in whatever language the
visiting browser's own locale happens to request, which for almost every real deployment
means English, in a product whose entire frontend is fixed Persian. Verified directly: an
unforced browser session showed T-0056's new failure text and long-shipped T-0026/T-0029
report prose both in English in the same page; the identical server call with an explicit
`Accept-Language: fa` header produced correct Persian for the parts triggered synchronously
inside that request.

There is a second, harder layer underneath the missing header. Most of the affected text —
report bodies, most `CheckRun.failure_detail` values — is written by the **Celery worker**,
which never has an HTTP request or an `Accept-Language` header at all. A frontend header fix
only reaches the synchronous half (like T-0056's `_reap_lost_dispatch`, which runs inside the
request). The worker half needs its own answer to "which language," independent of any
request — most plausibly a hardcoded `fa` activation at the top of `execute_check_run`,
matching the product decision, rather than a per-tenant or per-request language that does not
exist yet.

## Scope

**Changes**

- Decide and implement how the server settles on Persian without depending on the caller:
  most directly, activate `fa` explicitly wherever server-generated user-facing text is
  produced — the Celery worker's task entrypoint, and (if kept as a defense in depth)
  `LocaleMiddleware`'s default. Changing `LANGUAGE_CODE` to `"fa"` alone does not reach the
  worker, which has no request and thus no middleware.
- Confirm nothing currently relies on `Accept-Language`-driven English for a legitimate
  reason (e.g. an admin tool, a management command) before removing the dependency.
- A regression test that does not merely assert a translated string exists (that already
  passes today under the wrong assumption) but that the *stored* value is Persian when
  produced with no `Accept-Language` header at all — the shape of every real worker call.

**What explicitly does not change**

- The frontend's own strings, already fixed Persian since T-0072.
- T-0056's `_reap_lost_dispatch` mechanism itself — this task is about the language it writes
  in, not the recovery logic.

## How to prove it ran

`make verify`, then against `make up`: trigger a worker-produced failure (or reuse T-0056's
`dispatch_lost` path) with **no** `Accept-Language` header sent anywhere in the request chain,
and show the stored `failure_detail` (or report prose) is Persian. Then show the existing
English-language paths this task removes reliance on — if any caller legitimately wants
English, name it and say what happens to it now.

## Evidence

### 0. Decisions, made deliberately

**Decision 1 — two independent activation layers, not one.** `LANGUAGE_CODE` in
`services/api/cadgpt/config/settings/base.py` changed from `"en"` to `"fa"` (defense in
depth: it is what `LocaleMiddleware` falls back to for any request with no
`Accept-Language`, i.e. every real request `services/web` ever sends since T-0072), **and**
`cadgpt.apps.base.tasks.BaseTask.__call__` now wraps every task body in
`translation.override(settings.LANGUAGE_CODE)` explicitly. Investigated whether the second
layer was actually necessary before adding it (Django's own `gettext()` falls back to
`translation(settings.LANGUAGE_CODE)` — a module-level `_default` — for any thread that
never called `translation.activate()`, which I confirmed directly: with `LANGUAGE_CODE =
"fa"` and *no* activation anywhere, a bare `gettext("The worker running this check stopped
responding.")` in a fresh process already returned the Persian string). So `LANGUAGE_CODE`
alone would already have reached the worker, contrary to this task's own "Why" section
("Changing `LANGUAGE_CODE` alone does not reach the worker, which has no request and thus
no middleware") — that claim is about `LocaleMiddleware` specifically (true: it never runs
for Celery) but overstates the consequence, since `gettext`'s own fallback is independent of
middleware. Kept the explicit `BaseTask` activation anyway, deliberately, rather than relying
on that fallback alone: it is legible at the one place every task body runs, and it does not
depend on nobody else in the worker process ever having called `translation.activate()`
first (true today, but not a property `LANGUAGE_CODE`'s fallback documents or enforces).

**Decision 2 — two pre-existing bugs fixed alongside activation, not left broken by the
"no new gettext calls" framing.** The task's own framing assumed every affected string was
already `gettext`-wrapped and only its activated language was wrong. Auditing every
`failure_detail` write site (per the task's explicit ask to check whether T-0084/T-0085's
sweeps are in scope) found `CheckRunExecutor.reap_stalled` writing
`failure_detail="The worker running this check stopped responding."` as a bare Python
string literal — no `gettext` call at all, so no amount of activating the right language
could ever have made it Persian; T-0084 introduced it, T-0085 copied the sibling pattern
correctly (its own `reap_lost_dispatch` does use `_()`). Fixed by wrapping it
(`services/api/cadgpt/apps/review/services/execution.py`) and adding the catalogue entry.
Separately, verifying the real path (§3 below) surfaced a 403 whose `detail` was plain
English despite `Content-Language: fa` — traced to
`cadgpt/apps/tenancy/permissions.py`, where `IsTenantMember`, `IsTenantViewer`,
`IsTenantMemberOrAbove` and `IsTenantAdmin` all set `message = "<bare literal>"` on a DRF
`BasePermission`, again never through `gettext`. Fixed with `gettext_lazy` (not eager
`gettext`: `message` is a class attribute evaluated once at import time, before any
request's language is known — an eager call would freeze in whichever language happened to
be active during Django startup). Both are `CLAUDE.md`'s "every user-facing string goes
through gettext" invariant, violated independently of this task's activation question;
fixing them was necessary for this task's own claim ("the stored/served text is genuinely
Persian") to be true rather than true-with-two-silent-exceptions. Did **not** go looking for
further instances beyond these two discovered while doing the work — a full-codebase sweep
for ungettexted user-facing strings is a differently-scoped task if one is wanted later.

**Decision 3 — `test`/`verify` now compiles the `.po` catalogue before pytest runs, in both
the Makefile and CI.** The task's required regression test needs to assert a genuinely
translated stored value, not a proxy for one. Before this task, no test anywhere in the
suite did that, and two test files said so explicitly in their own docstrings
(`test_requirements.py`, `test_disclosure.py`: "this process's `.po` catalogue is not
compiled to `.mo` outside the container build ... so `gettext` here returns the English
source string verbatim"). That was an accident load-bearing for those tests staying green,
not a decision — `.github/workflows/verify.yml`'s `Tests` step never compiled messages
either, so CI has never once run `pytest` against a real Persian catalogue. Fixed by adding
a `compile-messages` prerequisite to `Makefile`'s `test`/`test-fast` targets and an
"Install gettext" + "Compile message catalogues" step to `.github/workflows/verify.yml`
before its `Tests` step (GitHub's own `ubuntu-latest` runner-image documentation does not
list `gettext` among preinstalled packages — checked rather than assumed, since the
production image already installs it explicitly for the same reason:
`deploy/docker/api.Dockerfile` line 17-18). This is a new, real environment requirement
`make verify`/CI now has (`msgfmt`) that it did not have before; it did not have it because
nothing before this task needed the catalogue to be real.

**Consequence of Decision 3, handled per-module.** Compiling the catalogue and defaulting to
`fa` together flipped 22 previously-green tests to red on the first `make verify` run,
because they asserted literal English gettext output with no override, riding on the same
accidental gap Decision 3 just closed. Two different fixes, by what each test actually
tests:
- `test_requirements.py`, `test_disclosure.py`, `test_report_markdown.py` (19 of the 22)
  are unit tests of pure Python composition functions (`requirement_text`,
  `disclosure_text`, `render_markdown_report`) whose actual subject is *structure* —
  cardinality picks the right verb, `enumeration` joins as "or" not "and", section
  ordering, injection-safety — not translated wording. Each now carries an explicit,
  local `@pytest.fixture(autouse=True) def english(): with translation.override("en"):
  yield`, replacing the accidental uncompiled-catalogue assumption with a stated, correct
  one, and each docstring was reworded to say so instead of the now-false "not compiled
  outside the container build" claim.
- `test_check_run.py::test_a_check_separates_a_violation_from_missing_data` and
  `test_rule_pack_selection.py::test_the_same_pack_selected_twice_is_refused_as_ambiguous`
  (the other 2 — plus one of the 22 was the pre-existing `reap_stalled` gap, now fixed
  above) are real end-to-end HTTP tests through the actual API. These now assert the real
  Persian substrings ("مجموعه نقشه" for "drawing set", "مبهم" for "ambiguous") rather than
  forcing English, because what a real, headerless request from the real frontend actually
  returns *is* Persian now, and asserting that is more honest than asserting the language
  the product deliberately stopped serving.

### 1. `make verify`

`msgfmt` is not present in this sandbox and there is no root access to `apt-get install`
it (confirmed: `sudo -n apt-get install -y gettext` → "sudo: a password is required").
Used `apt-get download gettext` (works without root — it only fetches the `.deb`, no
`dpkg -i`) and `dpkg-deb -x` to extract `msgfmt` and its two shared libraries into the
scratchpad directory, then ran `make verify` with that directory prepended to `PATH` and
`LD_LIBRARY_PATH` for this shell invocation only — nothing under the repo or a system
location was touched, and this workaround is not part of the deliverable; real CI installs
`gettext` properly via the new "Install gettext" step (Decision 3), and the production
image already does via `deploy/docker/api.Dockerfile`. Final run, from a clean tree state
(re-run after every code change below, this is the last one):

```
$ PATH="<scratchpad>/gettext-local/usr/bin:$PATH" \
  LD_LIBRARY_PATH="<scratchpad>/gettext-local/usr/lib/x86_64-linux-gnu:$LD_LIBRARY_PATH" \
  make verify
uv run ruff check .
All checks passed!
uv run ruff format --check .
187 files already formatted
uv run mypy packages/engine/src services/api/cadgpt
Success: no issues found in 170 source files
uv run lint-imports --no-cache
Analyzed 224 files, 710 dependencies.
I1 - no inference client, web framework or network reaches the checking engine KEPT
The engine knows nothing about the service that hosts it KEPT
Django apps are layered KEPT
Services never import the transport layer KEPT
Models never import services KEPT
Contracts: 5 kept, 0 broken.
cd services/api && uv run --project .. python manage.py compilemessages
File "cadgpt/locale/fa/LC_MESSAGES/django.po" is already compiled and up to date.
uv run pytest
245 passed, 32 warnings in 3.97s
cd services/web && pnpm install --frozen-lockfile && pnpm run verify
✓ 206 modules transformed. / built in 2.30s
Vite ✓ 489 modules transformed. / Storybook build completed successfully
EXIT CODE: 0
```

245 = 242 from T-0085's landed state, + 3 new regression tests
(`test_the_real_lost_dispatch_task_stores_persian_with_no_accept_language_anywhere`,
`test_the_real_stalled_sweep_task_stores_persian_with_no_accept_language_anywhere`,
`test_the_real_execute_check_run_task_stores_persian_for_a_claim_limit_failure`).
`git status --short` after every edit: `.github/workflows/verify.yml`, `Makefile`,
`services/api/cadgpt/apps/base/tasks.py`,
`services/api/cadgpt/apps/review/services/execution.py`,
`services/api/cadgpt/apps/review/tests/{test_check_run,test_disclosure,
test_report_markdown,test_requirements,test_rule_pack_selection}.py`,
`services/api/cadgpt/apps/tenancy/permissions.py`,
`services/api/cadgpt/config/settings/base.py`,
`services/api/cadgpt/locale/fa/LC_MESSAGES/django.po` — no other file touched.

**The new tests are not vacuous — verified by breaking them on purpose.** Temporarily set
`LANGUAGE_CODE = "en"` (leaving `BaseTask`'s explicit activation in place, since it also
reads `settings.LANGUAGE_CODE`) and re-ran the three new tests: all three failed, e.g.
`AssertionError: assert 'This run was claimed...' == 'این اجرا 3 ب...اره متوقف شد.'` for the
`execute_check_run` test. Reverted, re-ran: all three green again. This is the same
"break it on purpose" check T-0085's evidence used for its own new tests' false-positive
direction, applied here to confirm the assertions actually depend on the fix rather than
passing regardless.

### 2. Wiring — the registration lines

**`services/api/cadgpt/config/settings/base.py`**, the one setting every unactivated thread
(including a fresh Celery worker thread) and `LocaleMiddleware`'s no-`Accept-Language`
fallback both resolve against:

```python
LANGUAGE_CODE = "fa"
```

**`services/api/cadgpt/apps/base/tasks.py`**, `BaseTask.__call__` — the one method every
task in this codebase runs through (`execute_check_run`, `generate_report_file`,
`reap_stalled_runs`, `reap_lost_dispatch_runs`, and any task added later, since all inherit
`BaseTask`, quoted from `cadgpt/apps/review/tasks.py`: `@shared_task(base=BaseTask, ...)`
on all four):

```python
    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        bound = log.bind(task=self.name, task_id=getattr(self.request, "id", None))
        bound.info("task_started")
        with translation.override(settings.LANGUAGE_CODE):
            result = super().__call__(*args, **kwargs)
        bound.info("task_finished")
        return result
```

**`Makefile`**, `test`'s new prerequisite:

```
test: compile-messages  ## The whole suite, engine and service
	$(UV) pytest
```

**`.github/workflows/verify.yml`**, the two new steps immediately before `Tests`:

```yaml
      - name: Install gettext
        run: sudo apt-get update && sudo apt-get install --no-install-recommends -y gettext

      - name: Compile message catalogues
        working-directory: services/api
        run: uv run --project .. python manage.py compilemessages
```

### 3. The real path — `make up`, no `Accept-Language` anywhere

Built the image with the required proxy build-args (succeeded), then recreated `api`,
`worker`, `beat` against the real stack (postgres/redis/web left running), with a
`CHECK_RUN_STALL_SECONDS=60` override file for `api`/`worker`/`beat` only — same technique
and same precedent as T-0085's own evidence, to observe the periodic sweep in minutes
instead of the 30-minute production default; identical code path either way.

**A tenant whose `language` is `"en"`, not `"fa"`** — deliberately, via
`TenantProvisioningService().create(name=..., slug=..., owner=owner)` with no `language`
argument (defaults to `"en"`, `services/api/cadgpt/apps/tenancy/services.py:20`), *not* the
real frontend's `CreateWorkspacePage.tsx` call (which does send `language: "fa"`) — so
any Persian shown below cannot be explained by "this tenant happened to choose Persian."
Real services, real fixtures baked into the image (`three_doors.ifc`, `door_width.ids`):
a user, a tenant (`t0083-co`), a review, and a `CheckRun` created via
`CheckRun.objects.create_run` — `PENDING`, `task_id=""`, the exact shape `_dispatch`'s lost
`on_commit` callback leaves — then backdated 120s past the 60s test cutoff, entirely from a
`manage.py shell` invocation: no HTTP request, no `Accept-Language` header, nothing for
`LocaleMiddleware` to ever see.

```
TENANT_LANGUAGE en
RUN_UUID b13ffdec-4256-4ff1-9137-518e7507207d pending
```

**Beat's own tick, unprompted** (`docker compose logs worker`):

```
worker-1  | [...22:50:17,877...] task_started task=review.tasks.reap_lost_dispatch_runs
worker-1  | [...22:50:17,926...] check_run_dispatch_lost_reaped_by_sweep count=1 service=CheckRunExecutor
worker-1  | [...22:50:17,927...] Task review.tasks.reap_lost_dispatch_runs[...] succeeded ...: 1
```

**Read straight back from the database, a fresh `manage.py shell` call, no sweep issued by
that call:**

```
STATUS failed
FAILURE_REASON dispatch_lost
FAILURE_DETAIL 'این بررسی درخواست شد، اما هرگز به کارگری نرسید و از این رو پایان یافت. بررسی را دوباره درخواست کنید.'
TENANT_LANGUAGE en
```

**The `reap_stalled` fix (Decision 2), exercised the same way** — a second run, forced to
`RUNNING` with `started_at` two hours in the past, reaped by the next `reap_stalled_runs`
tick (`stalled_check_runs_reaped count=1`), read back:

```
STATUS failed
FAILURE_REASON stalled
FAILURE_DETAIL 'کارگری که این بررسی را اجرا می‌کرد، از پاسخ‌گویی بازایستاد.'
```

Before this task's fix to `execution.py`, this exact field would have read the bare Python
literal `'The worker running this check stopped responding.'` regardless of any language
setting, because nothing translated it at all.

**The permissions fix (Decision 2), exercised over real HTTP** — logged in as the real
owner via `POST /api/v1/auth/login/`, then two real requests, `curl`, no
`Accept-Language` header on either (curl sends none by default):

Without an `X-Tenant` header, hitting `ReviewViewSet.get_permissions`'s
`IsTenantMemberOrAbove` (`services/api/cadgpt/apps/review/api/v1/views.py`: `if self.action
in {"create", "destroy", "check"}: return [IsTenantMemberOrAbove()]`):

```
HTTP/1.1 403 Forbidden
Content-Language: fa
{"type":"about:blank#permission_denied","status":403,"code":"permission_denied",
 "detail":"نقش شما در این فضای کاری اجازهٔ این کار را نمی‌دهد.", ...}
```

(Before the fix, this was `"detail":"Your role in this workspace does not allow this
action."` — plain English, verified directly against the pre-fix image before rebuilding.)

With `X-Tenant: t0083-co` and the review's one run forced to `RUNNING` (the genuine 409
in-flight conflict, `ReviewService.request_check`'s own `ConflictError`):

```
HTTP/1.1 409 Conflict
Content-Language: fa
{"type":"about:blank#conflict","status":409,"code":"conflict",
 "detail":"بررسی‌ای برای این مورد در حال اجراست.", ...}
```

**Stack restored**: `docker compose -f deploy/compose.yaml up -d --force-recreate api
worker beat` (no override file) before the final `make verify` re-run in §1. Confirmed by
reading settings back inside the running container: `CHECK_RUN_STALL_SECONDS= 1800
LANGUAGE_CODE= fa`.

### 4. The named legitimate-English caller

Checked explicitly, per this task's own instruction, before removing the
`Accept-Language`/`LANGUAGE_CODE`-default dependency. Found one real, empirically-verified
case: `make schema` (`python manage.py spectacular`, writing
`services/web/openapi.yaml`, consumed by `pnpm run generate:api` for the frontend's
generated TS API types). This is a management command with no request either, so it is
subject to the exact same `LANGUAGE_CODE`/`_default` fallback as the worker. Ran it for
real (`manage.py spectacular --file <scratchpad>/openapi-check.yaml`) and grepped the
output for Persian script: **41 lines** now contain Persian text (DRF's own built-in
`OrderingFilter`/pagination parameter descriptions, e.g. "کدام فیلد باید هنگام
مرتب‌سازی نتایج استفاده شود." for "Which field to use when ordering the results." — not
this project's own strings, DRF's).

**What happens to it now:** nothing breaks today. `make schema` is **not** part of `make
verify` or `.github/workflows/verify.yml` (grepped both — `schema` is absent from
`verify`'s prerequisite list and from the CI job), and there is no `services/web/openapi.yaml`
committed to the repository to diff against (checked: `git ls-files | grep -i openapi` and
a filesystem search both come up empty). So the one real consequence is: the *next* person
who runs `make schema` to regenerate the frontend's API types gets a schema with English
structural text (paths, this project's own field names) mixed with Persian for a few
DRF-supplied parameter descriptions, where before this task it was uniformly English. Left
unfixed deliberately — pinning that one dev command to English regardless of the process
default is a different, smaller task (e.g. a `LANGUAGE_CODE=en` env override in the
`schema` Makefile target) than this one, and nothing currently depends on its output being
English, so there is nothing being silently broken, only a latent inconsistency worth
naming for whoever next runs it.

No other legitimate English-dependent caller was found. Checked specifically: Django admin
(`django.contrib.admin` is installed) is not affected in practice, because a real staff
browser sends its own real `Accept-Language` — the only thing that changed is the
no-header *fallback*, and admin is never visited by a client that sends no header at all
the way this product's own SPA does.

### NOT DONE

- **The `make schema` / DRF-parameter-description consequence (§4) is named, not fixed.**
  See above for why: not gated anywhere, nothing committed to diff against, and pinning it
  to English is a separate, smaller task if it turns out to matter once someone actually
  regenerates `services/web/openapi.yaml`.
- **No full-codebase sweep for other ungettexted user-facing strings.** Two were found and
  fixed because the work in this task surfaced them directly (`reap_stalled`'s
  `failure_detail`, `cadgpt/apps/tenancy/permissions.py`'s four `message` attributes) — both
  in the same category CLAUDE.md already mandates ("every user-facing string goes through
  gettext"). No exhaustive search for further instances elsewhere in the codebase was
  attempted; if more exist, they are pre-existing bugs of the same kind, not something this
  task's own diff introduced or is positioned to have caught systematically.
- **`Tenant.language` / `User.language`'s "member override" is unchanged and still
  effectively unreachable.** `ReportGenerationService.generate` already activates
  `translation.override(run.tenant.language)` for the one-time report file render (T-0051,
  pre-existing, not touched by this task), and the real frontend's
  `CreateWorkspacePage.tsx` does send `language: "fa"` when creating a tenant — but
  `User.language` (the documented "member override," `cadgpt/apps/account/models.py:30`)
  is set by `RegisterSerializer` to its own server-side default (`"en"`) and is never read
  anywhere in the request path (grepped: no `.language` reference outside
  `report_generation.py`'s `tenant.language` use and the model/serializer definitions
  themselves) — the "T-0029-era per-request language resolution" `report_generation.py`'s
  own docstring describes for a member's live override does not exist in the code as
  written; the actual per-request mechanism is exactly the `LocaleMiddleware`/
  `LANGUAGE_CODE` default this task hardens. Out of scope for this task (which is about the
  worker having *no* language decision, not about completing an unused per-member
  preference), but worth flagging as a discrepancy between a docstring's claim and the code
  for whoever next touches that file.

## Coordinator audit

Not reviewer-gated (task header: "none directly"), so the coordinator verified this
directly: independently re-ran `make verify` from a clean shell (245 passed, 5/5 contracts,
mypy clean, exit 0 — matches the evidence exactly, using the builder's own no-root
`msgfmt`-extraction workaround, still present in the shared scratchpad), and read every
diff (`base/tasks.py`, `tenancy/permissions.py`, `review/services/execution.py`,
`config/settings/base.py`, `Makefile`, `.github/workflows/verify.yml`, the five touched
test files, the `.po` catalogue).

**No fix-now findings.** The work is unusually thorough on its own: it found and fixed two
real pre-existing `gettext` violations outside this task's own stated scope
(`reap_stalled`'s bare-literal `failure_detail`, four ungettexted DRF permission
`message`s), closed a real testing gap that had let 22 tests pass against an
never-actually-compiled catalogue in every environment including CI, and used
`gettext_lazy` correctly (not eager `gettext`) for the class-attribute `message` fields,
where an eager call would have frozen the wrong language at import time. The three new
regression tests go through the real Celery task dispatch (`.delay()` under
`CELERY_TASK_ALWAYS_EAGER`), assert against a `.mo`-derived expected string rather than a
hand-typed one, and independently guard against the exact vacuous-pass failure mode
(`_is_persian`, refusing an uncompiled-catalogue fallback that would silently match on both
sides). Mutation-verified by the builder's own hand (temporarily reverted `LANGUAGE_CODE`
to `"en"`, confirmed all three new tests fail for the stated reason, restored).

**Two minor items named in the evidence's own NOT DONE, left as notes rather than new
tasks** (per the standing principle of not letting every finding spawn a task file): `make
schema`'s output now mixes English structure with a few DRF-supplied Persian parameter
descriptions — verified to affect nothing in `make verify` or CI, and nothing committed
depends on it. `report_generation.py`'s docstring describes a per-member language override
that was never actually wired into any request path — pre-existing, unrelated to this
task's own diff, a documentation/dead-code discrepancy for whoever next touches that file,
not a regression this task introduced.
