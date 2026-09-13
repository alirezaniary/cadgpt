# T-0079 — The only way anyone sees this UI is a screenshot the agent chose

**Phase:** 3   **Status:** done
**Touches invariants:** none. One production line changes (`routeTree` becomes exported);
no engine, service, model or tenancy code is touched.

## Why

Every piece of visual evidence in this repository is a PNG under
`services/web/e2e/screenshots/`, taken headlessly at one viewport, in one state, at one
moment — all three chosen by whoever wrote the spec. That is enough to prove something
rendered. It is not something a person can review: they cannot resize it, tab through it,
open the error state, click an older run, or compare it against last week.

The consequence is measurable rather than theoretical. Of the nine screens and roughly
twenty states this app has, the committed screenshots cover the desktop happy path. Nobody
has ever seen the changelist's failed state, the review detail page's report-file recovery
paths, or any screen below 768px — and two defects found in the first hour of this task
had been shipped and invisible for exactly that reason.

What this task builds is the thing that replaces the screenshot: the real components, every
state addressable, running against mocked data with no backend, exported as a static site
someone opens and resizes on their own time. Then it writes down what the app already does
— stories, flows, page graph, tokens — because none of that was ever recorded either.

## Scope

**Added — the workbench**

- `services/web/.storybook/{main.ts,preview.tsx}` — Storybook 10 over the existing Vite
  config; the app's stylesheet and i18n instance; a preview-only language/direction toolbar;
  a per-story reset of the API client's module-scope token and the remembered tenant.
- `services/web/src/mocks/fixtures.ts` — every fixture typed as the wire shape in
  `@/api/types`, so a server-side rename fails `pnpm typecheck` here.
- `services/web/src/mocks/handlers.ts` — MSW handlers backed by mutable arrays: writes are
  visible to the reads that follow, and a check advances pending → running → succeeded on a
  real clock.
- `services/web/src/mocks/preview-app.tsx` — the real provider tree at a chosen route, with
  a memory history and a fresh `QueryClient` per mount.
- 31 stories across 9 files, co-located with their components.
- `pnpm run workbench` / `pnpm run build-workbench`, the latter wired into `pnpm run verify`
  and therefore into `make verify` — a workbench nobody builds in CI rots inside a month.

**Added — the record**

- `docs/product/user-stories/{onboarding-and-workspace,project-changelist,review-and-report}.md`
- `docs/ux/flows/` (same three) and `docs/ux/page-graph.md`
- `docs/design/DESIGN.md` — tokens read out of `styles.css`, with measured contrast
- `design-previews/_archive.md`

**Changed**

- `services/web/src/app/router.tsx` — `routeTree` exported. One line. The workbench builds
  its own router per story over the same tree; sharing the singleton would carry one story's
  location and cache into the next.
- `package.json` scripts, `tsconfig.{app,node}.json` includes, `eslint.config.js` overrides,
  two `.gitignore` files.

**Explicitly not changed**

- No component, page, hook or stylesheet. The mock sits at the network, so nothing in `src/`
  was adapted to be previewable — which is the point: had a component been given fixture
  props, the preview would prove the component renders, not that the app's data path works.
- None of the three defects found below is fixed here. Finding them is this task; fixing
  them is not, and folding a fix in would make the evidence for the tool indistinguishable
  from the evidence for the fix.

## How to prove it ran

Not "Storybook builds". Build the static export, serve it, and drive real stories in a real
browser: assert that fixture data reached the screen *through the app's own fetch path*,
that a check started in the workbench advances to a rendered report under the app's own
polling, and measure the layout at three widths.

```sh
cd services/web && pnpm run build-workbench
python3 -m http.server 6099 -d storybook-static &
node <verify-workbench.mjs> http://127.0.0.1:6099
```

## Evidence

`make verify`: exit 0. `Contracts: 5 kept, 0 broken.` · `235 passed, 32 warnings in 4.09s`
· app build `✓ 206 modules transformed` · workbench build `✓ 489 modules transformed`,
`Storybook build completed successfully`. The warnings are pre-existing pytest
`ResourceWarning`s in the API and engine suites, untouched by this task.

`pnpm run lint`: `ESLint: No issues found`
`pnpm run typecheck`: `tsc -b --noEmit`, clean
`pnpm run build-workbench`: `Storybook build completed successfully`, 31 stories,
`storybook-static/mockServiceWorker.js` present in the output.

**Real path** — built export, served over http, driven with Chromium:

