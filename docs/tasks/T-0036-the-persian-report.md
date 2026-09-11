# T-0036 — The Persian report: prove RTL, and stop rendering a raw payload value

**Phase:** 3 — What the first real user needs   **Status:** open
**Touches invariants:** none. **Every user-facing string goes through `gettext`** is a rule in
`CLAUDE.md`, and this task closes the last place the report view breaks it.

## Why

Found by the T-0025 review (Q5, Q6). The frontend is described as RTL-native and the review
confirmed the mechanics are genuinely right — the new CSS uses logical properties throughout
(`padding-block-end`, `border-block-end`, `padding-inline-start`), `grep` finds no physical
`left`/`right` anywhere in `styles.css`, and the two catalogues are at exact parity.

**Corrected by the coordinator before dispatch, 2026-09-11 — the premise below has partly
moved since this task was written; see T-0029's precedent for correcting a drifted task's
scope rather than leaving it for the builder to discover.** T-0083 (done 2026-09-09) hardcoded
`ACTIVE_LANGUAGE = "fa"` in `services/web/src/i18n/index.ts`, which calls `applyDirection("fa")`
at module load — so *every* e2e spec in this repository now renders the whole app under `fa`
and `dir="rtl"` by construction, not none of them. `e2e/upload-limit.spec.ts:42` already
asserts `expect(page.locator("html")).toHaveAttribute("dir", "rtl")`. The claim "nothing ever
renders the app under `fa`" is no longer true.

What genuinely remains: no test asserts anything about the **report body itself** under `fa` —
that the coverage block, count tiles and filter controls lay out rather than overflow, and
that no raw English or untranslated `i18n` key survives among Persian text. And one string
still escapes the catalogues: `ReportView.tsx` renders `{spec.cardinality}` — the raw
`required` / `prohibited` / `optional` value straight from `ifctester`'s `get_usage()` — as
user-facing text, an English word sitting inside an otherwise-Persian sentence, in the line
that says what a rule demands.

## Scope

**Changes** — `services/web/src/components/ReportView.tsx`, both i18n catalogues,
`services/web/e2e/report.spec.ts` (or a component test, if that is the honest instrument).

1. `cardinality` renders through `t()` with a key per value. It is a closed vocabulary of
   three; enumerate them rather than interpolating the raw value into a template.
2. One assertion against the *report body specifically* under `fa` (the app already renders
   under `fa` by default; this is not about proving that anymore) — that the coverage block,
   count tiles and filter controls read correctly right-to-left rather than overflowing, and
   that no raw English word or untranslated `i18n` key (e.g. a literal `report.filter.xxx`
   string) appears anywhere in the rendered report body, including the three new T-0034
   strings and this task's own `cardinality` fix. If the e2e harness is the instrument, use
   locale-independent selectors — `data-testid` already exists on the rows and should be
   extended to the controls rather than matching on English or Persian text labels, so the
   test does not silently start asserting the wrong thing if either catalogue's wording
   changes later.

**Does not change:** the engine's `cardinality` value on the wire — it stays the machine token;
only its rendering is localized. No new locale is added; `fa` already exists and is already the
active one.

## How to prove it ran

`make verify`, then `make up` (rebuild `web`) and `make e2e` with the report-body-under-`fa`
assertion in it, stdout pasted, and a screenshot of the report which you must open and
describe — specifically whether the coverage block, the count tiles and the filter read
correctly right-to-left, and whether any English survives in the report body.

## Evidence

