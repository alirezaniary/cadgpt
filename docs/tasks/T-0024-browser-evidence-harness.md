# T-0024 — An end-to-end browser harness that drives the real stack and proves a report reached the screen

**Phase:** 3 — What the first real user needs   **Status:** open
**Touches invariants:** none — this task adds no production behaviour. It builds the
instrument every later Phase 3 task uses to produce its evidence block.

## Why

Phase 3 is almost entirely frontend: report presentation, the scope disclosure, the web
overlay, marked sheets. `docs/agents.md` says a task is done when the real path ran and the
output is pasted, and `CLAUDE.md` says a green suite is not evidence. But `services/web` has
no test runner at all — `make web-verify` is `eslint`, `tsc -b --noEmit` and `vite build`,
none of which renders a component — and this machine has no browser. So the next frontend
task has no way to produce an evidence block, and neither does the one after it.

The decision is recorded in `docs/decisions.md` under *"A frontend change proves itself in a
browser against the running stack"*: Playwright against the compose stack, not jsdom. Two of
the three defects Phase 2 found by running the stack lived in exactly the seam a jsdom render
cannot reach — tenant resolution never seeing the authenticated user, and JWT lifetimes
failing on the first real sign-in. A component test would have passed through both.

Once this lands, every later Phase 3 task's evidence block is a browser run over the real
stack, and the report an architect actually sees is the thing under test.

## Scope

**Changes**

- `services/web/package.json` — add `@playwright/test` as a dev dependency and an `e2e`
  script. Do **not** add it to `pnpm run verify`; see *What does not change*.
- `services/web/playwright.config.ts` — new. Base URL `http://localhost:8080` (the `web`
  service in `deploy/compose.yaml` publishes the built SPA there). One project, chromium.
  No webServer block: the stack is brought up by `make up`, not by Playwright, because the
  thing under test is the built container image and not a dev server.
- `services/web/e2e/` — new directory.
  - A fixture that seeds an account and a tenant **through the API** (`POST /api/v1/auth/register/`,
    `POST /api/v1/auth/login/`, `POST /api/v1/tenants/` on `http://localhost:8000`), because
    the SPA has no registration or tenant-creation screen and inventing one to make the test
    convenient would be building a feature for the harness. Use a unique email per run so the
    harness is re-runnable against a stack whose volumes were not reset.
  - `e2e/report.spec.ts` — the flow, driven entirely through the browser from sign-in onward.
- `Makefile` — an `e2e` target that runs it, alongside `up`/`down`. Not part of `verify`.
- `services/web/.gitignore` (or the repo's) — ignore Playwright's `test-results/` and report
  output. Screenshots that are pasted as evidence are committed; run artifacts are not.

**The flow the spec drives**, all of it through the UI except the seeding above:

1. Sign in at `/` with the seeded credentials (`SignInPage`).
2. Add a rule set: the form in `ReviewsPage` takes a name and an `.ids` file. Upload
   `packages/engine/tests/fixtures/door_width.ids`.
3. Create a review: name, the rule set just added from the `<select name="rule_set">`, and the
   IFC file `packages/engine/tests/fixtures/three_doors.ifc`.
4. Click **Run check**. The page polls; wait for the run to reach a terminal state rather than
   sleeping a fixed interval.
5. Click **Summary** to open `ReportView`.
6. Assert on what the report shows, and screenshot it.

**What does not change**

- No production code. If a component needs a `data-testid` to be reachable, add it — that is
  the one exception, and prefer a role or label query first.
- `make verify` stays fast and hermetic. The browser run is the per-task real-path proof, run
  by hand exactly as `curl` against the API is for a backend task; it is not a CI gate in this
  task. Wiring it into CI is a later decision and not this task's business.
- No vitest, no jsdom, no React Testing Library. `docs/decisions.md` records when they return.

## How to prove it ran

The fixtures are the same ones Phase 2 ran end to end, and they produce a known answer: three
doors, one compliant, one measured at 800mm against a 900mm requirement
(`ATTRIBUTE_VALUE_MISMATCH`, FAIL), one with no width recorded at all (`ATTRIBUTE_EMPTY`,
INDETERMINATE). The harness is correct when it reproduces that from the browser.

```sh
make up                       # postgres, redis, api, worker, web
make e2e                      # or: cd services/web && pnpm run e2e
```

The evidence block must show:

- `make verify` passing, including `web-verify` with the new dependency installed.
- The Playwright run passing, with its actual stdout pasted — not a description of it.
- The three assertions the spec makes on `ReportView`, quoted from the spec file:
  **1 passed, 1 failed, 1 indeterminate**, read from the rendered counts; the `FAIL` entity row
  carrying reason `ATTRIBUTE_VALUE_MISMATCH` with `800` in its detail cell; and the
  `INDETERMINATE` entity row carrying `ATTRIBUTE_EMPTY`. An assertion that only checks the page
  loaded proves nothing and will be sent back.
- The path of the committed screenshot of the rendered report, and confirm you opened it and
  it shows the report rather than an error state or an empty page.
- **Wiring:** quote the `e2e` line from `Makefile` and the `testDir`/`baseURL` lines from
  `playwright.config.ts`. A spec file that no target runs is not wired.

Known things that will bite, so you do not rediscover them:

- The SPA is served from the `web` container on `:8080`; the API is on `:8000`. Check how the
  built SPA is told the API's origin (`deploy/docker/web.Dockerfile`, and any `VITE_` variable)
  before assuming `localhost:8000` works from inside the page. `CORS_ALLOWED_ORIGINS` in
  `deploy/compose.yaml` already lists `http://localhost:8080`.
- Login puts the refresh token in an httpOnly cookie and returns the access token in the body.
  Drive sign-in through the UI so the SPA owns its own session; do not inject a token.
- Chromium must be downloaded (`pnpm exec playwright install --with-deps chromium`). If the
  download or a system dependency fails in this environment, that is a **NOT DONE** with the
  actual error pasted — do not fall back to jsdom, and do not stub the browser. The decision
  to use a real browser is recorded; substituting a different mechanism is a different task.

## Evidence

<!-- the builder writes this -->

## Review
