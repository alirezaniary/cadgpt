# T-0034 — The filter banner must not claim credit for what the engine capped

**Phase:** 3 — What the first real user needs   **Status:** done
**Touches invariants:** three-valued results, I7. **Reviewer-gated** — every line of this task
is a change to how a limitation is stated.

## Why

Found by the T-0025 review (Q1, Q4), not by a test. Two related ways the filtered report
understates what the reader is not seeing.

**The denominator is wrong.** `ReportView.tsx:64-67, 139` builds `allEntities` from
`r.entities`, which `check.py:103-104` has already truncated at `DEFAULT_ENTITY_LIMIT = 500`,
with the remainder recorded separately in `entities_omitted`. On the Schependomlaan run this
repository's Phase 0 measured — 3,623 non-passing entities — a FAIL-only filter renders

```
Showing 12 of 500 findings. The rest are hidden by this filter, not resolved.
```

That sentence asserts the entire gap between 12 and 500 is the filter's doing, and it states a
total of 500 for a run with 3,623 findings. T-0025's own Scope §3 said "do not conflate the two
numbers" — `entities_omitted` counts what the engine capped, the banner counts what the filter
hid — and the wording conflates them anyway. A reader who unchecks nothing still never learns
that 3,123 findings were never itemised at all.

**A partially-filtered specification gives no local signal.** `ReportView.tsx:187-191`
announces only when *every* row in a requirement is hidden. A specification showing 2 of 30
rows is indistinguishable from a specification with 2 findings. The global banner is the only
signal and it is off-screen the moment the reader scrolls into a long list — which, on a real
run, is immediately.

## Scope

**Changes** — `services/web/src/components/ReportView.tsx`, both i18n catalogues, `styles.css`
as needed, `services/web/e2e/report.spec.ts`.

1. The banner must distinguish the two numbers. Either state the omitted count alongside the
   filtered one, or word `total` as the count of *itemised* findings and name the cap
   separately. Whichever is chosen, a reader must be able to tell how many findings exist,
   how many were itemised, and how many the current filter is hiding — three numbers, never
   collapsed into two.
2. A per-requirement signal when some but not all of its rows are hidden.

**Does not change:** the engine, the cap itself, the count band (counts are of the run, not of
the view), and the absence of a PASS filter. `packages/engine` and `services/api` are not
touched.

## How to prove it ran

The existing e2e fixture has two itemised rows and cannot exercise a cap. A fixture or a
stubbed payload that has both `entities_omitted > 0` and a filter hiding rows is required —
if that cannot be reached through the real stack without an unreasonably large fixture, say so
and drive it through a component test with a real payload shape, but do not assert the wording
against a payload you hand-wrote to match it.

`make verify`, then `make up` (rebuild `web`) and `make e2e`, with stdout pasted, plus a
screenshot of a filtered report showing all three numbers.

## Evidence

**Scope decision, per "How to prove it ran."** Reaching `DEFAULT_ENTITY_LIMIT` (500) through
the real backend would need a fixture with 500+ failing entities in one requirement — deemed
unreasonably large, per the task's own escape hatch. `CHECK_ENTITY_LIMIT`
(`services/api/cadgpt/config/settings/base.py:323`) could lower the cap instead, but that is
`services/api` config and would change "the cap itself" for the whole environment, both of
which the Scope forbids touching. So: the real e2e path (`report.spec.ts`) proves the
*negative* — the new report-wide omission notice does not fire on a real run that never hit
the cap — and a Storybook component test, built on the engine-shaped `fx.report` fixture that
already existed for T-0025 (not written for this task), proves the *positive* — cap hit, filter
active, partial-hide signal all firing together with the numbers computed by the real component
code, not hand-typed to match.

**1. `make verify`.** Passes. (One environment fix, unrelated to this change: this sandbox had
`gettext-base` but not `gettext` itself, so `msgfmt` was missing and `compile-messages` failed
before ever reaching `services/web`. Fetched the `gettext` `.deb` with `apt-get download`
(no sudo needed, no install performed) and pointed `PATH`/`LD_LIBRARY_PATH` at the extracted
binary for this shell only — nothing under version control changed.)

