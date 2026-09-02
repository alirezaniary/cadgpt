# T-0046 — The catalogue picker has never been rendered by any test, and two defects are waiting in it

**Phase:** 3   **Status:** open
**Touches invariants:** none.

## Why

Found by the T-0031 review. `services/web/package.json` has **no test runner at all** — no
vitest, no React Testing Library — despite `CLAUDE.md` describing `services/web` as
"RTL-native". The only browser test in the repository is `e2e/report.spec.ts`, which drives the
*uploaded rule set* path. T-0031's entire frontend surface — the catalogue picker and the report's
selection block — has therefore never been rendered by anything, and its evidence was curl plus a
list of i18n keys.

This is the same shape as T-0028, whose fix was real in the API and invisible in the browser
until it was looked for. Two defects a single render would have caught, both already found by
reading:

- `catalogueFilter` in `ReviewsPage.tsx` is **one piece of state shared by every catalogue
  review's picker on the page**, so typing a filter under one review re-filters all of them at
  once.
- `ReviewsPage.tsx` renders *"No packs match this filter."* during `useRulePacks`' initial load,
  before any filter has been typed — the product says nothing matches before it has looked.

## Scope

**Changes**

- A component test runner for `services/web`, wired into `make web-verify` so it runs in
  `make verify` and not only in `make e2e`. `make verify` must stay fast and hermetic.
- The two defects above fixed, each with a test that fails without the fix.
- A render test over the picker and over the report's selection block — the surfaces T-0031 added
  and nothing has ever rendered.

**What explicitly does not change**

- The Playwright e2e harness (T-0024). It stays as the real-path instrument; this is the layer
  below it, for component behaviour a full stack run should not have to prove.
- The API, the wire format, the selection logic.

## How to prove it ran

`make verify` including the new runner, then: each of the two defects demonstrated failing with
its fix reverted, output pasted. Two pickers on one page filtered independently, shown rendered.

## Evidence

## Review
