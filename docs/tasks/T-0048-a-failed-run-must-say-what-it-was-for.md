# T-0048 — A failed run must say what it was supposed to check, and speak the application's error language

**Phase:** 3   **Status:** done
**Touches invariants:** "never assert compliance we did not establish" — its mirror, a failure
that fails to explain itself.

## Why

Found by the T-0031 review, which executed all three of these against the real stack. A run that
fails currently tells the tenant a Python detail, an internal storage key, or nothing at all.

1. **`_combine_reports([])` raises `IndexError`, and the tenant is shown the traceback fragment.**
   `execution.py`'s `first = reports[0]` is reached whenever a run has `review.rule_set is None`
   and an empty `rule_pack_selection`. Executed: `failed | internal_error | list index out of
   range`. `failure_detail` is on `CheckRunSummarySerializer`, so **"list index out of range" is
   what the user reads**. Not reachable over HTTP today — `ReviewViewSet` has no update mixin and
   `_resolve_selection` refuses an empty selection at request time — but reachable from
   `ReviewService.create(rule_set=None)` plus `create_run`, which is a management command or a
   future task away.

2. **Internal storage keys reach the tenant.** Pack row present, stored file gone. Executed:
   `failed | internal_error | [Errno 2] No such file or directory: 'rule-packs/sample/5d29…ids'`.
   The storage key is shown to the user, and the classification is wrong: `invalid_rule_set` is
   accurate, `internal_error` is not. The `_fail` truncation shape is pre-existing; the catalogue
   path is a new way to reach it.

3. **A failed run never shows what it was supposed to check.** **Corrected by the coordinator
   before dispatch, 2026-09-12, same precedent as T-0041/T-0045:** the page this describes is now
   `services/web/src/features/review/ReviewDetailPage.tsx` (T-0074 replaced `ReviewsPage.tsx`),
   and the defect is otherwise unchanged and confirmed still live: `ReportView` (and the
   `rulePackSelection` prop it takes) renders only when `currentReport` — `run.data?.report` — is
   truthy (`ReviewDetailPage.tsx:340-342`), and a failed run has no report. The `runFailed` block
   above it (`:296-301`, T-0081) shows `failureDetail` only. The run that fails *because* a cited
   pack vanished shows the reason but never the selection — so the one screen where "what was
   this supposed to cover?" matters most is the one that does not answer it.

## Scope

**Changes**

- A run that reaches execution with nothing to check terminates with a named reason rather than
  an `IndexError`. `CheckRunFailure` already models exactly this distinction between a rejected
  input and a crash.
- Storage-layer errors are classified honestly and do not carry internal paths into
  `failure_detail`. The operator still gets the full error in the log; the tenant gets the
  application's language.
- The run's recorded selection is visible on a failed run, not only on a successful one.

**What explicitly does not change**

- `_resolve_selection`'s request-time refusals (T-0031, correct and tested).
- The `_fail` / `failure_detail` mechanism itself, beyond what these three need.

## How to prove it ran

`make verify`, then each of the three reproduced against `make up` and shown fixed, with the
before and after `status | failure_reason | failure_detail` triple pasted for each. The third is
a rendered browser evidence item, not curl.

## Evidence

**Status: built.**

### 1. `make verify`

Passed, in full, with the fix applied (`services/api/cadgpt/apps/review/services/execution.py`,
`services/api/cadgpt/locale/fa/LC_MESSAGES/django.po`, `services/web/src/components/ReportView.tsx`,
`services/web/src/features/review/ReviewDetailPage.tsx`):

```
uv run ruff check .        -> All checks passed!
uv run ruff format --check . -> 191 files already formatted
uv run mypy ...            -> Success: no issues found in 173 source files
uv run lint-imports         -> Contracts: 5 kept, 0 broken.
uv run pytest               -> 296 passed, 34 warnings in 6.10s
pnpm run verify (eslint, tsc -b, vite build, storybook build,
                 vitest unit, vitest storybook)
  -> Test Files  1 passed (1) / Tests  2 passed (2)      (unit)
  -> Test Files  9 passed (9) / Tests  35 passed (35)    (storybook)
```