```
$ export PATH=/tmp/gettext-extract/usr/bin:$PATH
$ export LD_LIBRARY_PATH=/tmp/gettext-extract/usr/lib/x86_64-linux-gnu:$LD_LIBRARY_PATH
$ make verify
...
Contracts: 5 kept, 0 broken.
cd services/api && uv run --project .. python manage.py compilemessages
File "services/api/cadgpt/locale/fa/LC_MESSAGES/django.po" is already compiled and up to date.
uv run pytest
...
259 passed, 34 warnings in 4.65s
cd services/web && pnpm install --frozen-lockfile && pnpm run verify
...
> eslint .
> tsc -b --noEmit
> tsc -b && vite build
...
dist/assets/index-CIRLRG7e.js                406.17 kB │ gzip: 127.80 kB
✓ built in 2.60s
> storybook build -o storybook-static --quiet
...
Storybook build completed successfully
```

**2a. The real path — `make up` (web only) + `make e2e`, all 9 specs, against the real
backend.** `docker compose up --build` also rebuilds `api`/`worker`/`beat` (they share one
image), and this sandbox's Docker daemon cannot reach `pypi.org` for `uv sync` (its configured
proxy is `127.0.0.1:2080`, unreachable from inside the build container's network namespace —
a pre-existing sandbox limitation, not caused by this change). `api`/`worker`/`beat` were
already running unmodified code (this task touches neither), so only `web` needed a real
rebuild:

```
$ docker compose -f deploy/compose.yaml build web
...
#13 [web build 7/7] RUN pnpm run build
#13 ✓ built in 2.68s
...
#16 naming to docker.io/library/cadgpt-web:latest
 web  Built
$ docker compose -f deploy/compose.yaml up -d --no-deps web
 Container cadgpt-web-1  Recreated
 Container cadgpt-web-1  Started

$ cd services/web && pnpm exec playwright install chromium && pnpm run e2e
Running 9 tests using 4 workers
  ✓ e2e/breadcrumbs.spec.ts:18:1 › the breadcrumb trail carries a review three levels deep back out to the changelist (11.0s)
  ✓ e2e/report-recovery.spec.ts:42:1 › the recovery button's own POST is what moves a pending report to failed (13.7s)
  ✓ e2e/onboarding.spec.ts:25:1 › a brand-new person registers, creates a workspace and walks every project/review route, entirely in the browser (14.1s)
  ✓ e2e/report.spec.ts:34:1 › a real check run reproduces 1 pass / 1 fail / 1 indeterminate in the browser (14.2s)
  ✓ e2e/upload-limit.spec.ts:19:1 › the model size ceiling is stated at upload time (7.4s)
  ✓ e2e/session-isolation.spec.ts:43:1 › signing out clears the previous user's cached tenant and project data before the next person signs in on the same tab (10.7s)
  ✓ e2e/report.spec.ts:202:1 › a requirement that evaluated nothing explains why, in words, beside its status (9.9s)
  ✓ e2e/session-isolation.spec.ts:127:1 › the workspace dropdown never renders with zero options while the tenant list is still loading (4.4s)
  ✓ e2e/report.spec.ts:292:1 › a requirement that genuinely evaluated real entities still carries a caveat when its own specification's applicability was never established (6.4s)
9 passed (32.4s)
```

`e2e/report.spec.ts`'s first test now also asserts the negative directly against the live
report at `http://localhost:8080` (screenshot: `services/web/e2e/screenshots/report.png`,
regenerated by this run): `three_doors.ifc` produces 2 non-passing findings, nowhere near the
cap, and `[data-testid="filter-omitted-total"]` has count 0 — the new notice does not fire when
nothing was capped.

