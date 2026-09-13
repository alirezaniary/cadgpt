# T-0035 — Two latent defects in the report view: an unsortable list and a colliding key

**Phase:** 3 — What the first real user needs   **Status:** done
**Touches invariants:** none directly. Not reviewer-gated unless it grows.

## Why

Both found by the T-0025 review (Q2, Q3) by reading the code and reproducing in `node`. Neither
is reachable through today's payload; both are the kind of defect that surfaces once the wire
format moves, and `REPORT_SCHEMA_VERSION` exists precisely because it is expected to.

**One out-of-vocabulary status silently unsorts the entire list.** `ReportView.tsx:29`:
`SEVERITY_RANK[unknown]` is `undefined`, `undefined - n` is `NaN`, and `NaN || (a.index -
b.index)` falls through to index order — producing a non-transitive comparator that disables
severity ordering for every row, not just the unknown one. Observed:

```
input:  a:PASS b:WEIRD c:FAIL d:INDETERMINATE
output: a:PASS b:WEIRD c:FAIL d:INDETERMINATE   (unsorted -- FAIL left below PASS)
```

Reports are persisted documents read back by newer frontends. A FAIL sorted below a PASS
because a single row carried a status this build had not heard of is the severity ordering
T-0025 exists for, silently switched off. A `?? <rank>` default on the lookup makes the
degradation local to the unknown row.

**A non-unique React key.** `ReportView.tsx:167`: ``key={`${entity.global_id}-${entity.reason_code}`}``.
`global_id` is `string | null` for non-rooted entities, so two rows in one requirement with a
null GlobalId and the same reason code collide. The list is re-filtered on every toggle, and
duplicate keys leave React free to reconcile a stale row into a filtered view — which would
show the architect a row that the filter was asked to hide.

## Scope

`services/web/src/components/ReportView.tsx` only, plus a unit test per defect. No i18n, no
styles, no engine, no API.

- Give the rank lookup a defined default and decide deliberately where an unknown status ranks.
  It must not rank above FAIL and it must not be silently dropped.
- Include the pre-filter index in the row key.

## How to prove it ran

These are the two defects in this phase where a browser is not the right instrument — both are
pure functions over a payload. A test that feeds `bySeverity` a shuffled list containing an
unknown status and asserts FAIL still leads, and a test that renders two null-`global_id` rows
sharing a reason code and asserts both survive a filter toggle. `make verify` with both tests
named in the output, and the mutation proof for each: revert the fix, show the test failing.

`make e2e` is not required if no rendered text changed — say so rather than pasting an
unchanged screenshot.

## Evidence

### The two fixes

**Defect 1 (`services/web/src/components/ReportView.tsx`).** `bySeverity` now looks up rank
through a small `rank()` helper that falls back to `SEVERITY_RANK.INDETERMINATE` via `??`
when `status` is not one of the three known keys:

```ts
const UNKNOWN_STATUS_RANK = SEVERITY_RANK.INDETERMINATE;

export function bySeverity<T extends { status: Status }>(items: readonly T[]): T[] {
  const rank = (status: Status): number => SEVERITY_RANK[status] ?? UNKNOWN_STATUS_RANK;
  return items
    .map((item, index) => ({ item, index }))
    .sort((a, b) => rank(a.item.status) - rank(b.item.status) || a.index - b.index)
    .map(({ item }) => item);
}
```

Deliberate decision on where an unknown status ranks: tied with `INDETERMINATE` (rank 1) —
never above `FAIL` (rank 0, so a `FAIL` this build did establish is never pushed below an
unrecognised status), and never buried under `PASS` (rank 2, so an unknown is never silently
asserted as compliant either). `bySeverity` is exported (it was module-private before) so the
unit test below can feed it a status outside `Status`'s vocabulary directly — the one shape a
rendered test cannot exercise, because `EntityFilter`/`isVisible` in this same file has no key
for an unrecognised status either and would filter such a row out of the DOM before the sort
defect could ever be observed on screen. This exports one non-component value from a component
file, which is why `pnpm run lint` now prints one `react-refresh/only-export-components`
**warning** (not an error, does not fail `verify`) — noted here rather than hidden; fixing it
would mean moving `bySeverity` to a second file, which the task's scope line restricts to
"`ReportView.tsx` only."

