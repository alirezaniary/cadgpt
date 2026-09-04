# T-0074 — a changelist, an add form, and a detail view, in place of one page

**Phase:** 3   **Status:** open
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

## Review