**2b. The component test — a real headless browser against the actual built Storybook
artifact**, not a description of what the story should do. `ReportView.stories.tsx` exports
`FilteredWithOmissionsAndAPartialRequirement`, whose `play` function drives the real
`ReportView` component (real `userEvent.click`, real `expect(...).toHaveTextContent(...)`
from `storybook/test`) against `withMixedRequirement` — `fx.report` (T-0025's fixture, three
requirements already carrying `entities_omitted: 8, 5, 25`) plus one added `EntityOutcome`
(INDETERMINATE, real reason code `ATTRIBUTE_EMPTY`) so the door-width requirement mixes FAIL
and INDETERMINATE rows, the one shape `fx.report` didn't already have. Every number the `play`
function asserts is read back off that object's own fields (`entities_omitted`, array lengths),
never typed out to match the wording.

Built and served for real, then driven with Playwright/Chromium (already a project
devDependency) pointed at the actual static build:

```
$ pnpm run build-workbench   # part of `pnpm run verify`, already run above
$ cd storybook-static && python3 -m http.server 6461 &
$ node -e '...chromium.launch()... open iframe.html?id=components-report--filtered-with-omissions-and-a-partial-requirement, wait for [data-testid="filter-banner"], dump text + testids + screenshot...'

---- CONSOLE / PAGE ERRORS ----
(none)                                    # the play function's expect() calls did not throw

---- TESTID TEXT ----
filter-omitted-total[0]: 38 یافتهٔ دیگر، فراتر از 7 یافتهٔ فهرست‌شده در اینجا، وجود دارد — محدودیت موتور برای هر الزام باقی را پیش از اعمال این پالایش کنار گذاشته است، نه این پالایش.
filter-banner[0]: نمایش 4 از 7 یافتهٔ فهرست‌شده. 3 مورد با این پالایش پنهان شده‌اند، نه برطرف‌شده.
requirement-partially-hidden[0]: 1 از 5 یافتهٔ فهرست‌شده در اینجا با پالایش فعلی پنهان شده‌اند.
requirement-all-hidden[0]: همهٔ ردیف‌های این بخش با پالایش فعلی پنهان شده‌اند.
```

Three distinguishable numbers, exactly as the Scope requires: **38** findings the engine
capped and never itemised (independent of the filter, shown before any checkbox is touched),
**7** itemised, **3** hidden by the filter once INDETERMINATE is unchecked (4 of 7 shown) — and
the new per-requirement signal (**1 of 5** hidden on the door-width requirement) sitting beside
the untouched all-hidden note on the stairs requirement, which stayed fully hidden as before.
Screenshot: `services/web/e2e/screenshots/t0034-filter-banner-three-numbers.png`.

**3. Wiring.**

- The two new banners and the new per-requirement note are rendered from inside the same
  `ReportView` the app already mounts on every review's report — no new component, no new
  route; `services/web/src/components/ReportView.tsx` lines 228–232 (`filter-omitted-total`)
  and lines 338–345 (`requirement-partially-hidden`) sit directly beside the pre-existing
  `filter-banner` and `requirement-all-hidden` blocks they were added next to.
- Every string goes through `gettext` (`useTranslation`'s `t`), and both catalogues declare
  the three keys used — `services/web/src/i18n/en.json`:
  ```
  "omittedTotal": "{{omitted}} more finding(s) exist beyond the {{itemised}} itemised here — the engine's per-requirement limit capped the rest before this filter ever applied.",
  "showing": "Showing {{shown}} of {{itemised}} itemised finding(s). {{hidden}} are hidden by this filter, not resolved.",
  ...
  "partiallyHidden": "{{hidden}} of {{total}} itemised finding(s) here are hidden by the current filter."
  ```
  and the matching keys in `services/web/src/i18n/fa.json` (same three keys, Persian wording) —
  a missing key in either file would have surfaced as the raw key string in the screenshots
  above, and it did not.
- The component test is reachable the same way any Storybook story is: `ReportView.stories.tsx`
  exports `FilteredWithOmissionsAndAPartialRequirement`, and Storybook's own id derivation
  (`Components/Report` + the export name) is exactly the `components-report--filtered-with-
  omissions-and-a-partial-requirement` id the browser run above loaded and got a populated
  `[data-testid="filter-banner"]` back from — not a component instantiated ad hoc outside
  Storybook's own registration.

**NOT DONE:** nothing. Both scope items (the three-number banner, the per-requirement partial
signal) are implemented, verified via `make verify`, the real backend (the negative case), and
a real-browser run of the actual built component (the positive case, since the positive case
is unreachable through the real stack without an unreasonably large fixture, as explained
above).

## Fix-now pass (F1/F2/F3)

The review below found the production fix correct and the proof wrong in three ways. Fixed
all three; nothing in this pass touches `ReportView.tsx`'s actual banner logic (confirmed by
deliberately reintroducing both mutant defects the review found, watching the new test catch
each one, then reverting — see F1).