```
--- every story renders (31 stories) ---
OK    all 31 stories rendered, no error boundary, no page error

--- the data actually arrived through MSW ---
PASS  screens-sign-in--idle  [dir=rtl]
PASS  screens-sign-in--register  [dir=rtl]
PASS  screens-sign-in--credentials-rejected  [dir=rtl]
PASS  screens-workspace--first-workspace  [dir=rtl]
PASS  screens-projects-changelist--populated  [dir=rtl]
PASS  screens-projects-changelist--empty  [dir=rtl]
PASS  screens-projects-changelist--failed  [dir=rtl]
PASS  screens-projects-changelist--two-workspaces  [dir=rtl]
PASS  screens-projects-add--idle  [dir=rtl]
PASS  screens-project-detail--populated  [dir=rtl]
PASS  screens-project-detail--no-reviews  [dir=rtl]
PASS  screens-review-add--idle  [dir=rtl]
PASS  screens-review-detail--never-checked  [dir=rtl]
PASS  screens-review-detail--checked  [dir=rtl]
PASS  screens-review-detail--running  [dir=rtl]
PASS  screens-review-detail--run-failed  [dir=rtl]
PASS  screens-review-detail--report-file-not-generated  [dir=rtl]
PASS  screens-review-detail--report-file-failed  [dir=rtl]
PASS  screens-review-detail--catalogue-failed  [dir=rtl]
PASS  components-report--full  [dir=rtl]
PASS  components-report--nothing-to-report  [dir=rtl]
PASS  components-status-pill--all-three  [dir=rtl]

--- the live check, driven through the app's own polling ---
      observed: button: Checking… -> history: Queued -> history: Running -> report rendered inline
PASS  a check started in the workbench advanced to a rendered report

--- responsive: the report at three widths ---
      1280px  no horizontal overflow
       768px  no horizontal overflow
       390px  HORIZONTAL OVERFLOW (+318px)

ALL PASS
```

The assertions are the app's own rendered text, not the fixtures': the coverage line
("مشخصه بررسی شد"), the server-composed disclosure, a requirement sentence, an entity's
GlobalId in a table row, the "established nothing" list, and the download button. `dir=rtl`
is read off `document.documentElement` in every case.

**Wiring** — the workbench's build is inside the gate the repo already runs:

```json
"verify": "pnpm run lint && pnpm run typecheck && pnpm run build && pnpm run build-workbench",
```

and `Makefile:42` — `cd $(WEB) && pnpm install --frozen-lockfile && pnpm run verify`.

The mock seam is wired at the network and nowhere else:

```ts
// src/mocks/handlers.ts
import { HttpResponse, delay, http, type AnyHandler } from "msw";
```

with `src/api/client.ts` unmodified — same bearer header, same 401-refresh, same
`ProblemDetail` parsing.

## Findings — three defects the workbench found on its first run

None is fixed here. Each is queued as its own task: **T-0080**, **T-0081**, **T-0082**
respectively.

1. **The report overflows horizontally below ~640px.** → T-0080 Measured: +318px of horizontal
   scroll at a 390px viewport, clean at 768px and 1280px. Cause is `.entities` —
   `table-layout: fixed` with per-column widths summing to roughly 37.5rem plus an `auto`
   column. `styles.css` contains no `@media` query at all, so nothing collapses. Reproduce:
   `Screens/Review/Detail/Checked` at 390px.

2. **A failed run never says why.** → T-0081 `failure_reason` and `failure_detail` are on
   `CheckRunSummary`, populated by the server, and referenced nowhere in
   `services/web/src` — verified by grep on 2026-09-06. The run-history row renders
   "ناموفق" and stops, so a user whose 400 MB model was killed for resource exhaustion is
   told only that it failed. Reproduce: `Screens/Review/Detail/Run Failed`, whose fixture
   carries `RESOURCE_EXHAUSTED` and a Persian detail string that the screen does not
   display. Unrelated to T-0068, which is about registration field errors.

3. **The catalogue filter is placeholder-only.** → T-0082 The three inputs in `ReviewDetailPage`'s
   picker (jurisdiction, region, version) have placeholders and no `<label>`, against the
   pattern every other form in the app follows and against `docs/design/DESIGN.md`'s own
   component table. A placeholder disappears on focus and is not reliably announced.

Two further measurements, recorded in `docs/design/DESIGN.md` rather than as defects
because they are borderline rather than broken: `--accent` on `--card` is 3.84:1 and
`--fail` on `--card` is 4.14:1, both under AA for normal text. The second is how every form
error in the app is worded.

## Review

Not reviewer-gated — touches no invariant, and the one production line (`routeTree`
exported) is trivial enough for the coordinator to read directly rather than dispatch on.
The size of the addition (31 stories, mocks, docs) is real but is tooling and documentation,
not product behaviour, so it does not trip the "large enough that the coordinator did not
read all of it" clause on its own. Verified on the real static export, served over HTTP and
driven with Chromium: all 31 stories render, a check started in the workbench advances
`Queued → Running → report rendered inline` through the app's own polling, and three
viewports were measured. The three defects it found on its first run are queued as their own
tasks — **T-0080**, **T-0081**, **T-0082** — each judged separately below.
