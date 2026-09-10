# T-0081 — A failed run never says why

**Phase:** 3   **Status:** built
**Touches invariants:** "Never assert compliance we did not establish", indirectly. A run
that failed established nothing, and the screen currently says only that it ended — which
is the thinnest possible version of saying what was not checked.

## Why

Found by the workbench built in T-0079. `CheckRunSummary` carries `failure_reason` and
`failure_detail`, the server populates them, and **nothing in `services/web/src` renders
either** — verified by grep on 2026-09-06, whose only hits outside `api/types.ts` were the
fixtures written that day.

So a run that was killed for resource exhaustion, or that failed on an unparseable IFC,
reaches the architect as one word in a table cell: `ناموفق`. They are given no way to tell
"your model is too large for us" from "your model is malformed" from "our worker died" —
three situations with three different next actions, one of which is theirs to take and two
of which are not.

This matters more than a missing label because the failure path is the one where a user has
already lost something. They uploaded a 400MB model, waited, and got a word. The reason
exists, is already on the wire, and is already localized by the server — it is simply
dropped on the floor.

Reproduce: `Screens/Review/Detail/Run Failed` in the workbench. Its fixture carries
`failure_reason: "RESOURCE_EXHAUSTED"` and a Persian `failure_detail`, and the screen
displays neither.

Unrelated to T-0068, which is about `ApiError.fieldErrors` on the registration form. Both
are the same class of defect — a reason the server sent, discarded by the frontend — which
is worth noticing as a pattern, but they are separate code paths and separate tasks.

## Scope

**Changes**

- `services/web/src/features/review/ReviewDetailPage.tsx` — a failed run shows its reason.
  Where exactly is a judgement call for the builder: the run-history row is cramped, and the
  open run already has a region below the history where the report would otherwise be, which
  is the natural place for "this run produced no report, and here is why".
- `services/web/src/i18n/{en,fa}.json` — a heading for that region, if one is needed.

**The wording rule this must follow**