### 2. The real path — defects 1 and 2, before and after, against `make up`

Reproduced directly against the running compose stack's `api` container
(`docker compose -f deploy/compose.yaml exec -T api python manage.py shell`), using a real
tenant, a real uploaded `three_doors.ifc`, and a real seeded catalogue pack ("Accessible door
width", jurisdiction `sample`, v0.1). Each defect was driven exactly as the task's Why section
describes: defect 1 by calling `CheckRun.objects.create_run(review=review,
rule_pack_selection=[])` directly (bypassing `request_check`/`_resolve_selection`, which is
unchanged and still refuses this at request time) on a review with no `rule_set`, then
`CheckRunExecutor().execute(run.uuid)`; defect 2 by citing a real pack via
`RulePackService().snapshot(pack)`, creating the run, then deleting the pack's stored `.ids`
file from the shared `media_data` volume before executing.

**Before** (temporarily reverted `execution.py` to the pre-fix `HEAD` version, rebuilt
`cadgpt-api:latest`, redeployed, ran the repro, then restored the fix and rebuilt/redeployed
again — see below):

```
DEFECT1 raised: IndexError list index out of range
DEFECT1 failed | internal_error | list index out of range

DEFECT2 raised: FileNotFoundError [Errno 2] No such file or directory: '/app/services/api/mediafiles/rule-packs/sample/41965b0b-204b-4a65-a466-d6a488cd0e03.ids'
DEFECT2 failed | internal_error | [Errno 2] No such file or directory: '/app/services/api/mediafiles/rule-packs/sample/41965b0b-204b-4a65-a466-d6a488cd0e03.ids'
```

**After** (fix restored, `cadgpt-api:latest` rebuilt and redeployed again — the state the repo
is left in):

```
DEFECT1 failed | invalid_rule_set | این اجرا هیچ مجموعه‌قاعده یا بسته‌قاعده‌ای برای بررسی در برابر آن ندارد.

DEFECT2 failed | invalid_rule_set | فایل ذخیره‌شده برای بسته‌قاعده Accessible door width قابل خواندن نبود.
```

No `IndexError`, no internal storage path, and the classification is `invalid_rule_set`, not
`internal_error`, matching the Scope's stated correction for both. The Persian wording is the
real compiled catalogue (`LANGUAGE_CODE=fa` in this deployment) — new entries added to
`cadgpt/locale/fa/LC_MESSAGES/django.po` for both new user-facing strings, compiled with
`compilemessages` before the image was built. The catalogue pack's file was restored to the
shared volume afterward (`docker compose exec api python -c "shutil.copy(...)"`, verified
`.exists() == True`) so the seeded catalogue was left exactly as it was found.

The fix required wrapping *both* `RulePackService.checksum_of` and `RulePackService.local_path`
in the one `try/except OSError` inside `_evaluate_selection` — an earlier pass wrapped only
`local_path` and still leaked the raw storage path, because `checksum_of` opens the file
directly and raises first; this was caught by re-running the exact same repro against the
rebuilt image before treating the fix as done.

### 3. The real path — defect 3, rendered browser evidence

Not curl. Driven with a Playwright script against the built `web` container on
`http://localhost:8080` (the same image `make up` runs), using a freshly registered account and
tenant seeded through the real API (`/api/v1/auth/register/`, `/api/v1/auth/login/`,
`/api/v1/tenants/`), exactly as `services/web/e2e/report.spec.ts` does. To force the failure
deterministically rather than racing a fast worker: the `worker` container was stopped, a
review was created in the browser, the "Accessible door width — sample v0.1" catalogue pack was
selected and "اجرای بررسی با بسته‌های انتخاب‌شده" (run check) was clicked (creating a `PENDING`
run with no worker yet to claim it), the pack's stored file was then deleted from the shared
volume, and only then was the `worker` container restarted — so the run was guaranteed to fail
on the missing file, not race it.

Rendered output, read back from the DOM after navigating directly to the review's detail page
(`ReviewDetailPage.tsx`) with the authenticated session restored via Playwright's
`storageState`:

```
FAILURE_REASON invalid_rule_set
FAILURE_DETAIL "فایل ذخیره‌شده برای بسته‌قاعده Accessible door width قابل خواندن نبود."
SELECTION_TEXT "بسته‌های مقرراتی که بررسی شدند\nAccessible door width — sample v0.1"
```

Screenshot (`/tmp/t0048_failed_run_selection.png`) shows the review detail page's "دلیل
ناموفق‌بودن این اجرا" (why this run failed) card with the failure detail in Persian, no
internal path, and directly beneath it the new "بسته‌های مقرراتی که بررسی شدند" (rule packs
checked) section naming "Accessible door width — sample v0.1" — the exact selection this run
was dispatched to check, now visible on a *failed* run for the first time.

### Wiring

The failed-run branch in `ReviewDetailPage.tsx` renders the shared selection component
unconditionally on `run.data?.rule_pack_selection` (not gated on `currentReport`, unlike
`ReportView`):

```tsx
// services/web/src/features/review/ReviewDetailPage.tsx:296, :306
{runFailed && (
  <section className="card" data-testid="run-failure" data-failure-reason={failureReason}>
    ...
    <RulePackSelectionList selection={run.data?.rule_pack_selection ?? []} />
  </section>
)}
```

`RulePackSelectionList` is exported from `services/web/src/components/ReportView.tsx:109` and
imported in `ReviewDetailPage.tsx:28` (`import { ReportView, RulePackSelectionList } from
"@/components/ReportView";`) — the same component `ReportView` itself now calls internally for
a *succeeded* run, so the two paths cannot render two diverging implementations of "what was
this run's selection."

On the backend, `CheckRunExecutor.execute` (`execution.py:77-90`) is unchanged in its dispatch
to `_evaluate_selection`; the new classification lives entirely inside that method
(`execution.py:121-136` for the empty-selection guard, `:145-172` for the storage-error
wrapping), reached through the same `except InvalidIdsError as exc: return self._fail(run,
CheckRunFailure.INVALID_RULE_SET, str(exc), log)` (`execution.py:82-83`) every other
`InvalidIdsError` in this method already used — no new failure-classification branch was added
to `execute` itself.

### NOT DONE

Nothing. All three defects in Scope are fixed, verified against the real running stack, and the
before/after state is reproducible from this evidence. `_resolve_selection`'s request-time
refusals and the `_fail`/`failure_detail` mechanism itself were not touched, per Scope.

---

## Fix-now round: F1–F4 (post-build review)

An independent review of the "built" state above found four fix-now defects: F1, the
failed-run card asserted the packs "were checked" when nothing was; F2, the `except OSError`
around the catalogue-pack read misclassified operator-side faults (`PermissionError`,
`ConnectionError`, `TimeoutError`) as `invalid_rule_set` with no operator signal, defeating
Celery's retry policy; F3, the failed-run selection display never handled an uploaded
`RuleSet` (only the catalogue-pack shape); F4, none of the three original fixes had a test.
All four are fixed below, same task, same file scope, per `docs/agents.md`'s fix-now round.

### F1 — the heading no longer asserts "checked" on a run that never was

`RulePackSelectionList` (`services/web/src/components/ReportView.tsx:109-135`) now takes a
required `heading: "checked" | "selected"` prop instead of hard-coding
`t("report.selection.title")`. `ReportView`'s own call site (line 221) passes
`heading="checked"` — a `Report` exists there, so "checked" is true by construction.
`ReviewDetailPage.tsx`'s failed-run branch passes `heading="selected"` (line ~321) — this run
never produced a report, so it must never claim the packs were checked.

New i18n keys, both languages, never reusing "بررسی شدند"/"checked":

```
en.json: "titleSelected": "Rule packs selected for this run"
fa.json: "titleSelected": "بسته‌های مقرراتی انتخاب‌شده برای این اجرا"
```

### F2 — the storage-read guard is narrowed to `FileNotFoundError`, and the original
exception is logged before it is mapped

`_evaluate_selection` (`services/api/cadgpt/apps/review/services/execution.py:153-206`) no
longer wraps `checksum_of` + citation-mismatch-raise + `local_path`'s full body + teardown in
one `except OSError`. It now:

- catches `FileNotFoundError` only, narrowly around `checksum_of(pack)` alone (`:171-182`);
- catches `FileNotFoundError` only, narrowly around *entering* `local_path(pack)` via
  `contextlib.ExitStack().enter_context(...)` (`:192-204`) — not around `self._evaluate(...)`
  (now outside the `try`, at `:205`) and not around the `ExitStack`'s own teardown (which runs
  when the `with` block exits, after the narrow `try` has already returned or raised);
