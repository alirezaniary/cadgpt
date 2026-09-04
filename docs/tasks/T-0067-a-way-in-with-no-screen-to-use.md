# T-0067 — There is no screen to become a user: no signup, no first workspace

**Phase:** 3   **Status:** done
**Touches invariants:** tenancy (creates the tenant a user then acts inside; must go through
the existing `TenantProvisioningService` path, not a new one).

## Why

`App.tsx` renders exactly one unauthenticated screen, `SignInPage`. There is no registration
form and no link to one anywhere in `services/web`. The API has carried `POST /v1/auth/register/`
and `POST /v1/tenants/` since Phase 2 — that's how the phase's own evidence was produced, by
curl, never through a browser — but nobody built the UI for either. `report.spec.ts` says this
outright: *"Only account and tenant creation are seeded through the API first ... because the
SPA has no screen for either."*

The consequence is not cosmetic: a person with no account and no invitation has no way to start
using the product at all. And registering alone does not fix it — a freshly registered user has
zero tenants, and `App.tsx`'s workspace `<select>` just renders `workspace.none` with nothing to
click. Confirmed by the product owner: this task covers both gaps together, because closing only
the first still leaves a new user stuck on the second.

No OTP, no email verification — email and password is the whole registration input, matching
what `RegisterSerializer` already accepts (`full_name` and `language` both default).

## Scope

**Changes**

- A registration screen, reachable from `SignInPage` (e.g. a mode toggle or a link — match the
  existing card layout, don't introduce a new visual language). Fields: email, password. Calls
  `POST /v1/auth/register/` via the existing `api` client in `services/web/src/api/client.ts`,
  the same `ApiError` handling pattern `SignInPage.tsx` already uses. On success, sign the user
  in the same way `useSession().signIn` does — either by calling it directly with the same
  credentials, or by having the session layer consume the register response the same way it
  consumes login's, whichever needs less duplication. Do not duplicate the token-handling logic
  in `session.tsx`.
- A first-workspace screen: when `App.tsx` has a signed-in `user` but `tenants.data.results` is
  empty (and the tenant list has finished loading — do not show it while `tenants.data` is
  still undefined), render a minimal form instead of the empty `<select>` — a name field, calling
  `POST /v1/tenants/` via `TenantCreateSerializer`'s fields (`name`, `slug`, `language`). Slug can
  be derived from the name rather than asking for a second field, since nothing downstream
  depends on a specific slug shape beyond `SlugField`'s own validation — your call, but justify it
  in the evidence. On success, call `chooseTenant` with the created tenant so the shell renders
  immediately with no reload.
- New user-facing strings go in both `services/web/src/i18n/en.json` and `fa.json` — this
  product's own rule, not a suggestion; `SignInPage`'s existing keys under `auth.*` are the
  pattern to extend.
- `services/api/cadgpt/apps/tenancy/api/v1/serializers.py`'s `TenantCreateSerializer` and
  `services/api/cadgpt/apps/account/api/v1/serializers.py`'s `RegisterSerializer` are the
  contracts to build against; read them before writing the form, don't guess field names.

**What explicitly does not change**

- No OTP, no email verification, no password-confirmation field, no "forgot password" — out of
  scope, not deferred silently; say so in the evidence if a shortcut here was tempting.
- No invitation flow, no membership-role UI — that's `docs/plan.md`'s already-queued "Invitations
  and roles in the UI" item, not this task.
- `AccountService.register` and `TenantProvisioningService.create` are not touched. This is a
  frontend task against an existing backend contract.

## How to prove it ran

`make verify`, then the real path in a real browser against `make up`: a person with **no**
seeded account — don't use `fixtures.ts`'s API-seeded account for this — opens the app, follows
the registration screen, ends up signed in with the tenant-creation screen (not a broken empty
dropdown), creates a workspace by typing a name, and lands on `ReviewsPage` able to start a
review. Show that sequence, either as a new Playwright spec (`services/web/e2e/`) that does not
use `fixtures.ts`'s pre-seeded account, or as a driven browser session with screenshots at each
step — either way, capture the actual rendered screens, not just the network calls.

## Evidence

### What was built

- `services/web/src/features/auth/RegisterPage.tsx` (new) -- email + password only. Calls
  `POST /v1/auth/register/` through the existing `api` client, catches with the same
  `ApiError` pattern `SignInPage.tsx` uses. `RegisterView.post` (`services/api/cadgpt/apps/
  account/api/v1/views.py`) returns only the created `UserSerializer`, not a token pair, so
  on success this calls `useSession().signIn(email, password)` with the same credentials
  rather than teaching `session.tsx` a second way to plant an access token -- zero lines
  changed in `session.tsx`, per the task's "do not duplicate the token-handling logic".
- `services/web/src/features/auth/SignInPage.tsx` -- takes a new `onRegister: () => void`
  prop and renders one `.link-button` beneath the form ("Need an account? Create account").
  No other change to the sign-in form itself.
- `services/web/src/features/tenancy/CreateWorkspacePage.tsx` (new) -- one `name` field.
  Slug is derived client-side (`slugify()` in the same file: lower-cased, non-`[a-z0-9]`
  runs collapsed to a single hyphen, trimmed, a random 6-character suffix appended and the
  whole thing capped at 63 chars) rather than asking a brand-new user for a second field.
  Justification for the derivation, concretely: `Tenant.slug` is globally `unique=True`
  (`services/api/cadgpt/apps/tenancy/models.py`) but `Tenant.name` is not -- two different
  firms can both type "Acme" -- so a plain slugify-with-no-suffix would let the *second*
  visitor's plausible-sounding name collide with an existing tenant on their very first
  screen. The random suffix trades a human-readable slug for one that will not do that.
  On success, calls `chooseTenant(tenant)` directly with the mutation's response (the
  `TenantSerializer` shape) -- no reload, no extra fetch before the shell can render.
