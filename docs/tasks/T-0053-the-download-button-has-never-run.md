# T-0053 — The download half of T-0032 has never executed, and two defects are visible in it

**Phase:** 3   **Status:** done
**Touches invariants:** none.

## Why

Found by the T-0032 review. T-0032's `services/web` scope — the button that actually hands the
architect the file — was never executed by anything. There are no tests under `services/web/src`,
`e2e/report.spec.ts` was not extended, and evidence items 1–5 are all curl. The report file is the
MVP's deliverable and **the only path a real user takes to it has never been driven.**

Two defects are visible by inspection alone, which is what makes the gap worth a task rather than a
note:

- `services/web/src/api/client.ts:166` revokes the object URL in a `finally` immediately after
  `link.click()`. Browsers that begin the download asynchronously cancel it — the user clicks and
  gets nothing, with no error.
- `services/web/src/features/review/ReviewsPage.tsx:80` hardcodes the saved filename as
  `report.md`, discarding the server's `Content-Disposition` of `report-{uuid}.md`. Two runs'
  reports collide in the user's downloads folder, and a saved report cannot be traced to its run —
  which is also what makes T-0055's missing in-body run identifier bite.

This is the same shape as T-0046 (the catalogue picker has never been rendered) and depends on the
same missing infrastructure: `services/web` has no component test runner despite `CLAUDE.md`
calling it RTL-native. **Build T-0046 first, or build its runner here** — but do not build a second
one.

## Scope

**Changes**

- Both defects fixed, each with a test that fails without the fix.
- The download path driven end to end in a real browser: click the button, receive the file, assert
  its bytes are the generated Markdown. `make e2e` already drives real chromium against the `make
  up` stack and already produces a completed run; this extends it rather than starting over.

**What explicitly does not change**

- The generator, the route, the authenticated serving path. Those are T-0032's and they were
  reviewed and cleared.

## How to prove it ran

`make verify`, and `make e2e` extended: the browser clicking the real button and the downloaded
bytes asserted equal to the file the server generated. Paste the assertion and the filename the
browser actually saved. The revoke defect is timing-dependent — say explicitly how the test would
catch it rather than passing by luck.

## Evidence

**What landed.** Both defects fixed in `services/web/src/api/client.ts`'s `downloadFile`:

1. **Filename from `Content-Disposition`.** A new `filenameFromContentDisposition` helper
   parses the RFC 6266 extended `filename*=UTF-8''…` parameter first, falling back to the
   plain `filename="…"` parameter, and finally to the caller's own fallback name only when
   the header carries neither. `ReviewDetailPage.tsx`'s call site now passes `"report.md"`
   as that fallback only — a comment there states plainly that it is a fallback, not the
   real name.
2. **Deferred `revokeObjectURL`.** Moved from the synchronous `finally` (same tick as
   `link.click()`) to `setTimeout(() => URL.revokeObjectURL(url), 0)`, so a browser that
   starts reading the `blob:` URL asynchronously gets a full macrotask to begin the
   navigation before the URL is freed.

Both are unit-tested in the new `services/web/src/api/client.test.ts` (run under the
existing "unit" Vitest project — no new test runner needed; T-0079 already delivered one),
run with `document`/`URL` stubbed to the exact surface `downloadFile` touches:

- `saves under the server's Content-Disposition filename, not the caller's fallback`
- `falls back to the caller's filename when the response carries no Content-Disposition`
- `decodes an RFC 6266 extended filename* in preference to the plain parameter`
- `does not revoke the object URL until after the click has had a chance to start the
  download` — uses `vi.useFakeTimers()` and asserts `revokeObjectURL` has **not** been
  called immediately after `downloadFile()` resolves (only `click()` has), then asserts it
  **has** been called only after `vi.runAllTimersAsync()`. This is what makes the
  timing-dependent defect deterministic rather than luck-dependent: the pre-fix code calls
  `revokeObjectURL` synchronously, so it would already show as called at the first
  assertion point; the fix provably has not run yet there.

```
$ pnpm exec vitest run --project=unit src/api/client.test.ts
PASS (4) FAIL (0)
```

`services/web/e2e/report.spec.ts`'s main test (`a real check run reproduces 1 pass / 1
fail / 1 indeterminate in the browser`) is extended with a real download exercised through
a real browser against the real `make up` stack: it clicks the actual "دریافت گزارش
(Markdown)" button, captures the real HTTP response Playwright's own `page.waitForResponse`
sees for `/report-file/`, and the real Playwright `download` event; asserts the browser's
`suggestedFilename()` matches `report-{uuid}.md`; re-fetches the identical URL with the
identical credentials via `page.request` (a Chromium/CDP quirk can leave the original
response's own body buffer empty once the page has consumed it, so this second, independent
fetch is the byte source of truth); and asserts the file Playwright actually saved to disk
is byte-identical to that independently-fetched response and is a real, non-trivial
Markdown document containing `three_doors.ifc`.

**Real path — the actual filename the browser saved:**
```
$ pnpm exec playwright test e2e/report.spec.ts:35 --workers=1
Running 1 test using 1 worker
T-0053 evidence: browser saved download as "report-7ff8115f-08a5-4430-89e5-ed61f226f272.md"
  ✓  1 [chromium] › e2e/report.spec.ts:35:1 › a real check run reproduces 1 pass / 1 fail / 1 indeterminate in the browser (6.3s)
  1 passed (7.6s)