- logs `log.exception("check_run_pack_unreadable", rule_pack_id=..., cited_name=...)` (full
  traceback, `exc_info` set automatically by `.exception()`) before raising the tenant-facing
  `InvalidIdsError`.

`PermissionError`, `ConnectionError` and `TimeoutError` are **not** `FileNotFoundError`, so
none of them are caught here any more — they propagate to `execute`'s existing
`except Exception` branch: classified `internal_error`, logged, and re-raised (so
`execute_check_run`'s `autoretry_for=(ConnectionError, TimeoutError)` still sees them).

### F3 — the failed-run card names an uploaded `RuleSet` too

`ReviewDetailPage.tsx`'s failed-run branch (`:296-325`) now branches on `review.data?.rule_set`:

```tsx
{review.data?.rule_set ? (
  <section className="selection" data-testid="run-failure-rule-set">
    <h4>{t("report.selection.ruleSetTitle")}</h4>
    <p>{review.data.rule_set.name}</p>
  </section>
) : (
  <RulePackSelectionList
    selection={run.data?.rule_pack_selection ?? []}
    heading="selected"
  />
)}
```

A catalogue-selection run shows the corrected `RulePackSelectionList`; a `rule_set` run names
the rule set; a run with genuinely neither (the original defect-1 shape) falls through to
`RulePackSelectionList`, which renders `null` for an empty selection — the card then shows only
the failure reason, exactly as Scope requires for that one case.

### F4 — tests for all three fixes, mutation-proven

New file: `services/api/cadgpt/apps/review/tests/test_execution_failure_classification.py`,
3 tests, all passing against the real engine/DB (`rtk proxy uv run pytest
services/api/cadgpt/apps/review/tests/test_execution_failure_classification.py -v`):

```
test_a_run_with_no_rule_set_and_no_selection_fails_named_not_crashed PASSED
test_a_missing_pack_file_is_classified_honestly_without_the_storage_path PASSED
test_a_transient_storage_error_is_not_swallowed_as_invalid_rule_set PASSED
```

**Mutation proof 1 — the empty-selection guard.** `if not selection: raise
InvalidIdsError(...)` replaced with `if False: ...` (guard disabled). Re-running
`test_a_run_with_no_rule_set_and_no_selection_fails_named_not_crashed`:

```
>       first = reports[0]
E       IndexError: list index out of range
services/api/cadgpt/apps/review/services/execution.py:442: IndexError
FAILED ...test_a_run_with_no_rule_set_and_no_selection_fails_named_not_crashed - IndexError: list index out of range
```

Guard restored (file diffed byte-identical to the pre-mutation copy); test passes again.

**Mutation proof 2 — the `FileNotFoundError` narrowing.** Both `except FileNotFoundError`
clauses in `_evaluate_selection` widened back to `except OSError` (the pre-fix-now shape).
Re-running `test_a_transient_storage_error_is_not_swallowed_as_invalid_rule_set` (which
simulates a `ConnectionError` from `checksum_of`):

```
>       with pytest.raises(ConnectionError):
E       Failed: DID NOT RAISE ConnectionError
```

With the run's actual state at that point: `reason="invalid_rule_set"`,
`detail="فایل ذخیره‌شده برای بسته‌قاعده Accessible door width قابل خواندن نبود."` — the exact
misclassification F2 exists to prevent. Narrowing restored (file diffed byte-identical to the
pre-mutation copy); test passes again.

Frontend coverage (Storybook play functions, run via
`pnpm run test-storybook` / `vitest run --project=storybook`):

- `ReviewDetailPage.stories.tsx`'s `RunFailed` story gained a `play` function asserting the
  failed catalogue run shows `i18n.t("report.selection.titleSelected")`, never
  `i18n.t("report.selection.title")`, plus the cited pack's name.
- A new story, `RunFailedRuleSet`, with its own fixtures (`fx.uploadedRuleSet`,
  `fx.failedRunRuleSet`, `fx.failedReviewRuleSet` in `services/web/src/mocks/fixtures.ts`;
  `handlers.ts`'s run-detail handler now passes `[]` for `rule_pack_selection` when the
  review has a `rule_set`, mirroring `_resolve_selection`'s real behaviour) — its `play`
  function asserts the failed-run card shows `fx.uploadedRuleSet.name` and that
  `rule-pack-selection` is absent.

### `make verify`, full, after all four fixes

```
uv run ruff check .          -> All checks passed!
uv run ruff format --check . -> 192 files already formatted
uv run mypy packages/engine/src services/api/cadgpt -> Success: no issues found in 174 source files
uv run lint-imports --no-cache -> Contracts: 5 kept, 0 broken.
uv run pytest                -> 299 passed, 34 warnings in 6.24s
pnpm run verify:
  lint       -> 0 errors, 2 pre-existing warnings (unrelated files)
  typecheck  -> clean
  build      -> ✓ built in 3.85s
  build-workbench (storybook build) -> ✓ built in 12.86s
  test-unit  -> Test Files 1 passed (1) / Tests 2 passed (2)
  test-storybook -> Test Files 9 passed (9) / Tests 36 passed (36)
```

### The real path, again: defect 1, defect 2, and a fresh `chmod 000` repro

Rebuilt both images against the fix-now code (`DOCKER_BUILDKIT=0 docker build --network=host
-f deploy/docker/api.Dockerfile -t cadgpt-api:latest .` and the equivalent for `web.Dockerfile`
— the sandboxed proxy is only reachable from the build container in host-network mode),
redeployed `api`, `worker`, `beat`, `web` (`docker compose -f deploy/compose.yaml ps` confirms
all four running the freshly built image IDs), then reproduced against the live `api`
container exactly as the original evidence did (`docker compose exec -T api python manage.py
shell`), plus a new case:

```
=== DEFECT1: empty selection, no rule_set ===
DEFECT1 failed | invalid_rule_set | این اجرا هیچ مجموعه‌قاعده یا بسته‌قاعده‌ای برای بررسی در برابر آن ندارد.

=== DEFECT2 (F2): pack file deleted from storage ===
DEFECT2 failed | invalid_rule_set | فایل ذخیره‌شده برای بسته‌قاعده Accessible door width قابل خواندن نبود.
storage key leaked into detail: False

=== F2 fresh repro: chmod 000 on a pack file (must NOT become invalid_rule_set) ===
pack3 real path: /app/services/api/mediafiles/rule-packs/fixnow-chmod-044929af/33814012-a3a0-411f-bcc0-0a6d41c96768.ids
mode now: 0o100000
DEFECT_CHMOD raised (expected -- internal_error path re-raises): PermissionError: [Errno 13] Permission denied: '.../33814012-....ids'
DEFECT_CHMOD (after raise) failed | internal_error | [Errno 13] Permission denied: '.../33814012-....ids'
mode restored: 0o100644
```

**The `chmod 000` case no longer misclassifies as `invalid_rule_set` — confirmed.** Before
this round it did (that was the reviewer's live repro); after F2's narrowing it is
`internal_error`, with the real `PermissionError` logged (`check_run_pack_unreadable`, `error`
level, full traceback) and re-raised out of `execute()` so the worker reports it to the error
tracker rather than silently absorbing it. Defect 1 and defect 2 remain fixed exactly as the
original evidence recorded (identical `reason`/`detail` pairs).

### The real path, again: F1 and F3 rendered in the browser

Same rebuilt `web` image, same live stack. A fresh tenant, project and two reviews were
seeded through the real services (`docker compose exec -T api python manage.py shell` —
`AccountService.register` with a known password so the browser could actually sign in through
the UI form, then `TenantProvisioningService`, `MediaService`, `ReviewService`, `RulePackService`,
`RuleSetService`, `CheckRun.objects.create_run`, `CheckRunExecutor().execute` directly, the same
pattern the original defect-1/2 evidence used — Celery dispatch is bypassed on purpose so the
forced-failure setup is deterministic rather than a race against the live worker; execution
itself is the same production `CheckRunExecutor`, not a stub):

- **Scenario A** — catalogue review, pack file deleted, run failed `invalid_rule_set`.
- **Scenario B** — review created with an uploaded `RuleSet`, `rule_set.source_file` deleted,
  run failed (`internal_error` — this path is `execute()`'s direct `rule_set` branch, not
  `_evaluate_selection`; see NOT DONE below).

Driven with a Playwright script (`chromium`, not curl) against `http://localhost:8080`: signed
in through the real login form (رایانامه/گذرواژه/ورود), let the app auto-select the seeded
tenant, navigated straight to each review's detail page, read `[data-testid="run-failure"]`
back from the DOM:

```
=== SCENARIO A: run-failure card text ===
دلیل ناموفق‌بودن این اجرا
فایل ذخیره‌شده برای بسته‌قاعده Accessible door width قابل خواندن نبود.
بسته‌های مقرراتی انتخاب‌شده برای این اجرا
Accessible door width — fixnow-browser-43033230 v0.1
SCENARIO_A_HAS_SELECTED_HEADING true
SCENARIO_A_HAS_CHECKED_HEADING false
SCENARIO_A_HAS_PACK_NAME true

=== SCENARIO B: run-failure card text ===
دلیل ناموفق‌بودن این اجرا
[Errno 2] No such file or directory: '.../ids_ruleset/f45006d2-....ids'
مجموعه‌قاعدهٔ این اجرا
Fixnow accessible doors ruleset
SCENARIO_B_HAS_RULE_SET_NAME true
SCENARIO_B_HAS_PACK_SELECTION_TESTID false
```

Screenshots: `/tmp/t0048_fixnow_scenario_a.png` (heading reads "بسته‌های مقرراتی
انتخاب‌شده برای این اجرا", never "بررسی شدند", with the pack named beneath it) and
`/tmp/t0048_fixnow_scenario_b.png` (heading "مجموعه‌قاعدهٔ این اجرا" with "Fixnow accessible
doors ruleset" named, no empty pack-selection block).

### Wiring

`RulePackSelectionList`'s two call sites, both quoted from their current files:

```tsx
// services/web/src/components/ReportView.tsx:221
<RulePackSelectionList selection={rulePackSelection ?? []} heading="checked" />

// services/web/src/features/review/ReviewDetailPage.tsx:317-322 (inside the runFailed branch)
<RulePackSelectionList
  selection={run.data?.rule_pack_selection ?? []}
  heading="selected"
/>
```

The narrowed guard, both sites, quoted from `execution.py`:

```python
# :173
except FileNotFoundError as exc:
# :195 (inside `with contextlib.ExitStack() as stack:`, around `stack.enter_context(...)` only)
except FileNotFoundError as exc:
```

The new test file is collected by the same `uv run pytest` `make verify` already runs — no
separate registration needed (pytest's default rootdir discovery), confirmed by its 3 tests
appearing in the 299-passed total above.

### NOT DONE (fix-now round)

- **The direct `rule_set` execution path (`execute()`'s own `with media.local_path(rule_set.
  source_file)`, not `_evaluate_selection`) still leaks a raw storage path into
  `failure_detail` when the uploaded rule set's file is missing** (Scenario B above,
  `internal_error` with `[Errno 2] No such file or directory: '/app/.../ids_ruleset/....ids'`
  visible in the rendered card). This is the same pre-existing `_fail` truncation shape the
  original T-0048 evidence names as out of Scope ("The `_fail`/`failure_detail` mechanism
  itself... not touched"), and F2's brief was specifically `_evaluate_selection`'s
  catalogue-pack read, not this sibling path. Left as found rather than fixed silently under a
  different task's fix-now round; flagging it here rather than folding in an unscoped change.
- Nothing else. F1–F4 as specified are fixed, tested, mutation-proven, and reproduced against
  the real rebuilt stack, both over the API directly and rendered in a real browser.

## Review