- `services/web/src/api/queries.ts` -- added `useCreateTenant`, same shape as
  `useCreateReview`/`useCreateRuleSet`: a thin `useMutation` wrapper posting to
  `POST /v1/tenants/` and invalidating `keys.tenants` on success so the topbar dropdown
  (for a user who later ends up with more than one tenant) stays in step.
- `services/web/src/app/App.tsx` -- an `authMode` state toggles `SignInPage`/`RegisterPage`
  while `!user`; a new branch renders `CreateWorkspacePage` instead of the shell when
  `!tenant && tenants.data && tenants.data.results.length === 0` (guarded on `tenants.data`
  itself, not just its `.results`, so a first-load fetch in flight does not flash this
  screen at a user who actually has a workspace waiting -- the task's explicit
  requirement).
- `services/web/src/styles.css` -- one addition, `.link-button` (transparent background,
  underlined, `var(--accent)` colour, `font: inherit`) so the sign-in/register toggle reads
  as a text link inside the existing card rather than a second submit-shaped button --
  no new visual language, the existing palette only.
- `services/web/src/i18n/en.json` and `fa.json` -- new keys under the existing `auth.*` and
  `workspace.*` blocks (`auth.register`, `auth.registering`, `auth.registerTitle`,
  `auth.registerPrompt`, `auth.signInPrompt`, `auth.backToSignIn`; `workspace.createTitle`,
  `workspace.createHint`, `workspace.name`, `workspace.create`, `workspace.creating`).
  Every new user-facing string in both files, none left English-only.
- `services/web/e2e/onboarding.spec.ts` (new) -- see "Real path" below.

**Explicitly not touched, per scope:** `session.tsx`'s token handling (untouched, confirmed
by `git diff` below), `AccountService.register`, `TenantProvisioningService.create`, and no
OTP / email verification / password-confirmation / forgot-password / invitation / role UI
was added anywhere.

### `make verify`