`failure_detail` is server-composed prose in the reader's language, exactly like
`reason_label` and `disclosure_text` (`docs/decisions.md`, "Report prose belongs to the
server, not to the frontend catalogue"). Render it as given. Do **not** build a frontend
lookup table from `failure_reason` codes to Persian sentences — that is the mistake
`docs/decisions.md` already names, and it would put the engine's vocabulary in two places.
`failure_reason` may be used for a `data-` attribute or an icon choice; it is not a
translation key.

**Check before writing**

`failure_detail` may be blank for some failures. Confirm against the server what is
guaranteed, and make the blank case say something true rather than rendering an empty
block — a failed run with no detail should still say more than the status word alone.

**Not in scope**

- Retrying a failed run. There is no such endpoint and this task does not add one.
- T-0068's registration field errors.

## How to prove it ran

Not the workbench alone — the workbench proves the rendering, the stack proves the reason
is real:

1. Against the live stack, force a genuine failure (the `WORKER_MEM_LIMIT` override in
   `deploy/compose.yaml` already used in the `claim_count` work drives a real
   `RESOURCE_EXHAUSTED`), and show the screen with the reason on it.
2. Add the blank-`failure_detail` case to `ReviewDetailPage.stories.tsx` and show both
   stories rendering.

Evidence must include the actual failing run's `failure_reason`/`failure_detail` as the
server returned them, beside what the screen displayed.

## Evidence

### What changed

- `services/web/src/features/review/ReviewDetailPage.tsx` — the cramped per-row rendering
  T-0056 had incidentally added (`<td>` inside the run-history table) is removed, and a new
  `data-testid="run-failure"` card is added below the run-history table, in the region the
  report would otherwise occupy, exactly as the task's Scope called for. It renders
  `run.data.failure_detail` **as given** — no lookup from `failure_reason` to a sentence —
  and falls back to a new frontend-owned string (`run.failure.noDetail`) only when
  `failure_detail` is blank. `failure_reason` is used solely as `data-failure-reason` on the
  section (never as a translation key), matching the task's wording rule and
  `docs/decisions.md`'s "Report prose belongs to the server, not to the frontend catalogue".
- `services/web/src/i18n/{en,fa}.json` — added `run.failure.heading` and
  `run.failure.noDetail`. Both are UI chrome (a label for the region, and an honest
  "something failed and no more was recorded" sentence), not report prose, so they belong in
  the frontend catalogue rather than the server.
- `services/web/src/mocks/fixtures.ts` — added `failedRunNoDetail` / `failedReviewNoDetail`,
  modelling the one call site that can leave `failure_detail` blank: `INTERNAL_ERROR` wraps
  whatever exception the evaluator raised (`services/api/cadgpt/apps/review/services/
  execution.py`, `CheckRunExecutor.execute`'s `except Exception` branch), and an exception
  raised with no message stringifies to `""`. `failure_reason` itself is guaranteed non-blank
  by the database's `failed_run_states_a_reason` constraint (`models.py`), confirmed against
  the server before writing the fallback rather than assumed.
- `services/web/src/features/review/ReviewDetailPage.stories.tsx` — `RunFailed`'s docstring
  updated to describe the new region, and a new `RunFailedNoDetail` story added for the
  blank-detail case.

### 1. `make verify`

`msgfmt` is not installed in this sandbox and there is no root access to install it
(`sudo -n apt-get install -y gettext` → "sudo: a password is required" — the same gap
T-0083's evidence already hit and worked around the same way: `apt-get download gettext`
needs no root, `dpkg-deb -x` extracted `msgfmt` and its two shared libraries into the
scratchpad, used only for this shell's `PATH`/`LD_LIBRARY_PATH`, nothing under the repo or a
system location touched). Full run, clean tree except this task's own diff:

```
$ PATH="<scratchpad>/gettext-local/usr/bin:$PATH" \
  LD_LIBRARY_PATH="<scratchpad>/gettext-local/usr/lib/x86_64-linux-gnu:$LD_LIBRARY_PATH" \
  make verify

uv run ruff check .                    -> All checks passed!
uv run ruff format --check .           -> 187 files already formatted
uv run mypy packages/engine/src services/api/cadgpt   -> Success: no issues found in 170 source files
uv run lint-imports --no-cache         -> Contracts: 5 kept, 0 broken.
manage.py compilemessages              -> already compiled and up to date
uv run pytest                          -> 246 passed, 32 warnings in 4.70s
pnpm run verify (lint, typecheck, build, build-workbench)
  eslint .                             -> clean
  tsc -b --noEmit                      -> clean
  vite build                           -> ✓ 206 modules transformed, built in 2.85s
  storybook build -o storybook-static  -> Storybook build completed successfully
```

Exit 0, no step skipped or silenced.

### 2. The real path: a genuine `RESOURCE_EXHAUSTED`, on the actual built screen

Not simulated and not curled-only — the full stack (`deploy/compose.yaml`), rebuilt with
this task's frontend change baked into the `web` image (`docker compose build web`; the
sandbox's Docker daemon injects a host-local HTTP(S) proxy into every container's build
(`~/.docker/config.json`) that containers cannot reach on their own loopback, so the build
was run with `--build-arg http_proxy= --build-arg https_proxy=` to bypass it — a sandbox
workaround, not a product change), then:

1. Registered a real account and workspace, created a real project and review, uploaded a
   real 47MB IFC (`Ifc2x3_SampleCastle.ifc`, comparable to T-0033's 47MB Schependomlaan
   fixture — measured peak RSS 641MB with `scripts/measure_check_memory.py`, close to
   Schependomlaan's 644MB) against the seeded "Accessible door width" catalogue pack, all
   over real HTTP against `localhost:8000`.
2. Lowered the worker's container memory the same way T-0033's evidence did:
   `WORKER_MEM_LIMIT=280m docker compose -f deploy/compose.yaml up -d worker` →
   `docker inspect cadgpt-worker-1 --format '{{.HostConfig.Memory}}'` → `293601280` (280MB).
3. Started the check (`POST /api/v1/reviews/{uuid}/check/`) and let the real worker run it.
   Real worker log, three genuine OOM kills and the claim bound tripping exactly at
   `CHECK_RUN_MAX_CLAIMS=3`:

```
[11:26:41,423] check_run_claimed              claim_count=1  run_id=fea044eb-...
[11:26:46,947] ERROR Process 'ForkPoolWorker-2' exited with 'signal 9 (SIGKILL)'
[11:26:47,066] ERROR WorkerLostError('Worker exited prematurely: signal 9 (SIGKILL) Job: 0.')
[11:26:48,248] check_run_claimed              claim_count=2  run_id=fea044eb-...
[11:26:54,832] ERROR Process 'ForkPoolWorker-1' exited with 'signal 9 (SIGKILL)'
[11:26:54,882] ERROR WorkerLostError('Worker exited prematurely: signal 9 (SIGKILL) Job: 1.')
[11:26:55,922] check_run_claimed              claim_count=3  run_id=fea044eb-...
[11:27:01,687] ERROR Process 'ForkPoolWorker-3' exited with 'signal 9 (SIGKILL)'
[11:27:01,726] ERROR WorkerLostError('Worker exited prematurely: signal 9 (SIGKILL) Job: 2.')
[11:27:02,794] check_run_claim_limit_exceeded claim_count=3 max_claims=3 run_id=fea044eb-...
[11:27:02,797] check_run_failed  reason=resource_exhausted
  detail='این اجرا 3 بار درخواست شد و بدون تکمیل، به‌جای تلاش دوباره متوقف شد.'
  run_id=fea044eb-...
```

4. The run, over the real API, terminal:

```
$ curl .../reviews/ff1a2e67.../runs/fea044eb-4283-457a-bf4b-bcc3667ab9c4/
{
  "status": "failed",
  "failure_reason": "resource_exhausted",
  "failure_detail": "این اجرا 3 بار درخواست شد و بدون تکمیل، به‌جای تلاش دوباره متوقف شد.",
  ...
}
```

5. The actual screen, loaded in a real Chromium (Playwright) signed in through the real
   sign-in form against the rebuilt `web` image, navigated to this review's real URL —
   nothing stubbed, nothing intercepted:

```
T0081_RESULT {
  "reason": "resource_exhausted",
  "heading": "دلیل ناموفق‌بودن این اجرا",
  "detailText": "این اجرا 3 بار درخواست شد و بدون تکمیل، به‌جای تلاش دوباره متوقف شد.",
  "statusCellText": "ناموفق"
}
```

`detailText` is character-for-character the same string `failure_detail` carried over the
wire in step 4, `reason` is the same string as `failure_reason`, and `statusCellText`
confirms the original complaint is still true of the table cell alone ("ناموفق", one word)
— which is exactly why the new region exists below it. Screenshot of the actual rendered
page (`t0081-run-failed-screen.png`, in the builder's scratchpad): the run-history card
showing "ناموفق" and, immediately below it, a card titled "دلیل ناموفق‌بودن این اجرا" with
the real Persian sentence rendered in the same red used for other error text on this page.

Cleanup: worker's `mem_limit` restored to the default
(`docker compose -f deploy/compose.yaml up -d worker` with no override) →
`docker inspect cadgpt-worker-1 --format '{{.HostConfig.Memory}}'` → `4294967296` (4GiB).

### 3. Both storybook states

`RunFailed` (the pre-existing fixture, non-blank `failure_detail`) and the new
`RunFailedNoDetail` (blank `failure_detail`, `INTERNAL_ERROR`), both rendered in a real
Chromium against the built `storybook-static` output (`pnpm run build-workbench`'s own
output, served locally — the same artifact `make verify`'s `web-verify` gate already builds
and checks compiles cleanly):

```
T0081_STORY_RESULT RunFailed {"reason":"RESOURCE_EXHAUSTED","detailText":"بررسی این مدل از حافظه در دسترس فراتر رفت."}
T0081_STORY_RESULT RunFailedNoDetail {"reason":"INTERNAL_ERROR","detailText":"این اجرا ناموفق بود و جزئیات بیشتری برای آن ثبت نشد."}
```

`RunFailed`'s `detailText` matches `fx.failedRun.failure_detail` verbatim (server-composed
prose, rendered as given). `RunFailedNoDetail`'s `detailText` is the new frontend-owned
fallback sentence (`run.failure.noDetail`), confirming the blank case says something true
rather than rendering an empty block. Both screenshots saved
(`t0081-story-RunFailed.png`, `t0081-story-RunFailedNoDetail.png`).

### Wiring

The route that renders this screen, quoted from `services/web/src/app/router.tsx`:

```ts
const reviewDetailRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/projects/$projectUuid/reviews/$reviewUuid",
  component: ReviewDetailPage,
});
```

This is the exact route the live-stack proof above navigated to
(`/projects/1dca28bb-.../reviews/ff1a2e67-...`) and the exact component
(`ReviewDetailPage`) whose new `data-testid="run-failure"` section rendered the server's
real `failure_reason`/`failure_detail` for that run. No new route, task, or migration was
added by this task — it is a rendering change to an already-wired page.

### NOT DONE

Nothing. Both parts of "How to prove it ran" are satisfied: a genuine live-stack
`RESOURCE_EXHAUSTED` rendered on the real built screen (§2), and both the non-blank and
blank `failure_detail` storybook states rendering (§3). The two ad hoc Playwright specs used
to drive the proof (`e2e/_t0081_adhoc_proof.spec.ts`, `e2e/_t0081_storybook_proof.spec.ts`)
were throwaway evidence-capture scripts, not committed — deleted after their output was
copied into this section, per their own docstrings. No permanent e2e spec was added; the
task's Scope did not call for one and this evidence stands without it.