**Defect 2 (`services/web/src/components/ReportView.tsx`).** The row key now includes the
entity's index in `orderedEntities` — assigned once, before the filter runs, so it stays a
stable, unique tiebreaker across a filter toggle even when two entities share a null
`global_id` and the same `reason_code`:

```ts
const visibleEntities = orderedEntities
  .map((entity, entityIndex) => ({ entity, entityIndex }))
  .filter(({ entity }) => isVisible(entity, filter));
...
{visibleEntities.map(({ entity, entityIndex }) => (
  <tr key={`${entity.global_id}-${entity.reason_code}-${entityIndex}`} ...>
```

### Tests

**Unit test for defect 1** — `services/web/src/components/ReportView.test.ts`, run as a new
plain Vitest project (`unit`, added to `vitest.config.ts` beside the existing `storybook`
project — no new test runner, same Vitest, same config file) via `pnpm run test-unit`, wired
into `pnpm run verify`:

```
> vitest run --project=unit
 Test Files  1 passed (1)
      Tests  2 passed (2)
```

`bySeverity` is fed a shuffled list `[PASS, WEIRD, PASS, FAIL, INDETERMINATE]` (`"WEIRD" as
unknown as Status`) and asserts: the list is not shortened (`sorted` has the same length,
`"unknown-1"` is present — not silently dropped), `sorted[0]?.status` is `"FAIL"` (FAIL still
leads), and the unknown row's index is strictly after the FAIL row's index (never ranks above
FAIL). A second test asserts the sort is stable for equal-severity rows.

**Mutation proof, defect 1** — reverted `rank` to `SEVERITY_RANK[status]` (no `??` fallback)
and reran `pnpm run test-unit`:

```
 FAIL  |unit| src/components/ReportView.test.ts > bySeverity > keeps FAIL leading, and never drops the row, when a status outside the vocabulary is present
AssertionError: expected 'PASS' to be 'FAIL' // Object.is equality
Expected: "FAIL"
Received: "PASS"
 ❯ src/components/ReportView.test.ts:46:31
     46|     expect(sorted[0]?.status).toBe("FAIL");
 Test Files  1 failed (1)
      Tests  1 failed | 1 passed (2)
```

Fix restored; reran `pnpm run test-unit` → `Test Files 1 passed (1)`, `Tests 2 passed (2)`.

**Story test for defect 2** — `services/web/src/components/ReportView.stories.tsx`, new story
`DuplicateGlobalIdKeysSurviveAFilterToggle`, run via the existing `@storybook/addon-vitest`
`storybook` project (headless Chromium) as it already does for this file's other stories, via
`pnpm run test-storybook`:

```
✓ |storybook (chromium)| src/components/ReportView.stories.tsx (5 tests | 4 skipped) 1764ms
   ✓ Duplicate Global Id Keys Survive A Filter Toggle  1757ms
```

The story renders `ReportView` against a report whose door-width requirement carries two
entities with `global_id: null` and `reason_code: "SAME_REASON_CODE"` (one `FAIL` — `detail:
"keyed-a"`, one `INDETERMINATE` — `detail: "keyed-b"`), replacing two of that requirement's
three kept entities (already documented in this fixture as sitting exactly at
`entity_limit`), with `requirement.failed`/`indeterminate` adjusted by one in the same way the
existing `withMixedRequirement` fixture already establishes is safe. The `play` function: (1)
asserts both `keyed-a` and `keyed-b` render before any filter is touched; (2) unchecks the
INDETERMINATE filter box and asserts `keyed-b` (INDETERMINATE) disappears while `keyed-a`
(FAIL) survives; (3) rechecks the box and asserts both reappear, each with its own content —
not one row duplicated under two labels, not one lost; (4) asserts `console.error` was never
called with a "same key" message across the whole sequence — the exact signal React itself
emits the instant it renders two siblings with the same key, which is the signal that survives
even where the rendered *text* alone might come out right by luck (this component's rows are
purely derived from props, with no per-row state, so a content-only assertion is not on its
own guaranteed to catch a key collision — the console assertion is).