```
$ make verify
uv run ruff check .              -> All checks passed!
uv run ruff format --check .     -> 172 files already formatted
uv run mypy packages/engine/src services/api/cadgpt -> Success: no issues found in 156 source files
uv run lint-imports --no-cache   -> Contracts: 5 kept, 0 broken.
uv run pytest                    -> 235 passed, 32 warnings in 6.82s
cd services/web && pnpm install --frozen-lockfile && pnpm run verify
  eslint .          -> clean
  tsc -b --noEmit   -> clean
  tsc -b && vite build -> "✓ 108 modules transformed" / "✓ built in 2.50s"
$ echo $?
0
```

No Python file changed in this task (frontend-only against an existing backend contract),
so `ruff`/`mypy`/`contracts`/`pytest` are the pre-existing baseline, re-run clean; the only
gate this task could plausibly break is `web-verify`, and it is green.

### Real path

`docker compose -f deploy/compose.yaml up --build -d web` (also rebuilt `api`, which compose
recreated as a dependency) against the running `make up` stack, then a new Playwright spec,
`services/web/e2e/onboarding.spec.ts`, driven against `http://localhost:8080` (the built
`web` image behind nginx, same as every other e2e spec, `playwright.config.ts`) -- **not**
`fixtures.ts`'s pre-seeded `account` fixture; this spec imports `test`/`expect` straight from
`@playwright/test` and mints its own unique email inline, exactly the "no seeded account"
case the task asks for.

```
$ npx playwright test e2e/onboarding.spec.ts --project=chromium --reporter=list
Running 1 test using 1 worker
  ✓  1 [chromium] › e2e/onboarding.spec.ts:24:1 › a brand-new person registers, creates a
     workspace and starts a review, entirely in the browser (8.4s)
  1 passed (10.1s)
```

The sequence it drives and asserts on, with a screenshot at each step
(`services/web/e2e/screenshots/onboarding-{1..4}.png`, all captured this run):

1. `page.goto("/")` -> sign-in screen (`SignInPage`, heading "CADGPT" visible) -> clicks the
   new "Create account" link.
2. Lands on `RegisterPage` ("Create an account" subtitle visible). Fills a freshly-minted
   email (`onboarding-<timestamp>-<rand>@cadgpt.test`) and a password, submits.
   **Screenshot 1** (`onboarding-1-register.png`) shows the filled form before submit.
3. `RegisterPage` posts to `/v1/auth/register/`, then calls `signIn` with the same
   credentials. The app immediately shows `CreateWorkspacePage` -- asserted by both the
   "Create your first workspace" heading *and* `expect(page.locator("#workspace")).
   toHaveCount(0)`, i.e. the old broken empty `<select>` is provably not what rendered.
   **Screenshot 2** (`onboarding-2-first-workspace.png`) -- one name field, one button, no
   dropdown anywhere on the page.
4. Types a workspace name, clicks "Create workspace". `POST /v1/tenants/` succeeds,
   `chooseTenant` is called with the response, and the shell renders with **no reload** --
   asserted via `expect(page.locator("select#workspace option")).toHaveText([workspaceName])`,
   i.e. the dropdown's one option is the tenant that was just created, not a stale/empty
   list. **Screenshot 3** (`onboarding-3-reviews-shell.png`) shows the topbar with the new
   workspace selected and the `Reviews`/`Rule sets` cards rendered underneath.
5. On `ReviewsPage`: uploads a rule set (`door_width.ids`), creates a review against it with
   a real IFC (`three_doors.ifc`, the same fixtures `report.spec.ts` uses), clicks "Run
   check", waits for the run to reach a terminal state, opens the summary. Asserts the real
   three-valued counts off the rendered report: 1 pass / 1 fail / 1 indeterminate.
   **Screenshot 4** (`onboarding-4-report.png`) shows the completed report -- door width
   FAIL (800mm vs 900mm minimum) and INDETERMINATE (no width recorded), the same fixture
   shape `report.spec.ts` already established, now reached from a cold start with zero
   pre-seeded state.

Full suite re-run afterward to confirm no regression to the specs this task did not touch:

