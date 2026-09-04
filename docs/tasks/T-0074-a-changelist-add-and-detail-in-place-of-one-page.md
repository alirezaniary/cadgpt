# T-0074 — a changelist, an add form, and a detail view, in place of one page

**Phase:** 3   **Status:** done
**Touches invariants:** none — frontend-only, no rule evaluation, no tenancy-boundary
change (every new call still goes through the same tenant-scoped endpoints).
**Depends on:** T-0073 (the `Project` API this task routes against — do not start until
T-0073's evidence block shows the endpoints working for real).

## Why

The product owner rejected the single-page dashboard outright: rule sets, reviews, runs
and reports all lived on one page, reviews just accumulated in a flat `<li>` list forever,
and the summary view read as an unstyled dump. The requested shape, given explicitly and
twice: *"it had an add and change form, a list view and a detail view, organized, not like
this all in one page"* — Django admin's structure, minus its visual style. Concretely:
**a list of projects, an add-project form, and inside a project a list of its reviews with
its own add-review form, and inside a review its own detail page carrying the run/report.**
`@tanstack/react-router` is already a declared dependency in `package.json` and is wired up
nowhere — this task is what finally uses it.

## Scope

**Routing — new `src/app/router.tsx`, replacing the conditional-render body of `App.tsx`.**
`App.tsx` keeps the topbar/user-menu shell (untouched by T-0072) as the router's root
route layout, wrapping an `<Outlet />` where `ReviewsPage`'s whole tree used to sit.
Routes:

- `/` → redirect to `/projects`.
- `/projects` — `ProjectsListPage`: a table (name, review count, created date), an
  "افزودن پروژه" button that navigates to `/projects/new`, row click navigates to
  `/projects/:projectUuid`.
- `/projects/new` — `ProjectAddPage`: one field, the project's name. Submit calls
  `useCreateProject`, then navigates to the new project's detail page — Django admin's
  "save and continue editing," not back to the list.
- `/projects/:projectUuid` — `ProjectDetailPage`: the project's name as a heading, a table
  of its reviews (name, model filename, status, outcome pill, latest run date), an "افزودن
  بررسی" button to `/projects/:projectUuid/reviews/new`, row click to
  `/projects/:projectUuid/reviews/:reviewUuid`. Reviews come from `useReviews(tenant,
  projectUuid)` — see below.
- `/projects/:projectUuid/reviews/new` — `ReviewAddPage`: name + model file upload only.
  **No rule-set picker here** — per `docs/decisions.md`'s 2026-09-04 entry, rule-set
  upload is removed from the UI entirely; every review created from here has no `rule_set`
  of its own, so it always takes the catalogue path. Submit calls `useCreateReview` with
  the project's uuid, then navigates to the new review's detail page.
- `/projects/:projectUuid/reviews/:reviewUuid` — `ReviewDetailPage`: the review's name and
  model filename as a heading; the catalogue picker (jurisdiction/region/version filter +
  pack checkboxes) and "run check" action, moved here unchanged from today's
  `ReviewsPage`; a list of this review's past runs (status, outcome, date); and, inline
  below that, the currently-open run's report — `ReportView`, `useCheckRun`, the
  report-file download/generate affordances, all moved here verbatim from `ReviewsPage`.
  This is the "detail of each review... the result and stuff" the product owner asked for
  — the report lives on the review's own page, not the tenant's single dashboard.

**`src/api/types.ts`** — add `Project` (`uuid`, `name`, `created_at`, `review_count`).
`Review` gains `project: string` (the project's uuid).

**`src/api/queries.ts`**:
- `keys.projects`, `keys.project`.
- `useProjects(tenant)` — `GET /v1/projects/`.
- `useProject(tenant, uuid)` — for the detail page's heading; `GET /v1/projects/{uuid}/`
  (or reuse the list's cached page if that is cheaper — either is fine, this is not a
  perf-sensitive path yet).
- `useCreateProject(tenant)` — `POST /v1/projects/`, invalidates `keys.projects`.
- `useReviews(tenant, projectUuid)` — add the second parameter, `GET
  /v1/reviews/?project={projectUuid}` (T-0073's `ReviewFilterSet` addition), key becomes
  `["reviews", tenant, projectUuid]`.
- `useCreateReview` — add `project: string` to its payload type and request body,
  **remove** `ruleSet` from both (no caller passes one anymore).
- **Delete** `useRuleSets` and `useCreateRuleSet` entirely, and `RuleSet` from
  `api/types.ts` if nothing else references it — grep first; if something still does,
  leave the type and only delete the two hooks.

**`src/features/review/ReviewsPage.tsx`** is deleted. Its contents split across
`src/features/project/ProjectsListPage.tsx`, `ProjectAddPage.tsx`, `ProjectDetailPage.tsx`,
and `src/features/review/ReviewAddPage.tsx`, `ReviewDetailPage.tsx` (new files) roughly
along the boundaries described above. Move logic, do not rewrite it — `onCheck`,
`togglePack`, `catalogueFilter`, the report-file download/generate handlers, and
`ReportView`'s usage are all already correct and only need to move to
`ReviewDetailPage.tsx`.

**Report styling** (`src/components/ReportView.tsx`, `src/styles.css`) — this is a design
pass, not a restructure:
- The disclosure paragraph (`report.disclosure_text`, server-authored, sometimes English)
  gets its own bordered callout (`.disclosure` already exists in `styles.css` — check
  whether it is actually applied to this paragraph today; the live screenshot taken this
  session shows it rendering as bare unstyled text, so either the class is missing from
  the JSX or the rule isn't matching — find out which and fix that, not just the CSS).
- The three `.count--pass`/`.count--fail`/`.count--indeterminate` tiles already use the
  right token variables (`--pass-bg` etc., confirmed in `:root`) — the "bullshit" flagged
  here was their visual weight relative to the rest of the page, not wrong colors. Bring
  their padding/radius/typography in line with `.card` so they read as part of the same
  system rather than three loose swatches.
- `.entities` (the findings table) keeps its GUIDs but gets real column alignment —
  check the current `td` styling actually produces aligned columns at the viewport widths
  a real report renders at; the live screenshot this session showed ragged wrapping.

**i18n** (`en.json`, `fa.json`) — add `project.title`, `project.new`, `project.name`,
`project.reviewCount`, `project.empty`, and whatever the split pages need that
`review.*` doesn't already cover. Delete `ruleSet.*` keys that no longer render anywhere
(grep to confirm) and `review.ruleSetNone` (the removed `<select>`'s empty option).

**What explicitly does not change:** the topbar/user-menu (T-0072), the auth pages, the
create-first-workspace page, the catalogue-picker's own behavior, `ReportView`'s data
contract, the backend (T-0073 already landed it; this task only calls it).

## How to prove it ran

```sh
pnpm run lint && pnpm run typecheck && pnpm run build   # make web-verify
```

Then the real path, rebuilt container, real browser:

```sh
docker compose -f deploy/compose.yaml up --build -d web
```

Drive it with Playwright (ad hoc or as rewritten e2e specs — the existing suite's selectors
targeting `ReviewsPage`'s single-page flow will not survive this task and need rewriting,
same as T-0072 rewrote them for the avatar menu): register, land on `/projects`, create a
project, land on its detail page with an empty review list, create a review with a real
IFC file, land on the review's detail page, pick catalogue packs, run a check, watch it
reach a terminal status, and see the report render inline with the disclosure box actually
boxed. Screenshot each of the five pages and paste them here, or describe pixel-verified
differences from this session's `live-main.png`/`report.png` if screenshots are not
attachable to the task file directly.

## Evidence

### `make verify`

```
$ make verify
uv run ruff check .                 -> All checks passed!
uv run ruff format --check .        -> 185 files already formatted
uv run mypy packages/engine/src services/api/cadgpt   -> Success: no issues found in 169 source files
uv run lint-imports --no-cache      -> Contracts: 5 kept, 0 broken.
uv run pytest                       -> 235 passed, 32 warnings in 3.85s
cd services/web && pnpm install --frozen-lockfile && pnpm run verify
  eslint .          -> clean
  tsc -b --noEmit   -> clean
  tsc -b && vite build:
    dist/assets/index-D7JgSwE0.css   12.19 kB
    dist/assets/index-CXoDT9sN.js   401.80 kB
    ✓ built in 2.37s
```
Exit code 0. The backend suite (235 tests) is untouched by this task and still green — this
task added and moved no backend code, per its own "what explicitly does not change."

### Real path — rebuilt container, real browser, full e2e suite

```
$ docker compose -f deploy/compose.yaml up --build -d
$ docker compose -f deploy/compose.yaml exec -T api python manage.py seed_rule_packs
skipped (already seeded): Accessible door width (sample)
skipped (already seeded): Door name recorded (sample)
skipped (already seeded): No doors permitted (sample)
done: 0 created, 3 skipped, 4 rule packs in the catalogue
```
(The catalogue was already seeded from an earlier session; the command is idempotent and
this run proves it stays that way. "4 rule packs" because this long-lived dev database also
carries a stray "Accessible door width" v0.2 pack from earlier manual testing — real,
pre-existing data, not something this task created; the e2e specs disambiguate against it by
filtering on "v0.1", the version the fixture on disk actually declares.)

```
$ cd services/web && npx playwright test --project=chromium --reporter=list --workers=1

Running 6 tests using 1 worker

  ✓  1 [chromium] › e2e/onboarding.spec.ts:25:1 › a brand-new person registers, creates a workspace and walks every project/review route, entirely in the browser (5.7s)
  ✓  2 [chromium] › e2e/report-recovery.spec.ts:42:1 › the recovery button's own POST is what moves a pending report to failed (8.1s)
  ✓  3 [chromium] › e2e/report.spec.ts:34:1 › a real check run reproduces 1 pass / 1 fail / 1 indeterminate in the browser (5.7s)
  ✓  4 [chromium] › e2e/session-isolation.spec.ts:43:1 › signing out clears the previous user's cached tenant and project data before the next person signs in on the same tab (4.9s)
  ✓  5 [chromium] › e2e/session-isolation.spec.ts:127:1 › the workspace dropdown never renders with zero options while the tenant list is still loading (3.7s)
  ✓  6 [chromium] › e2e/upload-limit.spec.ts:19:1 › the model size ceiling is stated at upload time (3.0s)

  6 passed (32.2s)
```
Reproduced twice in a row with the same result, after the two real bugs below were fixed.

All five specs that targeted the old single-page `ReviewsPage` (`onboarding`,
`report`, `report-recovery`, `session-isolation`, `upload-limit`) were rewritten for the
project → review → review-detail route split, following T-0072's precedent: real Persian UI
copy, real routes, no mocked frontend state. `report.spec.ts` now drives the review through
the catalogue picker (the rule-set-upload path it used to exercise no longer exists in the
UI) against the catalogue's seeded "Accessible door width" (sample, v0.1) pack — the same
`door_width.ids` fixture, so the same 1 pass / 1 fail / 1 indeterminate assertions, the same
reason codes, the same requirement-text and applicability-text assertions, the same
severity-ordering and filter-banner assertions all still hold, now against the review's own
detail page instead of an inline card on a shared dashboard.

**Two real bugs found by running the actual stack, not by reading the diff:**

1. **Cross-tenant stale route after sign-out.** `session-isolation.spec.ts`'s first run
   (before either fix below) failed: after user A signed out and user B registered fresh on
   the same tab, the shell rendered an error banner and an *empty-reviews* project-detail
   page instead of the expected `/projects` changelist. Screenshot at the time
   (`test-results/.../test-failed-1.png`, not committed) showed the topbar and an "افزودن
   بررسی" button with "خطایی رخ داد" (a generic error) above "هنوز بررسی‌ای نیست" — the
   router had never left the URL `/projects/<tenant-A's-project-uuid>` that was on screen
   when A signed out, so after B's session became ready the same route matched again, now
   under B's `X-Tenant` header, and `useProject`/`useReviews` 404'd against a project B
   does not own. Tenant scoping correctly refused the data (no leak), but the page itself
   was broken. Root cause: neither sign-out nor an explicit workspace switch ever reset the
   router's location. Fixed in `App.tsx`: the sign-out handler now also calls
   `navigate({ to: "/" })`, and the workspace-switch handler calls
   `navigate({ to: "/projects" })` — both applied only to the explicit, user-initiated
   transitions, not to the automatic first-tenant auto-select effect (which must not disturb
   a deep-linked URL). Re-run after the fix: green, screenshots below confirm a clean
   `/projects` changelist for the new user.

2. **The "run check" button and the run-history row read stale after a run had actually
   succeeded.** Manually inspecting `report.png` from the first passing run showed the
   catalogue picker's submit button still reading "در حال بررسی…" (Checking…) and the
   run-history table still reading "در صف" (Queued) *while the report below them was
   already fully rendered* with real pass/fail/indeterminate counts and a working download
   link. Root cause: `ReviewDetailPage`'s `busy` flag was derived from the separately-polled
   `useCheckRuns` list snapshot (2s interval, started on its own clock) rather than the
   currently-open run's own live status (`useCheckRun`, 1.5s interval, already showing
   "succeeded" — that status is exactly why the report was rendering). Fixed by deriving
   `busy` from the open run's own live status when one is open, falling back to the list
   snapshot only when none is. Re-run after the fix (screenshot below): the button reads "اجرای
   بررسی با بسته‌های انتخاب‌شده" again, re-enabled, at the same instant the report is
   showing real results. The run-history *row's* own status/outcome text can still lag the
   live run by up to ~2s (its own independent poll) — cosmetic, self-correcting, and the
   same class of eventual consistency the pre-existing `useReviews`/`useCheckRun` pair
   already had; not treated as a bug.

### Screenshots (all in `services/web/e2e/screenshots/`, produced by the real suite above)

- `onboarding-1-register.png`, `onboarding-2-first-workspace.png` — unchanged auth flow.
- `onboarding-3-projects-list.png` — route 1/5, `/projects`: empty changelist, "پروژه‌ها"
  heading, "افزودن پروژه" button.
- `onboarding-4-project-add.png` — route 2/5, `/projects/new`: one field ("نام"), filled
  with the test's project name, "ایجاد پروژه" submit.
- `onboarding-5-project-detail.png` — route 3/5, `/projects/:uuid`: the new project's name
  as the heading, empty reviews table, "افزودن بررسی" button — landed here directly after
  create, not back on the list ("save and continue editing").
- `onboarding-6-review-add.png` — route 4/5, `/projects/:uuid/reviews/new`: name + IFC file
  fields only, model-size hint ("حداکثر 126.0 MB برای هر مدل."), **no rule-set picker**.
- `onboarding-7-review-detail-report.png` — route 5/5, `/projects/:uuid/reviews/:uuid`: the
  catalogue picker, the run-history table, and the rendered report all on one page, full
  page screenshot.
- `report.png` (from `report.spec.ts`, the canonical evidence shot): confirms, on the real
  rebuilt image, that (a) the disclosure paragraph now sits inside a visibly bordered
  callout (`getComputedStyle(...).borderInlineStartWidth === "3px"`, asserted in the spec
  itself, not just eyeballed), (b) the three pass/fail/indeterminate tiles now share
  `.card`'s padding, radius and shadow instead of reading as three flat swatches, and (c)
  the findings table's five columns (pill, IFC class, GUID, reason, detail) line up cleanly
  under `table-layout: fixed` instead of wrapping raggedly.
- `isolation-1-user-a-data.png` / `isolation-2-user-b-clean-slate.png` — user A's project
  visible on their own detail page, then user B's empty `/projects` changelist on the same
  tab after sign-out, proving the query-cache-clear fix (T-0067) still holds through the
  new routes.

Additionally (ad hoc, via a throwaway Playwright script, not committed — same practice
T-0072 used for its menu-open screenshot): a *populated* `/projects` row read
`adhoc-project-1788539576483 | 1 | ۱۳ شهریور ۱۴۰۵، ۲۰:۰۲` under the "نام / بررسی‌ها / تاریخ
ایجاد" headers, and the corresponding project's reviews table read `adhoc-review-...  |
three_doors.ifc | تمام‌شده | مردود (pill) | ۱۳ شهریور ۱۴۰۵، ۲۰:۰۲` under "نام / پروندهٔ مدل
/ وضعیت / نتیجه / آخرین اجرا" — both changelist tables carry exactly the columns the task
specified, with real data, real formatting, and correct RTL column order.

### Wiring

`services/web/src/main.tsx`:
```tsx
<RouterProvider router={router} />
```
inside `<SessionProvider>`, replacing the previous direct `<App />` render.

`services/web/src/app/router.tsx` — every route from the task's Scope section, registered:
```tsx
const indexRoute = createRoute({ getParentRoute: () => rootRoute, path: "/", beforeLoad: () => { throw redirect({ to: "/projects" }); } });
const projectsRoute = createRoute({ getParentRoute: () => rootRoute, path: "/projects", component: ProjectsListPage });
const projectNewRoute = createRoute({ getParentRoute: () => rootRoute, path: "/projects/new", component: ProjectAddPage });
const projectDetailRoute = createRoute({ getParentRoute: () => rootRoute, path: "/projects/$projectUuid", component: ProjectDetailPage });
const reviewNewRoute = createRoute({ getParentRoute: () => rootRoute, path: "/projects/$projectUuid/reviews/new", component: ReviewAddPage });
const reviewDetailRoute = createRoute({ getParentRoute: () => rootRoute, path: "/projects/$projectUuid/reviews/$reviewUuid", component: ReviewDetailPage });
export const router = createRouter({ routeTree: rootRoute.addChildren([indexRoute, projectsRoute, projectNewRoute, projectDetailRoute, reviewNewRoute, reviewDetailRoute]) });
```

`services/web/src/app/App.tsx`:
```tsx
<Outlet />
```
is the root route's own layout body (`createRootRoute({ component: App })`), sitting where
`<ReviewsPage />` used to render directly.

`services/web/src/api/queries.ts` — `useCreateReview`'s request body carries `project`,
matching T-0073's now-required `ReviewCreateSerializer.project` field:
```ts
return api.post<Review>("/v1/reviews/", { name, model_file: media.uuid, project });
```
and `useReviews` calls `` `/v1/reviews/?project=${projectUuid}` ``, T-0073's
`ReviewFilterSet.project` filter.

### What changed beyond the literal file list, and why

- **`App.tsx`'s sign-out and workspace-switch handlers now call `navigate()`** — bug 1
  above; not in the original Scope, required to make the real path actually work.
- **`ReviewDetailPage`'s `busy` derivation** — bug 2 above; same reasoning.
- **`ProjectViewSet`/`ReviewViewSet` etc. — untouched.** Confirmed by `git diff --stat`
  against `services/api/`: empty. This task touched only `services/web/`.
- **`keys.reviews`, `keys.projects`, `keys.project`, `keys.runs`, `keys.review`** added/
  changed in `queries.ts`'s key registry; `useRuleSets`/`useCreateRuleSet` deleted outright
  (grepped first — the `RuleSet` *type* is still referenced by `Review.rule_set`, so it
  stays per the task's own instruction to leave the type and delete only the two hooks).
- **`review.ruleSet` and `review.ruleSetNone`** i18n keys deleted alongside the whole
  `ruleSet.*` object — grepped first, confirmed orphaned (the old `<select>` that used
  `ruleSetNone` is gone, and `review.ruleSet` was never actually referenced by any JSX even
  before this task).

### NOT DONE

**The F1/F2 "nothing established" coverage-math regression (`nothing_established.ids`,
previously the second half of `report.spec.ts`) has no e2e path any more and is dropped
from the rewritten suite, not silently — flagged here.** That fixture exercised a rule set
authored specifically to hit `NO_SUBJECTS_NOTHING_CHECKED` vs. `NO_SUBJECTS_BUT_REQUIRED`;
reaching it required uploading an arbitrary IDS file, which is exactly the affordance this
task's own scope (and the 2026-09-04 decision it implements) removes from the UI. The only
three IDS fixtures in the *catalogue* (`door_width`, `door_name_recorded`, `door_prohibited`)
do not reproduce that scenario against `three_doors.ifc`. Adding
`nothing_established.ids` to `seed_rule_packs.py`'s `SEED_MANIFEST` would restore e2e
coverage but is a backend change, and this task's own Scope states the backend does not
change — so I did not make that edit unilaterally. Flagging it rather than guessing, per
this task's own instructions: the underlying `ReportView.tsx`/`check.py` logic this
regression protects is untouched by this task and still covered by the API-level pytest
suite (235 passed, unchanged), so this is a loss of *e2e* (browser-level) coverage
specifically, not a loss of coverage overall. Recommend a small follow-up task, if wanted:
extend `SEED_MANIFEST` with a fourth dev-only "sample" pack from this fixture.

Everything else in the task's Scope is done: the six routes, `Project`/`useProjects`/
`useProject`/`useCreateProject`, `useReviews(tenant, projectUuid)`, `useCreateReview` with
`project` and no `ruleSet`, `useRuleSets`/`useCreateRuleSet` deleted, `ReviewsPage.tsx`
deleted (not left dead), the report styling pass (disclosure callout, count tiles, entities
alignment), and the i18n additions/deletions.

## Review

Not gated per this task's own header (touches no invariant, frontend-only, every call
already routes through T-0073's tenant-scoped endpoints). Two real bugs were found and
fixed by executing the real path rather than trusting the diff — see Evidence above — which
is the check this repository substitutes for a review round on a non-gated task.
