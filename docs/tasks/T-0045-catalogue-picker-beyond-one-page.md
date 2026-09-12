# T-0045 — The catalogue picker must show every pack, and filter on the server

**Phase:** 3   **Status:** done
**Touches invariants:** none structurally, but this is the coverage failure in the picker.

## Why

**Corrected by the coordinator before dispatch, 2026-09-12, following the T-0029/T-0036/T-0041
precedent for a drifted task file:** this task was written before T-0074 (done 2026-09-04)
replaced `ReviewsPage.tsx` with `features/project/ProjectDetailPage.tsx` and
`features/review/ReviewDetailPage.tsx`. The catalogue picker described below now lives in
`ReviewDetailPage.tsx` (`data-testid="catalogue-picker"`, `catalogueFilter` state,
`filteredPacks` memo) — the premise and the defect are otherwise unchanged.

Found by the T-0031 review. `services/web/src/api/queries.ts`'s `useRulePacks` fetches
`/v1/rule-packs/` with no `size` parameter and never follows `next`; `SimplePagination.page_size`
is 20 (`services/api/cadgpt/apps/base/drf/pagination.py:16`). `ReviewDetailPage.tsx` then filters
that one page client-side with `String.includes` (`pack.jurisdiction.toLowerCase().includes(...)`
etc., in its `filteredPacks` memo).

The moment the catalogue exceeds 20 packs a user filtering for a jurisdiction whose packs sit on
page 2 is shown `review.catalogue.empty` — *"No packs match this filter."* — and cannot select
them. The packs exist, the filter is correct, and the product says nothing matches. **That is
silent narrowing of what can be picked, dressed as an empty result**, and it is the same class of
failure T-0031 refused on the server side.

It is not hypothetical: the plan's stated near-term path is Iranian building code, then EU, then
US. Twenty is one jurisdiction's worth.

`RulePackFilterSet` (`services/api/cadgpt/apps/rulepack/api/v1/filters.py`) already exposes
server-side `jurisdiction`, `region` and `version` filters that the frontend does not use, so the
client is reimplementing — with different semantics — a filter that already exists. The client's
substring `includes` diverges from the server's `iexact`, which means the two disagree about what
matches even within one page.

## Scope

**Changes**

- `ReviewDetailPage.tsx`'s picker filters through the existing server-side `RulePackFilterSet`
  rather than over one client-held page, so the result set is the catalogue and not the first
  20 rows of it.
- The list is either fully paged through or explicitly paged in the UI. Decide which and say why
  in the evidence — a picker that loads everything is fine at catalogue scale and honest; a
  picker that loads one page and does not say so is not.
- The empty state must distinguish **"no packs match this filter"** from **"the catalogue has not
  loaded yet"**. Both i18n catalogues.

**What explicitly does not change**

- `RulePackFilterSet` itself, or the pagination default. Both are correct; the frontend is what
  ignores them.
- The selection wire format, the run record, the refusal logic. T-0031 settled those.

## How to prove it ran

`make verify`, then against `make up`:

1. Seed the catalogue past one page — **more than 20 packs** — and show a pack on page 2 being
   found by a filter and successfully selected, ending in a completed run that cites it.
2. The pre-fix behaviour reproduced once, so the defect is on record: the same filter returning
   the empty state before the change.
3. Rendered evidence from `make e2e`'s chromium, not curl. The defect is in the browser.

## Evidence

### What changed

- `services/web/src/api/queries.ts` — `useRulePacks(tenant, filter: RulePackFilter)` now sends
  `jurisdiction`/`region`/`version` to `/v1/rule-packs/` (the same fields `RulePackFilterSet`
  exposes, `iexact`) and walks every page with `size=100`
  (`SimplePagination.max_page_size`) until `page >= pages`, returning the full, already-filtered
  `RulePack[]`. `keys.rulePacks` now keys on `(tenant, filter)`.
- `services/web/src/features/review/ReviewDetailPage.tsx` — `catalogueFilter` still drives the
  three inputs directly; a debounced `queryFilter` (300ms) is what's actually sent to
  `useRulePacks`, so the server is asked once per pause in typing, not once per keystroke. The
  old `filteredPacks` client-side `.includes` memo is gone — `packs = rulePacks.data ?? []` is
  already server-filtered and complete. Three states are now rendered distinctly:
  `data-testid="catalogue-loading"` (`rulePacks.isLoading`), `data-testid="catalogue-empty"`
  (loaded, zero rows), and a plain `error.generic` line for `rulePacks.isError` (a fetch that
  never answered is not "no match" either — the same silent-narrowing failure this task exists
  to remove, for a different reason).
