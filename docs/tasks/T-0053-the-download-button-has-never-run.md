# T-0053 — The download half of T-0032 has never executed, and two defects are visible in it

**Phase:** 3   **Status:** open
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

## Review