**Mutation proof, defect 2** — reverted the key back to
`` `${entity.global_id}-${entity.reason_code}` `` (dropping `entityIndex`) and reran:

```
stderr | src/components/ReportView.stories.tsx > Duplicate Global Id Keys Survive A Filter Toggle
Encountered two children with the same key, `null-SAME_REASON_CODE`. Keys should be unique so
that components maintain their identity across updates. Non-unique keys may cause children to
be duplicated and/or omitted — the behavior is unsupported and could change in a future
version.
 ❯ |storybook (chromium)| src/components/ReportView.stories.tsx (5 tests | 1 failed | 4 skipped) 955ms
   × Duplicate Global Id Keys Survive A Filter Toggle 943ms
AssertionError:
console.error was called with: [["Encountered two children with the same key, ...", "null-SAME_REASON_CODE"]]: expected [ …(2) ] to be undefined
 Test Files  1 failed | 8 skipped (9)
      Tests  1 failed | 33 skipped (34)
```

Fix restored; reran → `Test Files 1 passed | 8 skipped (9)`, `Tests 1 passed | 33 skipped
(34)`.

### `make verify`

Ran the whole gate, not just the frontend slice. This sandbox has no system `gettext`
package (`msgfmt`) and no passwordless `sudo` to install one; a portable extraction of the
`gettext` `.deb` from an earlier session already existed under `/tmp/gettext-extract` (used
only to put `msgfmt` on `PATH`/`LD_LIBRARY_PATH` for `manage.py compilemessages` — this is
environment setup, not a change to any gated file; CI installs the same package via `apt-get`
in `.github/workflows/verify.yml`). Full output in `/tmp/make_verify2.log`; relevant lines:

```
uv run ruff check .            → All checks passed!
uv run ruff format --check .   → 187 files already formatted
uv run mypy packages/engine/src services/api/cadgpt → Success: no issues found in 170 source files
uv run lint-imports --no-cache → Contracts: 5 kept, 0 broken.
uv run pytest                  → 259 passed, 34 warnings in 4.48s
cd services/web && pnpm run verify
  eslint .                     → 1 warning (react-refresh/only-export-components on the
                                  bySeverity export above), 0 errors
  tsc -b --noEmit               → (clean)
  vite build                    → (clean)
  storybook build                → Storybook build completed successfully
  vitest run --project=unit     → Test Files 1 passed (1); Tests 2 passed (2)
  vitest run --project=storybook → Test Files 9 passed (9); Tests 34 passed (34)
```

`make verify` exit code: `0`.

### `make e2e`

Not run. No rendered text, translation key, or DOM structure visible to a screenshot changed
— both fixes are sort-order/key-identity logic invisible to a static screenshot, and the
existing story-level regression coverage above (real headless-Chromium rendering, real React
reconciliation, real `console.error`) is the applicable "real path" for this pair of pure
in-browser logic defects, exactly as the task's own "How to prove it ran" section anticipated
("a browser is not the right instrument" for the pure-function half, and the Storybook
play-function mechanism — already wired into `verify` for this exact file — for the
DOM-reconciliation half).

### Files touched

- `services/web/src/components/ReportView.tsx` — both fixes.
- `services/web/src/components/ReportView.test.ts` — new, unit test for defect 1.
- `services/web/src/components/ReportView.stories.tsx` — new story, test for defect 2.
- `services/web/vitest.config.ts` — added the `unit` Vitest project.
- `services/web/package.json` — added `test-unit` script, wired into `verify`.

### NOT DONE

Nothing. Both defects are fixed, both have a regression test proven by mutation, and
`make verify` passes end to end.

## Review