- `services/web/src/i18n/en.json` / `fa.json` — added `review.catalogue.loading`
  ("Loading the catalogue…" / "فهرست در حال بارگذاری است…") beside the existing
  `review.catalogue.empty`.
- New permanent regression spec `services/web/e2e/catalogue-pagination.spec.ts` (two tests, see
  below).

### Decision: walked in full, not paginated in the UI

The picker walks every page of the (filtered) result rather than adding Next/Previous controls.
Reasoning: the catalogue is one row per shipped jurisdiction/region/version pack — `docs/plan.md`
Phase 3's own near-term path is "Iranian building code, then EU, then US", i.e. low hundreds of
rows at the outside for years, not a per-tenant list that grows without bound. At that scale,
loading the full (filtered) result and rendering it as one list is the "picker that loads
everything, at catalogue scale, and is honest about it" the task itself calls out as fine —
adding pagination chrome to a multi-select checklist this small would only add UI state to keep
in sync with `selectedPacks` for no real benefit. `RULE_PACK_PAGE_SIZE = 100`
(`SimplePagination.max_page_size`) keeps the *fetch* to the fewest round trips regardless: with
25 packs seeded for this evidence, the whole filtered result already arrives in one request; a
future catalogue past 100 would need a second internal page, which the walk already handles
(`while page < pages`), transparently to the UI.

### Loading vs. empty vs. error, in both catalogues

`en.json`/`fa.json` both carry `review.catalogue.loading` next to `review.catalogue.empty` — the
UI chrome's active language is the build-time constant `fa` (`src/i18n/index.ts`, `en.json` is
`fallbackLng` only, never rendered directly by this SPA), so the browser evidence below is
Persian; the English half of the same distinction is the `en.json` key itself, exercised by
`make verify`'s frontend build (both catalogues are bundled and validated as JSON/i18next
resources) — see screenshots below for the Persian strings actually rendering in Chromium.

### `make verify`

Full run, pasted in order (fixed a genuinely missing `msgfmt` — see below — before this could
even start; not a code change):

```
$ make verify
uv run ruff check .                        All checks passed!
uv run ruff format --check .               191 files already formatted
uv run mypy packages/engine/src services/api/cadgpt    Success: no issues found in 173 source files
uv run lint-imports --no-cache             Contracts: 5 kept, 0 broken.
cd services/api && uv run --project .. python manage.py compilemessages   (compiled)
uv run pytest                              296 passed, 34 warnings in 4.69s
cd services/web && pnpm install --frozen-lockfile && pnpm run verify
  eslint .                                 0 errors, 2 warnings (pre-existing, unrelated files)
  tsc -b --noEmit                          (clean)
  tsc -b && vite build                     ✓ built in 2.19s
  storybook build -o storybook-static      ✓ built in 8.71s
  vitest run --project=unit                2 passed
  vitest run --project=storybook           35 passed (9 files)
```

Environment note (not a code change, listed for whoever runs this next): this sandbox's
`services/api` gate depends on GNU gettext's `msgfmt` (`make messages`/`compile-messages`,
`Makefile:73`), which was not installed and had no root access to `apt-get install`. Fixed by
downloading the `gettext` `.deb` with `apt-get download` (no root needed), extracting it under
`~/.local/gettext-extract`, and placing a `~/.local/bin/msgfmt` shim that sets
`LD_LIBRARY_PATH` to the extracted `libgettextlib`/`libgettextsrc` before exec'ing the real
binary. `~/.local/bin` is already first on `PATH` in this shell, so this is transparent to
`make verify` and does not touch the repo.

### Real path: `make up`, seeded past one page, page-2 pack selected and cited

Stack: `make up` (rebuilt `web` on the fixed code; `api`/`worker`/`beat` were already running
and untouched by this task — see below for why a full `docker compose build` of `api` could not
complete in this sandbox).