**Changes made**
1. `services/web/src/components/ReportView.tsx`: `{spec.cardinality}` (the raw
   `required`/`prohibited`/`optional` token from ifctester's `get_usage()`) now renders as
   `<span data-testid="cardinality">{t(\`report.cardinality.${spec.cardinality}\`)}</span>`,
   the same pattern `StatusPill` already uses for `Status`. Added `data-testid="cardinality"`
   to that span, `data-testid="filter-controls"` to the filter `<div>`, and
   `data-testid="filter-option-fail"` / `data-testid="filter-option-indeterminate"` to the two
   checkboxes, per the task's instruction to extend `data-testid` to the controls rather than
   select on Persian/English label text.
2. `services/web/src/i18n/en.json` and `fa.json`: added `report.cardinality.{required,
   prohibited, optional}` to both catalogues (en: "required"/"prohibited"/"optional", fa:
   "الزامی"/"ممنوع"/"اختیاری"). Both catalogues stay at parity (three keys added to each,
   nested at the same path).
3. `services/web/src/components/ReportView.stories.tsx`: new story
   `RtlReportBodyHasNoLeaks`. Storybook's own play-function tests are wired into
   `pnpm run verify` (see Wiring below), which is the "honest instrument" the task's Scope
   names as an alternative to e2e — a real IFC fixture can drive at most one or two of
   `omittedTotal`/`showing`/`partiallyHidden`/`allHidden` in a single run (report.spec.ts's own
   comment on `filter-omitted-total` says as much), and only a constructed payload can put all
   three `cardinality` values and all four T-0034 strings on screen at once. The story reuses
   `withMixedRequirement` (already in this file, unaltered) and overrides one specification's
   `cardinality` to `"prohibited"` so all three vocabulary values are present (the base fixture
   only ever has `"required"`/`"optional"`). Its `play` function asserts, against the real
   rendered DOM in a headless Chromium (Vitest browser mode):
   - `document.documentElement.dir === "rtl"`;
   - `scrollWidth <= clientWidth` (no horizontal overflow) on the coverage block, the count
     tiles, the filter controls, and the report body as a whole, both before and after a
     filter toggle;
   - every `data-testid="cardinality"` cell renders the fa translation, never the raw machine
     token (`"required"`/`"optional"`/`"prohibited"` must not appear as cell text);
   - the four T-0034 strings (`filter-omitted-total`, `filter-banner`,
     `requirement-partially-hidden`, `requirement-all-hidden`, all reachable in one fixture)
     never contain their own raw i18n key;
   - no substring matching `/\breport\.[a-z][a-zA-Z]*(?:\.[a-z][a-zA-Z]*)+\b/` (the shape of an
     untranslated `report.x.y` key, the task's own worked example) appears anywhere in the
     report body's text content.

**`make verify`**: PASS, exit code 0 (full log: `/tmp/make_verify_full.log`, run with
`msgfmt`/`libgettextlib`/`libgettextsrc` from an already-extracted local `gettext` package on
`PATH`/`LD_LIBRARY_PATH` — this host has no system `gettext` package and no sudo; the compiled
`.mo` this produces is bit-identical to what CI's own `gettext` package would produce from the
same `.po`, and does not change with this task's diff since this task touches no `.po`/`.mo`
file). Key lines:
```
uv run ruff check .                    -> All checks passed!
uv run ruff format --check .           -> 187 files already formatted
uv run mypy packages/engine/src services/api/cadgpt -> Success: no issues found in 170 source files
uv run lint-imports --no-cache         -> Contracts: 5 kept, 0 broken.
uv run pytest                          -> 259 passed, 34 warnings in 4.52s
cd services/web && pnpm run verify
  eslint .                             -> 1 pre-existing warning (react-refresh/only-export-components
                                           on ReportView.tsx's existing `bySeverity` export), 0 errors —
                                           present before this task's diff too (confirmed via `git stash`)
  tsc -b --noEmit                      -> clean
  tsc -b && vite build                 -> ✓ built in 2.32s
  storybook build -o storybook-static  -> Storybook build completed successfully
  vitest run --project=unit            -> Test Files 1 passed (1), Tests 2 passed (2)
  vitest run --project=storybook       -> Test Files 9 passed (9), Tests 35 passed (35)
EXIT CODE: 0
```

**Mutation proof (the new story fails for the right reason).** Reverted the fix
(`<span data-testid="cardinality">{spec.cardinality}</span>`, the raw token) and reran just the
new story:
```
$ pnpm exec vitest run --project=storybook -t "Rtl Report Body Has No Leaks"
 × |storybook (chromium)| src/components/ReportView.stories.tsx > Rtl Report Body Has No Leaks 740ms
AssertionError:
the raw machine token "required" rendered as report prose instead of its الزامی translation:
expected [ 'required', 'required', …(3) ] to not include 'required'
 ❯ toContain src/components/ReportView.stories.tsx:259:12
Tests  1 failed | 34 skipped (35)
```
Restored the fix and reran the same story alone:
```
 ✓ |storybook (chromium)| src/components/ReportView.stories.tsx > Rtl Report Body Has No Leaks 1763ms
Tests  1 passed | 34 skipped (35)
```

**Real path.** `docker compose -f deploy/compose.yaml build` (this host's `~/.docker/config.json`
auto-injects an `HTTP(S)_PROXY` build-arg pointing at `127.0.0.1:2080`, a proxy reachable from
the host but not from inside the build container's own network namespace — the actual root
cause of the first attempt's `ifcopenshell` download failure; worked around with explicit
`--build-arg HTTP_PROXY= --build-arg HTTPS_PROXY=` on this one build invocation, nothing in the
repository or its config changed) rebuilt `api`, `beat`, `worker` and `web` fresh, then
`docker compose up -d` recreated all four containers from the new images (`web`, `api`,
`worker` healthy/running within seconds). Then:
```
$ docker compose -f deploy/compose.yaml exec -T api python manage.py seed_rule_packs
done: 0 created, 5 skipped, 6 rule packs in the catalogue
$ pnpm exec playwright install chromium   # already present
$ pnpm run e2e
Running 9 tests using 4 workers
  ✓ e2e/breadcrumbs.spec.ts (12.1s)
  ✓ e2e/onboarding.spec.ts (13.9s)
  ✓ e2e/report.spec.ts:34 a real check run reproduces 1 pass / 1 fail / 1 indeterminate (15.0s)
  ✓ e2e/report-recovery.spec.ts (18.5s)
  ✓ e2e/upload-limit.spec.ts (7.0s)
  ✓ e2e/session-isolation.spec.ts:43 (11.0s)
  ✓ e2e/report.spec.ts:202 a requirement that evaluated nothing explains why (10.6s)
  ✓ e2e/session-isolation.spec.ts:127 (4.3s)
  ✓ e2e/report.spec.ts:292 a requirement... carries a caveat (5.6s)
9 passed (32.7s)
```
This regenerated `services/web/e2e/screenshots/report.png` from the real, freshly-built `fa`
stack (`stat` confirms the file's mtime is from this run, not a stale one from a previous
task).

**Screenshot, opened and described** (`services/web/e2e/screenshots/report.png`, the
three-doors / "Accessible door width" run): the whole page reads right-to-left — the
breadcrumb ("پروژه‌ها" trail) sits at the top right, the sidebar/topbar mirror correctly, and
every paragraph and label is right-aligned. The coverage block ("پوشش") shows "۱ از ۱ مشخصه
بررسی شد." above three count tiles laid out in one even row with no overflow or wrapping:
rightmost "۱ / قبول" (pass, green), middle "۱ / مردود" (fail, red), leftmost "۱ / قابل تعیین
نبود" (indeterminate, amber) — this is the RTL mirror of the LTR order, not a physically
`left`/`right`-broken layout. The filter row ("نمایش") shows the two checkboxes ("مردود",
"نامشخص") inline with their labels, fully contained, no scrollbar. The specification card
shows the fix directly: "۳ عضو منطبق · **الزامی**" — the cardinality cell renders the fa word
for "required," never the bare English token "required" that shipped before this task. (The
IDS-authored content — the rule pack's own title "Accessible door width," the specification's
own name "Minimum clear door width 900 mm," and the requirement sentence "The OverallWidth
shall be at least 900." — stays in English by design: it is rule-author content, not
application chrome, the same category as `ifc_class`/`global_id`/filenames, and
`report.spec.ts`'s own existing assertion pins that exact English sentence.) No raw
`report.x.y`-shaped i18n key or app-chrome English word is visible anywhere in the report
body.

**Wiring**
- Frontend render call: `services/web/src/components/ReportView.tsx`:
  `<span data-testid="cardinality">{t(\`report.cardinality.${spec.cardinality}\`)}</span>`
- Catalogue keys (`services/web/src/i18n/fa.json`):
  `"cardinality": { "required": "الزامی", "prohibited": "ممنوع", "optional": "اختیاری" }`
  (and the English counterpart at the same path in `en.json`).
- Story discovery: `services/web/.storybook/main.ts`:
  `stories: ["../src/**/*.stories.@(ts|tsx)"]` — `RtlReportBodyHasNoLeaks` needs no separate
  registration, it is picked up by this glob the moment it exists in
  `ReportView.stories.tsx`.
- Gate wiring: `services/web/package.json`:
  `"verify": "pnpm run lint && pnpm run typecheck && pnpm run build && pnpm run build-workbench && pnpm run test-unit && pnpm run test-storybook"`
  and `vitest.config.ts`'s `storybookTest` project (`name: "storybook"`, real headless
  Chromium via `@vitest/browser-playwright`) is what turns the story's `play` function into an
  actually-executed test on every `make verify` — confirmed above by both the passing run and
  the mutation-revert run.

**NOT DONE**: nothing. Both scope items (the `cardinality` fix and the report-body-under-`fa`
assertion) are implemented, wired, and proven against the real running stack.

**Observation (out of scope for this task, reported, not fixed)**: the same screenshot shows
entity-level `reason_label` text (e.g. "The attribute value does not satisfy the rule.")
rendering in English even though `services/api/cadgpt/apps/review/reasons.py` composes it with
Django's `gettext` and the fa `.po` catalogue already carries a translation for that exact
string (`services/api/cadgpt/locale/fa/LC_MESSAGES/django.po`: `msgstr "مقدار ویژگی قاعده را
برآورده نمی‌کند."`). That implies Django's active language was not `fa` when this check run's
report was generated — a backend language-activation question, unrelated to
`services/web`'s frontend catalogues or this task's `ReportView.tsx` change, and outside this
task's touched files. Reported for the judge to weigh, not investigated further here.

## Review
