# T-0024 — An end-to-end browser harness that drives the real stack and proves a report reached the screen

**Phase:** 3 — What the first real user needs   **Status:** done
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

**`make verify` — passes clean, including `web-verify` with `@playwright/test` installed.**

```
$ make verify
uv run ruff check .
All checks passed!
uv run ruff format --check .
157 files already formatted
uv run mypy packages/engine/src services/api/cadgpt
Success: no issues found in 138 source files
uv run lint-imports --no-cache
Contracts: 5 kept, 0 broken.
uv run pytest
........................................................................ [ 44%]
........................................................................ [ 88%]
..................                                                       [100%]
162 passed, 18 warnings in 2.88s
cd services/web && pnpm install --frozen-lockfile && pnpm run verify
Already up to date

> @cadgpt/web@0.1.0 verify /home/alireza/Projects/cadgpt/services/web
> pnpm run lint && pnpm run typecheck && pnpm run build

> @cadgpt/web@0.1.0 lint
> eslint .

> @cadgpt/web@0.1.0 typecheck
> tsc -b --noEmit

> @cadgpt/web@0.1.0 build
> tsc -b && vite build

vite v6.4.3 building for production...
✓ 105 modules transformed.
dist/index.html                   0.40 kB │ gzip:  0.27 kB
dist/assets/index-BlFZKBg_.css    3.69 kB │ gzip:  1.30 kB
dist/assets/index-B-UsX-Yz.js   301.65 kB │ gzip: 94.27 kB │ map: 1,279.35 kB
✓ built in 1.94s
$ echo $?
0
```

**Chromium install.** `pnpm exec playwright install chromium` (no `--with-deps`: this
machine has no passwordless `sudo`, and a plain launch check proved the system libraries
Chrome for Testing needs are already present — a real headless launch rendered
`data:text/html,<h1>hello</h1>` and read back `hello` before any of the harness files were
written). Chromium 151.0.7922.34 (playwright build v1234) downloaded to
`/home/alireza/.cache/ms-playwright/chromium-1234`.

**Real path: `make up` then `make e2e` against the running compose stack.**

```
$ docker compose -f deploy/compose.yaml ps
NAME                IMAGE                COMMAND                  SERVICE    STATUS
cadgpt-api-1        cadgpt-api:latest    "sh -c 'python manag…"   api        Up (healthy)
cadgpt-postgres-1   postgres:17-alpine   "docker-entrypoint.s…"   postgres   Up (healthy)
cadgpt-redis-1      redis:7-alpine       "docker-entrypoint.s…"   redis      Up (healthy)
cadgpt-web-1        cadgpt-web           "/docker-entrypoint.…"   web        Up
cadgpt-worker-1     cadgpt-api:latest    "celery -A cadgpt.co…"   worker     Up (healthy)

$ make e2e
cd services/web && pnpm exec playwright install chromium && pnpm run e2e
> @cadgpt/web@0.1.0 e2e /home/alireza/Projects/cadgpt/services/web
> playwright test
Running 1 test using 1 worker
  ✓  1 [chromium] › e2e/report.spec.ts:26:1 › a real check run reproduces 1 pass / 1 fail / 1
     indeterminate in the browser (6.2s)
  1 passed (7.4s)
```