Seeded 15 extra packs onto the existing 10 (`sample` jurisdiction, from `manage.py
seed_rule_packs`), reusing the real engine fixture `door_width.ids` under 15 distinct
jurisdiction labels and a distinct version (`9.9`, chosen only so it can't collide with any
existing `v0.1` pack's text in other specs' loose locators — see "found in passing" below) —
**not** an invented regulation; the seed's own `source_citation` says exactly what it is:

```
$ docker exec cadgpt-api-1 python manage.py shell -c "
from pathlib import Path
from cadgpt.apps.rulepack.services import RulePackService
service = RulePackService()
ids_path = Path('/app/packages/engine/tests/fixtures/door_width.ids')
citation = ('cadgpt engine test fixture ... seeded 15 times under distinct jurisdiction '
            'labels and a distinct version, purely to push the rule pack catalogue past '
            'one page of SimplePagination.page_size (20) for T-0045 real-path evidence.')
for i in range(1, 16):
    service.seed(ids_path=ids_path, jurisdiction=f'z-t0045-page2-{i:02d}',
                 region='', version='9.9', source_citation=citation)
"
created 15
total 25
```

Catalogue ordering (`RulePack.Meta.ordering` = `RulePackViewSet.ordering` =
`(jurisdiction, region, name, version)`) puts the 10 `sample` packs at positions 1–10 and the 15
`z-t0045-page2-*` packs at 11–25 — `z-t0045-page2-12` sits at **position 22**, past the pre-fix
picker's one-page, 20-row fetch:

```
1  sample            Accessible door width                            0.1
...
10 sample            Restricted predefined type applicability         0.1
11 z-t0045-page2-01  Accessible door width                            9.9
...
22 z-t0045-page2-12  Accessible door width                            9.9   <-- target
...
25 z-t0045-page2-15  Accessible door width                            9.9
total 25
```

`make e2e`'s chromium project, new spec `catalogue-pagination.spec.ts`:

```
✓ [chromium] › catalogue-pagination.spec.ts:30 › a pack seeded past the catalogue's first page
  is found by a server-side filter, selected, and cited by a completed run  (12.2s)
✓ [chromium] › catalogue-pagination.spec.ts:92 › the picker distinguishes a filter matching
  nothing from the catalogue not having answered yet  (12.5s)
```

Test 1 types `z-t0045-page2-12` into the jurisdiction field, waits for the debounced
server-side filter to return exactly that row (position 22), selects it, clicks "run check",
waits for the report, and asserts `[data-testid="rule-pack-selection"]` (the run's own citation,
T-0031, never re-derived from the live catalogue) contains `z-t0045-page2-12`. Screenshot:
`services/web/e2e/screenshots/catalogue-page-two-selected.png` — the filter field reads
`z-t0045-page2-12`, the matching pack is checked, and the rendered report's "Rule packs
checked" section reads `Accessible door width — z-t0045-page2-12 v9.9`.