**F3 — the fixture is now engine-shaped in the dimension that was wrong.**
`packages/engine/src/cadgpt_engine/check.py:136-160` fixes the exact relationship a
hand-written fixture has to respect: `outcomes = tuple(_outcome(...) for f in facet.failures)`
never contains a `PASS` row, and `entities = outcomes[:entity_limit]` /
`entities_omitted = max(0, len(outcomes) - entity_limit)` together mean a requirement with
`entities_omitted > 0` itemises *exactly* `entity_limit` entities — never more, never fewer —
and `len(outcomes)` always equals `failed + indeterminate`. `services/web/src/mocks/fixtures.ts`
now holds every requirement in `fx.report` to one `entity_limit = 3` (a fixture-only constant,
documented in the comment above `export const report`, unrelated to the real deployed
`CHECK_ENTITY_LIMIT` — `services/api/cadgpt/config/settings/base.py:323` — which is 500 and
would make the array unreadable in a fixture):

- Door-width requirement: the PASS-status entity mixed into `entities` is gone (a passing
  entity can never be among `facet.failures`). `entities` now holds exactly 3 FAIL rows,
  `entities_omitted: 8` stays, and `failed` moved from 3 to 11 so that
  `failed + indeterminate` (11) equals `entities.length + entities_omitted` (3 + 8) —
  previously `failed: 3` while `entities_omitted: 8` implied at least 8 more failing
  entities existed than the requirement's own aggregate admitted. Spec-level `failed`/
  `matched` and the report-level `failed` total were updated the same way (3 → 11).
- Stairs requirement: a third INDETERMINATE entity was added so `entities.length` reaches
  the same `entity_limit` (3), and `entities_omitted` moved from 5 to 4 so that
  `3 + 4 = 7` matches the requirement's own `indeterminate: 7` exactly (previously
  `2 + 5 = 7` coincidentally summed right but `entities.length` (2) didn't match the other
  requirements' implied limit).
- Spaces requirement: `entities_omitted` moved from 25 to 0. This requirement's `failed` and
  `indeterminate` are both 0 (everything passed), so `len(outcomes) = 0` — there is nothing
  for any limit to have capped, and a nonzero `entities_omitted` here was simply wrong, not a
  different limit.

`services/web/src/components/ReportView.stories.tsx`'s `withMixedRequirement` mutation was
updated to match: since the door-width requirement's kept entities are already at the fixture's
`entity_limit`, turning one FAIL row INDETERMINATE now *replaces* the last kept entity
(`entities.slice(0, -1)` plus the new row) instead of appending a fourth, and `failed`/
`indeterminate` move by one in the same requirement so the totals stay internally consistent
after the mutation too. The evidence block above's "real engine-shaped payload" claim is now
accurate in the dimension F3 checked — every requirement's `entities`/`entities_omitted`/
`failed`/`indeterminate` obey the same arithmetic `check.py` itself enforces, and no `PASS`
row appears among itemised findings anywhere in the fixture.

**F1 — the assertions are anchored, and proven to catch the actual mutations.**
`ReportView.stories.tsx`'s `play` function (`FilteredWithOmissionsAndAPartialRequirement`,
now lines 122-197) no longer asserts bare `toHaveTextContent(String(n))`. Every assertion
instead builds the full expected sentence with `i18n.t(...)` — the same `@/i18n` singleton
and the same catalogue key/interpolation `ReportView.tsx` itself calls via `useTranslation`'s
`t` — and compares the whole rendered string, so a number landing in the wrong
`{{placeholder}}` produces a sentence that cannot equal the correctly-built one. Two explicit
negative assertions (lines 164-178) additionally construct the two concrete wrong sentences
by name — the omitted total substituted for the filter's hidden count, and shown/hidden
swapped — each guarded by `expect(a, msg).not.toBe(b)` on the underlying numbers so the
negative check cannot become vacuous if the fixture's numbers ever coincide.