Run twice in a row against the same, never-reset stack (unique email/tenant slug per run,
per the fixture's design) — both passed, proving the harness is re-runnable without
`make reset`:

```
$ pnpm run e2e   # first run
  ✓  1 [chromium] › ... (7.8s)
  1 passed (9.3s)
$ pnpm run e2e   # second run, same containers, no reset in between
  ✓  1 [chromium] › ... (6.1s)
  1 passed (7.1s)
```

**The flow the spec actually drove**, entirely through the UI from sign-in onward: sign in
with the API-seeded credentials, add a rule set from `door_width.ids`, create a review from
`three_doors.ifc` against that rule set, click **Run check**, poll (via the app's own
polling, not a fixed sleep) until **Summary** appears, open it, and read the rendered
report.

**The three assertions on `ReportView`, quoted from `services/web/e2e/report.spec.ts`:**

```ts
await expect(report.locator(".count--pass .count__value")).toHaveText("1");
await expect(report.locator(".count--fail .count__value")).toHaveText("1");
await expect(report.locator(".count--indeterminate .count__value")).toHaveText("1");
...
const failRow = report.locator('[data-testid="entity-row"][data-status="FAIL"]');
await expect(failRow).toHaveCount(1);
await expect(failRow.locator('[data-testid="reason"]')).toHaveAttribute(
  "data-reason-code",
  "ATTRIBUTE_VALUE_MISMATCH",
);
await expect(failRow.locator('[data-testid="detail"]')).toContainText("800");

const indeterminateRow = report.locator(
  '[data-testid="entity-row"][data-status="INDETERMINATE"]',
);
await expect(indeterminateRow).toHaveCount(1);
await expect(indeterminateRow.locator('[data-testid="reason"]')).toHaveAttribute(
  "data-reason-code",
  "ATTRIBUTE_EMPTY",
);
```

`data-testid`/`data-reason-code`/`data-status` were added to the entity row and its reason
cell in `services/web/src/components/ReportView.tsx` — the one production change this task
permits — because the rendered cell shows the *translated* reason label
("The attribute value does not satisfy the rule.") and the stable `ReasonCode` string is
otherwise not present in the DOM at all.

**Screenshot:** `services/web/e2e/screenshots/report.png` (committed; run artifacts under
`test-results/` are gitignored, not this file). Opened and confirmed it shows the actual
rendered report, not an error or empty state: header "Accessible door width", a red **Fail**
pill, three count tiles reading **1 / 1 / 1** ("Passed" / "Failed" / "Could not be
determined"), the indeterminate notice "These were not checked. They are not passes.", and
the specification's two listed entities — a **Fail** row for `IfcDoor` `...JVBqA2` with
"The attribute value does not satisfy the rule." and detail `The attribute value "800.0"
does not match the requirement`, and an **Indeterminate** row for `...JVBqA3` with "The
attribute is present but holds no value." and detail `The attribute value "None" is empty`.
The passing door (`...JVBqA1`, 1000mm) is counted in the summary tiles but not listed as a
row, matching `ReportView`'s existing behaviour of only rendering non-passing entities.

**Wiring.**

`Makefile`:
```
e2e:  ## Run the Playwright suite against the stack `make up` already started
	cd $(WEB) && pnpm exec playwright install chromium && pnpm run e2e
```

`services/web/playwright.config.ts`:
```
  testDir: "./e2e",
  ...
    baseURL: "http://localhost:8080",
```

`services/web/package.json`: `"e2e": "playwright test"` under `scripts`, invoked by the
`Makefile` target above via `pnpm run e2e`.

**What changed, file by file:**
- `services/web/package.json` / `pnpm-lock.yaml` — `@playwright/test` devDependency, `e2e`
  script.
- `services/web/playwright.config.ts` — new.
- `services/web/e2e/fixtures.ts` — new. Seeds a unique account + tenant through
  `POST /api/v1/auth/register/`, `POST /api/v1/auth/login/`, `POST /api/v1/tenants/` on
  `http://localhost:8000` directly (not through the `web` container's proxy), so the
  seed step puts rows in the database without exercising the SPA.
- `services/web/e2e/report.spec.ts` — new. The flow described above.
- `services/web/eslint.config.js` — a file-scoped override turning off
  `react-hooks/rules-of-hooks` for `e2e/**/*.ts`: the plugin mistook Playwright's fixture
  callback argument `use` for React 19's built-in `use` hook. Tooling config, not
  production behaviour.
- `services/web/src/components/ReportView.tsx` — `data-testid`/`data-status` on the entity
  `<tr>`, `data-testid`/`data-reason-code` on the reason `<td>`, `data-testid` on the
  detail `<td>`. No visible change; text content is unchanged.
- `services/web/.gitignore` — ignore `test-results/` and `playwright-report/`.
- `Makefile` — `e2e` target added to `.PHONY` and defined; **not** added to the `verify`
  target's dependency list.
- `services/web/e2e/screenshots/report.png` — committed evidence screenshot.

**Not part of `make verify`, confirmed:** `verify: lint types contracts test web-verify` in
the `Makefile` is unchanged; `e2e` is a separate target.

## Review

**Reviewer not dispatched — the gate did not fire.** No invariant is touched: the only
production change is three data attributes on an existing `<tr>` and two `<td>`s, with no
text content, ordering or count altered. It is not a milestone boundary. The evidence block
is complete and the coordinator verified it independently rather than taking it on trust —
read the whole 28-line production-touching diff, confirmed `verify: lint types contracts
test web-verify` is unchanged in the `Makefile`, and opened
`services/web/e2e/screenshots/report.png`, which shows the rendered report with 1 / 1 / 1,
the FAIL row carrying `"800.0" does not match the requirement`, and the INDETERMINATE row
carrying `"None" is empty`. Accepted.

**One defect found by the coordinator while reading the evidence, filed rather than fixed
here.** The screenshot shows the requirement description rendering as
`<ifctester.facet.Attribute object at 0x76f24ab599a0>` — a Python object repr where the text
of the requirement belongs. Root cause is `description=str(facet)` at
`packages/engine/src/cadgpt_engine/check.py:77`; no `ifctester` facet defines `__str__`, so
it falls back to the default repr. Pre-existing since Phase 2 and outside this task's scope,
so it is **T-0026**, not a change to this task. It is sequenced ahead of T-0025 because
T-0025 orders and filters findings, and there is no point ranking a memory address by
severity.