```
$ npx playwright test --project=chromium --reporter=list
Running 4 tests using 4 workers
  ✓  upload-limit.spec.ts       (16.7s)
  ✓  onboarding.spec.ts         (20.2s)
  ✓  report-recovery.spec.ts    (22.7s)
  ✓  report.spec.ts             (24.8s)
  4 passed (27.5s)
```

### Wiring

- The toggle that makes `RegisterPage` reachable, `services/web/src/app/App.tsx`:
  `return authMode === "signIn" ? (<SignInPage onRegister={() => setAuthMode("register")} />) : (<RegisterPage onSignIn={() => setAuthMode("signIn")} />);`
- The first-workspace screen's guard, same file:
  `if (!tenant && tenants.data && tenants.data.results.length === 0) { return <CreateWorkspacePage />; }`
- Registration reusing the session's own sign-in path rather than a new one,
  `services/web/src/features/auth/RegisterPage.tsx`:
  `await api.post("/v1/auth/register/", { email, password }); await signIn(email, password);`
- The mutation backing workspace creation, registered in the same query-key space every other
  mutation here uses, `services/web/src/api/queries.ts`:
  `mutationFn: (payload) => api.post<Tenant>("/v1/tenants/", payload), onSuccess: () => client.invalidateQueries({ queryKey: keys.tenants }),`
- Backend routes this frontend calls, unchanged, already registered before this task
  (confirmed present, not re-wired): `services/api/cadgpt/apps/account/api/v1/urls.py`:
  `path("auth/register/", RegisterView.as_view(), name="register"),`; `services/api/cadgpt/
  apps/tenancy/api/v1/urls.py`: `router.register("tenants", TenantViewSet, basename="tenant")`.

### NOT DONE

Nothing from this task's scope. Explicitly out of scope and not built, per "What explicitly
does not change": OTP, email verification, a password-confirmation field, "forgot password",
any invitation flow, and any membership-role UI. No shortcut was taken in place of any of
these -- they are simply absent, as specified.

One judgement call, not a gap: `TenantCreateSerializer.slug` is a required field with no
server-side derivation, so the frontend must supply *some* value. The random-suffix
client-side derivation above is not the only valid choice (a server-side slug-from-name
endpoint would be another), but it needed no backend change, matches "your call, but justify
it in the evidence", and is exercised for real in the browser test above (not just unit
logic) -- the created tenant's slug is what the topbar's `#workspace` `<select>` ends up
keyed on.

## Addendum — 2026-09-04, both fix-now review findings closed

Both fix-now findings from the review round below are fixed, mutation-tested (each fix was
temporarily reverted, proven to make its own kill test fail against a freshly rebuilt
container, then restored and reproven green), and re-verified against a freshly rebuilt
`web`/`api` pair. The two MEDIUM findings queued as T-0068/T-0069 were left untouched, as
instructed.

### 1. HIGH — `signOut` now clears the TanStack Query cache

**Fix**, `services/web/src/app/session.tsx`:

```ts
import { useQueryClient } from "@tanstack/react-query";
...
  const queryClient = useQueryClient();
...
  const signOut = useCallback(async () => {
    await api.post("/v1/auth/logout/");
    setAccessToken(null);
    setUser(null);
    setTenantState(null);
    setTenant(null);
    localStorage.removeItem(LAST_TENANT_KEY);
    queryClient.clear();
  }, [queryClient]);
```

`SessionProvider` already renders inside `QueryClientProvider` (`services/web/src/main.tsx`:
`<QueryClientProvider client={queryClient}><SessionProvider>`), so `useQueryClient()` reaches
the same client instance every query in the app uses -- no new client, no prop threading.
`.clear()` rather than enumerating query keys: the reviewer's own point was that keys are not
user-scoped today, so any allowlist of keys to invalidate is exactly the kind of thing that
misses the next one added later. Nothing else in `signOut` changed.