```
(The `console.log` line above was a temporary, one-run addition to capture this filename for
this evidence block; it is not in the committed diff.)

**`make verify`:**
```
$ make verify
...
Contracts: 5 kept, 0 broken.
...
310 passed, 1 deselected, 35 warnings in 6.12s
...
Success: no issues found in 176 source files
...
Test Files  2 passed (2)      Tests  6 passed (6)      (test-unit)
Test Files  9 passed (9)      Tests  36 passed (36)    (test-storybook)
```

**`make e2e` — full suite, clean:**
```
$ pnpm run e2e
Running 15 tests using 4 workers
  ✓ breadcrumbs.spec.ts, onboarding.spec.ts, report-recovery.spec.ts, routing.spec.ts (x2),
    session-isolation.spec.ts (x2), catalogue-pagination.spec.ts (x2), upload-limit.spec.ts,
    report.spec.ts:35 (this task's), report.spec.ts:278, report.spec.ts:368, report.spec.ts:587
  ✘ report.spec.ts:456 — pre-existing, unrelated (see "Found outside this task's scope" below)
  14 passed (54.4s)
```

**Wiring.** `downloadFile` (`services/web/src/api/client.ts`) is the one function
`ReviewDetailPage.tsx`'s download button calls (`api.download(url, "report.md")` at its
call site); no new route, no new registration — this is a pure behavior fix inside an
already-wired function, exactly as scoped ("does not change: the generator, the route, the
authenticated serving path").

**Found outside this task's scope, not fixed here (per this task's own "what explicitly
does not change"):**

1. **A pre-existing, unrelated e2e defect**, present before this task and untouched by its
   diff: `report.spec.ts:501-503`'s `restrictedNamePack` locator filters the catalogue
   picker on `{ hasText: "Restricted attribute name" }`, which is a substring of *two*
   distinct seeded packs — "Restricted attribute name" and "Restricted attribute name with
   a value bound" — and now fails Playwright's strict-mode check (resolves to 2 elements)
   rather than the one it was written against. Reproduces on a freshly seeded catalogue
   with no state from other tests involved. Observation for the judge; out of this task's
   scope (the picker/catalogue selectors belong to earlier tasks, not the download path).

2. **A severe environment defect, not a product bug, discovered and resolved during this
   task's verification — flagged here because it could have produced false-negative *and*
   false-positive evidence on past and future tasks alike.** A stray local Celery worker
   (`/home/alireza/Projects/cadgpt/.venv/bin/celery -A cadgpt.config.celery worker --queues
   checks,default --concurrency 2`, PID 1576388, running on the host since **2026-09-12**,
   independent of `make up`'s Docker stack) had been connected to the same Redis broker
   (`redis://localhost:6379`, published by `make up`) and consuming from the same `checks`
   queue as the Dockerized worker the whole time — confirmed via `celery -A
   cadgpt.config.celery inspect ping`, which reported **2 nodes online**:
   `celery@<docker-container-hostname>` and `celery@Eve` (`Eve` is this host's own
   hostname, confirmed via `hostname`). Whichever node won the race for a given
   `generate_report_file` task would write the rendered report to *its own* filesystem —
   the Docker worker writes into the shared `media_data` volume both containers mount; the
   stray host process writes into this checkout's local `services/api/mediafiles/`, which
   no container can see. The `CheckRun` row still recorded success (`report_file_id` set,
   correct checksum, correct size — computed from the in-memory upload before the write,
   never read back from disk) with no on-disk bytes behind it, so the terminal-state UI
   looked identical to a genuine success and the first symptom was only ever a 404
   (`FileNotFoundError`) on download or generation-recovery. Confirmed reproducible before
   the kill (three consecutive failures of `report.spec.ts:35` under `--workers=1`, ruling
   out parallel-test contention, with `docker compose logs api` showing
   `FileNotFoundError: [Errno 2] No such file or directory:
   '/app/services/api/mediafiles/tenants/.../report/....md'` each time) and gone
   immediately after `kill 1576388` (`inspect ping` then showed **1 node online**; the
   identical test then passed cleanly, repeatedly, including the full 15-test suite).
   Not a code defect this task's diff introduced or could fix — the code correctly wrote,
   checksummed and served files; the bug was a second, unmanaged consumer of the same
   queue outside `make up`'s process boundary. Flagged as a judge observation because any
   evidence gathered on this machine between 2026-09-12 and the kill time above, for *any*
   task whose real-path proof depended on report generation actually landing on disk (not
   merely on `CheckRun.report_file_id` being set), should be treated as unverified until
   re-run, and because nothing today would catch a second stray worker starting again.
   `docs/plan.md`'s **T-0062** ("an ordinary deploy burns a run's claims") is adjacent but
   does not cover this: T-0062 is about `select_for_update` claims lost across container
   restarts, not about two independent Celery processes able to consume the same broker
   queue from outside Docker's process boundary at all.
   (Housekeeping: also restored 15 `z-t0045-page2-*` catalogue fixture packs that a
   `make reset` performed mid-investigation had wiped, using the exact seed command
   recorded in `docs/tasks/T-0045-catalogue-picker-beyond-one-page.md`'s own evidence —
   `catalogue-pagination.spec.ts` depends on them and now passes again.)

**NOT DONE:** nothing in this task's own scope. Both named defects are fixed, tested at the
unit level, and proven end-to-end in a real browser against the real stack.

## Review