Test 2 delays `**/v1/rule-packs/**` responses by 1.5s to make the loading branch observable,
asserts `catalogue-loading` is visible and `catalogue-empty` is absent during that window
(screenshot `catalogue-loading.png`, Persian: "فهرست در حال بارگذاری است…"), then types a
jurisdiction guaranteed to match nothing and asserts `catalogue-empty` is visible and
`catalogue-loading` is absent (screenshot `catalogue-empty.png`, Persian: "هیچ بسته‌ای با این
پالایش مطابقت ندارد.").

### Pre-fix defect reproduced once, in the browser

`git stash push -- services/web/src/features/review/ReviewDetailPage.tsx
services/web/src/api/queries.ts` restored the exact pre-fix code (client-side `.includes` over
one unfiltered page). Rebuilt the `web` image on that code, redeployed the container, and ran a
throwaway spec (`_t0045_prefix_repro.spec.ts`, deleted immediately after, never committed) typing
the *exact* jurisdiction of a pack that genuinely exists (`z-t0045-page2-12`, position 22):

```
✓ [chromium] › PRE-FIX DEFECT: a pack that genuinely exists past the catalogue's first page
  reads as no match  (3.6s)
```

Screenshot: `services/web/e2e/screenshots/PREFIX-DEFECT-catalogue-empty-false-negative.png` —
the jurisdiction field reads `z-t0045-page2-12` and the picker still says "هیچ بسته‌ای با این
پالایش مطابقت ندارد." (no packs match this filter), for a pack that is on the very page the
screen is showing filter results for. This is the defect described in "Why", captured live.

`git stash pop` restored the fix; the `web` image was rebuilt again (`docker inspect` on the
resulting image and the earlier fixed build show the identical layer digest,
`sha256:f2a53e...`, confirming byte-identical output), and the container redeployed before any
further evidence was gathered.

### Full `make e2e`, fixed code, after restoring the stash

```
$ make e2e
✓ breadcrumbs.spec.ts                                                          (10.0s)
✓ catalogue-pagination.spec.ts › page-2 pack found, selected, cited            (12.2s)
✓ onboarding.spec.ts                                                           (15.3s)
✓ report-recovery.spec.ts                                                     (16.1s)
✓ routing.spec.ts (both)
✓ report.spec.ts:34 › 1 pass / 1 fail / 1 indeterminate                       (12.6s)
✓ catalogue-pagination.spec.ts › loading vs. empty                            (12.5s)
✓ session-isolation.spec.ts (both)
✓ upload-limit.spec.ts
✓ report.spec.ts:202 › evaluated nothing
✓ report.spec.ts:292 › applicability caveat
✘ report.spec.ts:380 › restricted attribute name / two-facet applicability
✓ report.spec.ts:511 › Persian applicability
14 passed, 1 failed
```

### Found in passing, both out of this task's scope, neither silenced

1. **Repaired, not code:** the very first full `make e2e` run after seeding turned up
   `FileNotFoundError` on the pre-existing `sample`/"Accessible door width" pack's
   `source_file` (`.../mediafiles/rule-packs/sample/d98b2136-....ids` did not exist on disk,
   though the DB row did) — a storage/DB drift that predates this task (the row and its seed
   citation are original T-0030 data), breaking `onboarding.spec.ts`, `report-recovery.spec.ts`
   and `report.spec.ts`'s main test, none of which touch anything T-0045 changed. Deleted the
   one orphaned row and let `manage.py seed_rule_packs` (idempotent, unmodified) recreate it
   with a real file; verified afterwards no other `RulePack.source_file` is missing on disk.
   Pure data repair, no line of product code touched.
2. **Reported, not fixed (out of scope):** `report.spec.ts:380` (`a restricted attribute name
   renders as its own sentence...`) fails independently of this task —
   `.locator("li", { hasText: "Restricted attribute name" }).filter({ hasText: "v0.1" })`
   resolves to 2 elements once `door_name_restricted_with_bound.ids` ("Restricted attribute
   name with a value bound") exists in the catalogue, because the older locator has no
   jurisdiction/uniqueness anchor and "Restricted attribute name" is a substring of the newer
   pack's name too. Confirmed this is unrelated to any change here: both packs were already
   present in the `sample` seed before this task started, and none of this task's 15 added
   packs share that name. This is `report.spec.ts`'s own locator, last touched around the
   "T-0039 review, F1" fixture addition per `seed_rule_packs.py`'s comments — flagging as an
   observation rather than editing another task's spec file out of scope.

### Cleanup

The throwaway pre-fix repro spec was deleted before finishing;
`services/web/e2e/catalogue-pagination.spec.ts` is the only new file kept, as a permanent
regression test — it depends on the 25-pack catalogue seeded above (including
`z-t0045-page2-12`) continuing to exist in this environment, the same precondition
`report.spec.ts` already documents for its own catalogue packs (seeded via `manage.py
seed_rule_packs`, run once against the real stack).

### Wiring

`RulePackViewSet` (`services/api/cadgpt/apps/rulepack/api/v1/views.py:79`):
`filterset_class = RulePackFilterSet` — unchanged, already registered; this task only made the
frontend actually call through it with `jurisdiction`/`region`/`version` query params instead of
ignoring it. Frontend call site: `ReviewDetailPage.tsx`, `const rulePacks =
useRulePacks(slug, queryFilter);` — the only caller of `useRulePacks`, itself the only exported
hook wired to `/v1/rule-packs/` (`services/web/src/api/queries.ts`).

### NOT DONE

Nothing. Every item in Scope landed: server-side filtering, full paging (walk-through, decision
recorded above), and the three-way loading/empty/error distinction in both `en.json` and
`fa.json`. `RulePackFilterSet`, the pagination default, the selection wire format, the run
record and the refusal logic were not touched.

## Review