Proof this actually closes the gap the reviewer found, not just a claim that it should:
reproduced both of the reviewer's mutations directly in `ReportView.tsx`, ran the suite, watched
it fail with a readable diff, then reverted.

Mutation 1 — `hidden: totalOmitted` instead of `hidden: hiddenByFilter` (the exact bug T-0034
removes, re-attributing the engine's cap to the filter):

```
 FAIL  |storybook (chromium)| src/components/ReportView.stories.tsx > Filtered With Omissions And A Partial Requirement
expect(element).toHaveTextContent()
Expected element to have text content:
  نمایش 2 از 6 یافتهٔ فهرست‌شده. 4 مورد با این پالایش پنهان شده‌اند، نه برطرف‌شده.
Received:
  نمایش 2 از 6 یافتهٔ فهرست‌شده. 12 مورد با این پالایش پنهان شده‌اند، نه برطرف‌شده.
```

Mutation 2 — `shown`/`hidden` swapped:

```
 FAIL  |storybook (chromium)| src/components/ReportView.stories.tsx > Filtered With Omissions And A Partial Requirement
expect(element).toHaveTextContent()
Expected element to have text content:
  نمایش 2 از 6 یافتهٔ فهرست‌شده. 4 مورد با این پالایش پنهان شده‌اند، نه برطرف‌شده.
Received:
  نمایش 4 از 6 یافتهٔ فهرست‌شده. 2 مورد با این پالایش پنهان شده‌اند، نه برطرف‌شده.
```

Both mutations fail loudly with the actual vs. expected numbers visible. `ReportView.tsx` was
then reverted to the exact code already in this repository (`git diff` on the file after
reverting shows no residual change from the mutation), and the suite passes clean again (see
F2's run below).

**F2 — the `play` function is now a real, automated regression gate, wired into `make verify`.**
Investigated `@storybook/addon-vitest` (the addon Storybook itself recommends for Storybook
8+/Vite projects) against this repository's actual versions — Storybook `10.6.0`, Vite `6.4.3`
— and it installed and ran cleanly; no fallback to a manual/NOT-DONE path was needed.

- `services/web/package.json` devDependencies gained `@storybook/addon-vitest@10.6.0`,
  `vitest@4.1.11`, `@vitest/browser@4.1.11`, `@vitest/browser-playwright@4.1.11`, and
  `playwright@1.62.1` (pinned to the same release as the already-present
  `@playwright/test@1.62.1`, so both use the same already-installed Chromium build).
- `services/web/vitest.config.ts` (new file) configures a `storybook` Vitest project via
  `storybookTest({ configDir: ".storybook" })` from `@storybook/addon-vitest/vitest-plugin`,
  running in real headless Chromium through `@vitest/browser-playwright`'s `playwright()`
  provider — not jsdom, not a mock DOM.
- `services/web/.storybook/main.ts:5` registers the addon in the same `addons` array the
  existing `@storybook/addon-a11y` is already registered in:
  ```
  addons: ["@storybook/addon-a11y", "@storybook/addon-vitest"],
  ```
- `services/web/package.json:15` adds the runner script:
  ```
  "test-storybook": "vitest run --project=storybook",
  ```
  and `services/web/package.json:12` wires it into the existing gate:
  ```
  "verify": "pnpm run lint && pnpm run typecheck && pnpm run build && pnpm run build-workbench && pnpm run test-storybook",
  ```
  which `Makefile:42`'s `web-verify` target already runs (`cd $(WEB) && pnpm install
  --frozen-lockfile && pnpm run verify`), which `Makefile:19`'s `verify` target already
  depends on (`verify: lint types contracts test web-verify`) — so `make verify` now executes
  every story's `play` function for real, every time, with no separate opt-in step.

Since Storybook 10.3, `addon-vitest` composes each story's project annotations
(`.storybook/preview.tsx`'s decorators, MSW loader) automatically when it transforms the story
into a test — attempting a manual `setProjectAnnotations` setup file produced an explicit
console notice saying so and to remove it, which was done; there is no custom setup file.

Real run, standalone:

```
$ ./node_modules/.bin/vitest run --project=storybook

 RUN  v4.1.11 /home/alireza/Projects/cadgpt/services/web

 Test Files  9 passed (9)
      Tests  33 passed (33)
   Start at  09:19:33
   Duration  16.95s (transform 0ms, setup 47.72s, import 2.54s, tests 29.21s, environment 0ms)
```

Real run, as part of the actual `make verify` (full output; environment `gettext` shim from
the original evidence above still required and still used):

```
$ export PATH=/tmp/gettext-extract/usr/bin:$PATH
$ export LD_LIBRARY_PATH=/tmp/gettext-extract/usr/lib/x86_64-linux-gnu:$LD_LIBRARY_PATH
$ make verify
...
Contracts: 5 kept, 0 broken.
...
259 passed, 34 warnings in 5.15s
cd services/web && pnpm install --frozen-lockfile && pnpm run verify
...
> eslint .
> tsc -b --noEmit
> tsc -b && vite build
...
✓ built in 2.38s
> storybook build -o storybook-static --quiet
...
Storybook build completed successfully
> vitest run --project=storybook
...
 Test Files  9 passed (9)
      Tests  33 passed (33)
```

**Fresh positive-case dump, corrected numbers, real headless Chromium against the rebuilt
static Storybook** (same method as the original evidence block: `storybook-static` served over
HTTP, driven with Playwright): the three numbers are now 12 (engine-capped, never itemised),
6 (itemised), 4 (filter-hidden), consistent with `entity_limit = 3` on two requirements
(door-width: 3 kept + 8 omitted = 11; stairs: 3 kept + 4 omitted = 7):

```
---- CONSOLE / PAGE ERRORS ----
(none)

---- TESTID TEXT ----
filter-omitted-total[0]: 12 یافتهٔ دیگر، فراتر از 6 یافتهٔ فهرست‌شده در اینجا، وجود دارد — محدودیت موتور برای هر الزام باقی را پیش از اعمال این پالایش کنار گذاشته است، نه این پالایش.
filter-banner[0]: نمایش 2 از 6 یافتهٔ فهرست‌شده. 4 مورد با این پالایش پنهان شده‌اند، نه برطرف‌شده.
requirement-partially-hidden[0]: 1 از 3 یافتهٔ فهرست‌شده در اینجا با پالایش فعلی پنهان شده‌اند.
requirement-all-hidden[0]: همهٔ ردیف‌های این بخش با پالایش فعلی پنهان شده‌اند.
```

Screenshot regenerated: `services/web/e2e/screenshots/t0034-filter-banner-three-numbers.png`.

**Real e2e path re-run** (negative case, against the already-running backend containers —
`ReportView.tsx`'s production logic is byte-for-byte unchanged by this pass, confirmed above
by reverting both mutations back to the exact prior code, so this re-run is a regression check,
not new evidence about the fix itself):

```
$ ./node_modules/.bin/playwright test
Running 9 tests using 4 workers
  ✓ e2e/breadcrumbs.spec.ts:18:1 › ...
  ✓ e2e/report.spec.ts:34:1 › a real check run reproduces 1 pass / 1 fail / 1 indeterminate in the browser (12.8s)
  ✓ e2e/onboarding.spec.ts:25:1 › ...
  ✓ e2e/report-recovery.spec.ts:42:1 › ...
  ✓ e2e/upload-limit.spec.ts:19:1 › ...
  ✓ e2e/session-isolation.spec.ts:43:1 › ...
  ✓ e2e/report.spec.ts:202:1 › ...
  ✓ e2e/session-isolation.spec.ts:127:1 › ...
  ✓ e2e/report.spec.ts:292:1 › ...
9 passed (32.2s)
```

A full `docker compose build web` rebuild (to get a byte-identical fresh image) was attempted
first and failed on this sandbox's pre-existing network limitation, unrelated to this
change — the build container's `pnpm install` needs `corepack` to reach the npm registry and
gets `ECONNREFUSED 127.0.0.1:2080` (the same proxy-from-inside-the-build-network-namespace
issue the original evidence block already documented for `api`/`worker`/`beat`). The e2e run
above instead ran straight against the already-running `web` container (serving the same
`ReportView.tsx` this pass leaves unchanged) and the local Storybook build, which is what
actually needed to prove the positive case.

**F1/F2/F3 status: all three closed.** F1 — anchored, exact-string assertions that
demonstrably fail on both of the reviewer's mutations. F2 — `@storybook/addon-vitest` wired
in for real, no fallback needed; `make verify` now runs every `play` function as an automated
Vitest suite, not a one-shot manual script. F3 — the fixture obeys `check.py`'s own
`entities`/`entities_omitted`/`failed`/`indeterminate` arithmetic for one consistent
`entity_limit`, and carries no `PASS` row among itemised findings.

**NOT DONE (this pass):** nothing. F4/F5/F6 and the two nits are the review's own
non-blocking observations for the judge and are deliberately not touched here, per the
dispatch instructions for this fix-now pass.

## Review

**Verdict: fix now, same task.** The production change in `ReportView.tsx` is correct — the
reviewer confirmed `totalOmitted` sums `entities_omitted` (`check.py:160`) correctly, the three
numbers are genuinely distinct at runtime, `packages/engine`/`services/api` are untouched, and
no invariant (I1, tenancy, three-valued) is violated by the shipped code. The evidence block's
*proof*, not the fix, is what falsified:

- **F1 (fix now).** The Storybook `play` function's assertions
  (`ReportView.stories.tsx:107-130`) are all `toHaveTextContent(String(n))` — an unanchored
  substring match. Reviewer mutated the built bundle so `showing`'s `hidden` interpolation
  received `totalOmitted` (38) instead of the filter's own hidden count (3) — i.e. reintroduced
  the exact defect T-0034 removed, the cap re-attributed to the filter — and the play function
  passed clean, no exception, no console output: the same signature the evidence block cites as
  proof of correctness. A second mutation (swapping `shown`/`hidden`) also passed clean. The
  test cannot tell the fix from the bug it fixes.
- **F2 (fix now).** The play function is never executed by anything in this repository.
  `pnpm run verify` → `build-workbench` is `storybook build`, which does not run `play`; there
  is no `@storybook/test-runner`, `addon-vitest`, or `vitest` wired anywhere, and no CI step
  invokes one. The "component test" was run once, by hand, with an ad-hoc Node/Playwright
  script, and is not a regression guard — contradicting the evidence block's framing of it as
  "a component test."
- **F3 (fix now).** The fixture used for the positive case is not engine-shaped in the one
  dimension under test: `entities_omitted > 0` implies `len(entities) == CHECK_ENTITY_LIMIT`
  (500) per `check.py:159-160`, but the three fixture requirements carry three different,
  mutually inconsistent implied limits (5/8, 2/5, 0/25), and one `EntityOutcome` counted among
  "7 itemised findings" has `status: "PASS"`, which `check.py`'s `outcomes` (built from
  `facet.failures` only) cannot produce. The evidence block's "real engine-shaped payload"
  claim overstates what was exercised.

Sent back to the same builder per `docs/agents.md` ("Fix now — same task, same builder, no new
review afterward"). Non-blocking observations from the same review (F4: a redundant recomputation
of a quantity the report already carries elsewhere, which could disagree with it — no invariant
broken today but worth a judge look; F5: the real e2e assertion is a bare `toHaveCount(0)`
negative with no positive control; F6: `allHidden`'s wording still allows the pre-T-0034
conflation on a capped-and-filtered requirement; two nits) are recorded here for the judge, not
self-approved into the queue.