**Real, mutation-tested proof.** A new spec, `services/web/e2e/session-isolation.spec.ts`,
test 1 ("signing out clears the previous user's cached tenant and rule-set data before the
next person signs in on the same tab"): user A registers, creates a workspace, uploads a rule
set, signs out; user B registers a *different* brand-new account in the *same tab* (no new
browser context -- a new context would sidestep the cache entirely and prove nothing) and the
spec asserts B's dropdown shows only B's tenant, A's tenant name appears nowhere on the page,
and the rule-sets list is empty, not a stale render of A's rule set.

Kill test, `queryClient.clear()` line removed, `web`/`api` rebuilt fresh
(`docker compose -f deploy/compose.yaml up --build -d web`, confirmed via
`docker inspect -f '{{.State.StartedAt}}' cadgpt-web-1` postdating the edit):

```
✘  session-isolation.spec.ts:36 signing out clears the previous user's cached tenant ...
   Error: expect(locator).toBeVisible() failed
   Locator: getByRole('heading', { name: 'Create your first workspace' })
   Timeout: 15000ms
   Error: element(s) not found
```

Without the clear, user B never even reaches the first-workspace screen -- B lands straight
on a shell carrying A's stale, cached tenant list, which is worse than the reviewer's own
description (not just stale data rendered, but the acceptance-criterion screen skipped
entirely for a user with a stale non-empty cache). Fix restored, same rebuild step, full spec
green again:

```
✓  session-isolation.spec.ts:36 signing out clears the previous user's cached tenant and
   rule-set data before the next person signs in on the same tab (17.3s)
```

Screenshots from the passing run, both captured this session:
`services/web/e2e/screenshots/isolation-1-user-a-data.png` (A's rule set, A's tenant name in
the dropdown) and `isolation-2-user-b-clean-slate.png` (B's shell: dropdown reads "Tenant B
...", no "Tenant A" text anywhere on the page, "Rule sets" card empty, "Reviews" card empty).

**Incidental, unrelated observation, not fixed here (out of this round's scope):**
`isolation-1-user-a-data.png` shows a stray "Something went wrong." banner above the Rule
sets card even though the rule set itself was created successfully (it is visible in the same
screenshot and the spec's own assertion on it passed). `ReviewsPage.onAddRuleSet` calls
`event.currentTarget.reset()` after `await createRuleSet.mutateAsync(...)` resolves; if a
re-render has already detached that form node by then, `.reset()` throws a plain (non-`ApiError`)
exception, which lands in the same `catch` and renders `error.generic` even though the mutation
itself succeeded. Unrelated to either fix-now finding, does not affect either repro's outcome
(both spec assertions pass regardless), and not something this round's instructions cover --
noted rather than silently left out of the record, not fixed.

### 2. MEDIUM (falsified the evidence) — `App.tsx` no longer flashes a zero-option `select#workspace`

**Fix**, `services/web/src/app/App.tsx`:

```tsx
const tenantList = tenants.data;
if (!tenant && !tenantList) return <main className="centered" />;
if (!tenant && tenantList && tenantList.results.length === 0) {
  return <CreateWorkspacePage />;
}
```

(`tenants.data` is read into a local `const` because TypeScript could not narrow the repeated
property access across the two `if`s on its own -- `tsc -b --noEmit` flagged `'tenants.data'
is possibly 'undefined'` on the first attempt; the local binding fixes the narrowing and
`make verify`'s `web-verify` gate now passes clean.) The new first line is exactly the
reviewer's prescribed fix: while `!tenant`, do not fall through to the shell until
`tenants.data` has actually loaded -- show the same loading state `!ready` already uses, then
branch to `CreateWorkspacePage` or the shell once data is present.

**Real, mutation-tested proof -- and a genuine test-design bug found and fixed along the
way.** Test 2 in `session-isolation.spec.ts` ("the workspace dropdown never renders with zero
options while the tenant list is still loading") holds the tenant-list `GET` open for 1.5s via
`page.route` after a fresh registration, then samples `page.locator("#workspace").count()`.

The first version of this test used `expect(locator).toHaveCount(0)` and passed against
*both* the mutated (bug-reproducing) code and the fixed code -- a false green. Diagnosed live
with instrumented console logging against the actual running stack: `toHaveCount(0)` is a
*retrying* web-first assertion, and even with the bug present it eventually becomes true --
once the delayed fetch resolves with zero tenants, the mutated code moves on to
`CreateWorkspacePage`, which also renders no `#workspace` (it has none to render). The retry
walks straight past the buggy intermediate window (`select#workspace` present with zero
`<option>`s, confirmed directly: `count=1` sampled every 150-200ms for the full 1.5s delay
under the mutated code) into the later, coincidentally-also-selector-free state, and reports
success. Rewritten to a non-retrying point-in-time check instead --
`expect(await locator.count()).toBe(0)`, a plain-value assertion that does not poll -- which is
what a "never during this window" claim actually requires:

```ts
for (let i = 0; i < 5; i += 1) {
  const count = await page.locator("#workspace").count();
  expect(count, `select#workspace must not exist while the tenant list is still loading (iteration ${i})`).toBe(0);
  await page.waitForTimeout(200);
}
```

A second, real environmental fact surfaced during this diagnosis and is now encoded as an
explicit wait rather than an assumption: registration + login together took ~2.5-2.8s in this
session (real `bcrypt`/PBKDF2 hashing plus this host's other running containers), longer than
the original 1-1.5s assertion loop -- so an early version of the test's loop ran entirely
*during* the register/login round trip, before the tenants fetch even started, and would have
passed vacuously for that reason too. The test now asserts registration actually completed
(`"Create an account"` text gone, `.error` absent) before starting the sampling loop.

A third, unrelated false-failure cause was also found and fixed in the same pass: the test's
original passwords (`"IsolationA!2026-e2e"` next to email local part `isolation-a-...`,
`"NoFlash!2026-e2e"` next to `no-flash-...`) were lexically similar enough to their emails to
occasionally trip Django's `UserAttributeSimilarityValidator`
(`AUTH_PASSWORD_VALIDATORS`, `services/api/cadgpt/config/settings/base.py`) -- confirmed live
via a throwaway diagnostic spec: `{"detail":"The password is not acceptable.","errors":
{"password":["The password is too similar to the email address."]}}`. All passwords in this
file are now lexically unrelated to their email local parts (`"Guarded#2026-HarnessA"` /
`"Guarded#2026-HarnessB"` / `"Guarded#2026-Harness"`), matching the already-safe pattern
`fixtures.ts` and `onboarding.spec.ts` use.

With the *corrected* test (non-retrying assertion, registration-completed gate, safe
passwords), the kill test against the mutated code (the loading-guard line removed, `web`/`api`
rebuilt fresh, confirmed via container start time postdating the edit) now fails for the right
reason:

```
✘  session-isolation.spec.ts:112 the workspace dropdown never renders with zero options
   while the tenant list is still loading
   Error: select#workspace must not exist while the tenant list is still loading (iteration 0)
   expect(received).toBe(expected)
   Expected: 0
   Received: 1
```

Fix restored, same rebuild step, green again:

```
✓  session-isolation.spec.ts:112 the workspace dropdown never renders with zero options
   while the tenant list is still loading (7.0s)
```

### Re-run gates and full suite, against the final, correctly-fixed, freshly rebuilt container

```
$ make verify
uv run ruff check .              -> All checks passed!
uv run ruff format --check .     -> 172 files already formatted
uv run mypy packages/engine/src services/api/cadgpt -> Success: no issues found in 156 source files
uv run lint-imports --no-cache   -> Contracts: 5 kept, 0 broken.
uv run pytest                    -> 235 passed, 32 warnings in 7.71s
cd services/web && pnpm run verify -> eslint clean, tsc -b --noEmit clean, vite build succeeded
$ echo $?
0
```

```
$ docker compose -f deploy/compose.yaml up --build -d web
 api  Built
 web  Built
 Container cadgpt-web-1  Recreated / Started
$ npx playwright test --project=chromium --reporter=list
Running 6 tests using 4 workers
  ✓ session-isolation.spec.ts:36  signing out clears the previous user's cached tenant and
    rule-set data before the next person signs in on the same tab (17.3s)
  ✓ onboarding.spec.ts:24         a brand-new person registers, creates a workspace and
    starts a review, entirely in the browser (17.6s)
  ✓ report-recovery.spec.ts:47    the recovery button's own POST is what moves a pending
    report to failed (22.9s)
  ✓ upload-limit.spec.ts:13       the model size ceiling is stated at upload time, in
    English and Persian (6.8s)
  ✓ session-isolation.spec.ts:112 the workspace dropdown never renders with zero options
    while the tenant list is still loading (7.1s)
  ✓ report.spec.ts:40             a real check run reproduces 1 pass / 1 fail / 1
    indeterminate in the browser (27.1s)
  6 passed (29.7s)
```

No regression to either spec this task's first round already established (`onboarding.spec.ts`,
`report.spec.ts`, `report-recovery.spec.ts`, `upload-limit.spec.ts`).

### Wiring, both fixes

- `services/web/src/main.tsx`: `<QueryClientProvider client={queryClient}><SessionProvider>`
  -- confirms `useQueryClient()` inside `session.tsx` resolves to the one client instance
  every query (`useTenants`, `useRuleSets`, `useReviews`, ...) reads from, so `.clear()`
  reaches all of them, not a second, disconnected client.
- `services/web/src/app/App.tsx`: the guard quoted above, between the `!user` branch and the
  shell's `return (`.

### NOT DONE (unchanged from the first round, plus nothing new)

Still nothing from this task's own scope. The two MEDIUM findings from the review
(membership-revocation mid-session, `slugify`'s non-Latin collapse, `RegisterPage` never
sending `language`) are intentionally not addressed here -- they are queued as
`docs/tasks/T-0068-a-failure-with-no-reason-given.md` and
`docs/tasks/T-0069-onboarding-edges-the-happy-path-skips.md`, per the coordinator's explicit
instruction not to re-litigate them in this round.

## Review

Gated on the tenancy invariant. Verified clean: `make verify` reproduced independently, i18n key
sets identical in both locales, `session.tsx` untouched as claimed, server-side tenancy holds
(`for_user`/`_lookup` reject a forged `X-Tenant`), `onboarding.spec.ts` is an honest test of the
real DOM. Four findings survived; two falsify the evidence block itself.

**Fix now — same task, same builder:**

1. **HIGH, invariant-adjacent.** `session.tsx`'s `signOut` clears the user, tenant and access
   token but never clears the TanStack Query cache. Query keys are not user-scoped, so the next
   person to sign in on the same tab renders off the previous user's cached tenant name and rule
   sets — live-reproduced. It also falsifies this task's own acceptance criterion: with a stale
   non-empty `tenants` cache, `CreateWorkspacePage` never renders for the new user at all: they
   land on a shell keyed to a workspace they cannot use, recoverable only by an undiscoverable
   page reload.
2. **MEDIUM, falsifies the evidence.** `App.tsx`'s guard, `!tenant && tenants.data && tenants.
   data.results.length === 0`, falls through to the shell while `tenants.data` is still `undefined`
   (the fetch in flight) — rendering `select#workspace` with **zero options** for the fetch's
   duration on every fresh registration. That is exactly the broken empty dropdown this task
   exists to remove; the evidence block's claim that `CreateWorkspacePage` renders "immediately"
   is true only after the auto-retrying Playwright assertion outlasts the transient window.

**Queued — new task files, not fixed here:** T-0068 (registration's failure path is silent —
password policy and duplicate-email never explained, and the register/login throttle bucket can
strand a user mid-signup with no recovery messaging), T-0069 (three related edges: a user whose
last membership is revoked mid-session has no way back to `CreateWorkspacePage` without a reload;
`slugify`'s stem collapses for any non-Latin name, weakening the collision-avoidance argument;
`RegisterPage` never sends `language`, so a Persian-UI signup still gets English error copy).
