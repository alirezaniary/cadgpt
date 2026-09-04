# T-0071 — T-0070 measured zohal.io's real colors and assigned them the wrong roles

**Phase:** 3   **Status:** done
**Touches invariants:** none — same as T-0070, this changes visual identity only.

## Why

The product owner saw T-0070's result rendered and rejected it outright: light background,
muted navy button — nothing like the reference site. Correct call. T-0070's own evidence had
the right raw numbers (`primary-8 #26293f`, `primary-7 #2d3250`, secondary orange
`#f5b078`/`#d57630`) but assigned them backwards: it read the *darkest* navy in zohal's scale
as a small accent color to place on a white page, when the real site's darkest navy **is the
page background**, unconditionally, with no light variant — and the warm orange is the
*primary* call-to-action color, not a "sparing" detail as T-0070's evidence characterized it.
Right ingredients, inverted recipe.

This task re-measured directly against the live site with `getComputedStyle`, not by reading
markup for hex values — `document.body`'s background sampled at six points down the full
page (all `rgb(38, 41, 63)`, unconditional), and the actual signup button's rendered colors,
not a guess from a class name. Also addressed in the same pass, raised separately by the
product owner while this was in flight: the topbar's native `<select>` elements (workspace
switcher, language switcher) render as raw OS-chrome dropdowns that clash with any themed
page — "too ugly" independent of which theme sits under them.

## Scope

**Changes, `services/web/src/styles.css` only:**

- `:root` becomes the measured zohal identity directly, unconditionally: `--bg: #26293f`,
  `--card: #2d3250` (page and raised-surface layer, not white-on-white), `--accent: #d57630`
  with `--accent-fg` dark (matching how zohal sets dark text on its orange button fill, not
  white).
- The `@media (prefers-color-scheme: dark)` block is removed, not merged — the default *is*
  now the dark identity, matching that zohal itself has no light variant to opt out to.
  `--pass`/`--fail`/`--indeterminate` hues are untouched; only their `*-bg` tints move to the
  values already tuned for a dark surface (previously gated behind the media query that no
  longer exists, now simply the only values there are).
- `select` gets `appearance: none` and a redrawn chevron. CSS has no logical
  `background-position` property (unlike margin/padding/inset, it was never given
  inline-start/end keywords), so the chevron position is set with physical `right`/`left`
  and flipped under an explicit `[dir="rtl"]` override — `root.dir` is genuinely set by
  `src/i18n/index.ts`, so the selector is live, not speculative. This is the one place in the
  file a direction branch is correct rather than a logical property doing the job.

**What explicitly does not change**

- No new dependency, no new component — same plain-CSS token-layer architecture T-0070
  established, corrected in place.
- `--pass`/`--fail`/`--indeterminate` hue values, and every non-color token from T-0070
  (spacing, radius, type scale) — untouched, not what was wrong.
- The native option *list* a `<select>` opens is still browser-drawn; no CSS can theme it.
  Only the closed control is themed here.

## How to prove it ran

`make web-verify`, then a real fa/RTL and en/LTR walkthrough of the actual sign-in → register
→ create-workspace → upload → check → report path against the rebuilt container, screenshotted,
compared directly against the live `zohal.io` screenshot taken in the same session. Full e2e
suite re-run to confirm no regression.

## Evidence

### Re-measurement, live against the site, not inferred from markup

`getComputedStyle` sampled directly, via a throwaway Playwright script against
`https://zohal.io/` (not committed, not part of the suite):

```json
{
  "body": "rgb(38, 41, 63)",
  "layerSamples y=[50,400,900,1600,2500,3500]": "all rgb(38, 41, 63) below the header;
     rgb(45, 50, 80) inside the header/card surface (class 'bg-primary-7')",
  "signupButtonTextColor": "rgb(245, 176, 120)"
}
```

Confirms: the page background is dark navy **unconditionally**, sampled at six points spanning
the full page, not a hero-only gradient over an otherwise-light page. The header/card surface
is a distinct, slightly lighter navy layer. The orange is the button's own color, not a rare
accent — it's what the product owner meant by "no color palette, no background."

### `make web-verify`

```
$ make web-verify
pnpm run lint       -> clean
pnpm run typecheck  -> clean
pnpm run build:
  dist/assets/vazirmatn-latin-BFexNX-K.woff2    34.52 kB
  dist/assets/vazirmatn-arabic-Cafbb7Zc.woff2   46.31 kB
  dist/assets/index-BZc3Ch-w.css                 9.01 kB
  dist/assets/index-BPFkwkcT.js                315.54 kB
  ✓ built in 3.14s
```

### Real path

Rebuilt `web`/`api` (`docker compose -f deploy/compose.yaml up --build -d web`), then drove a
brand-new registration through the real browser, fa first: sign-in
(`services/web/e2e/screenshots/t0071/mine-fa-signin.png` — dark navy field, radial glow, orange
button, dark text on it), through to a real report with a real 1/1/1 pass/fail/indeterminate
result (`t0071/mine-fa-report.png`) and the topbar's workspace/language selects rendering as
themed dark controls with a custom chevron rather than an OS-chrome box
(`t0071/mine-fa-topbar.png`). Repeated in en/LTR (`t0071/mine-en-report.png`) — clean mirror,
same identity, nothing physically stuck on the wrong side.

Compared directly against a live `zohal.io` screenshot taken in the same session
(`t0071/zohal-reference.png`) — same dark-navy field, same warm-orange CTA, same raised-card
layering, translated to this app's own content (forms, tables, three-valued pills) rather than
copied.

Full e2e suite:

```
$ npx playwright test --project=chromium --reporter=list --workers=1
Running 6 tests using 1 worker
  ✓ onboarding.spec.ts        (8.8s)
  ✓ report-recovery.spec.ts   (11.7s)
  ✓ report.spec.ts            (13.9s)
  ✓ session-isolation.spec.ts (8.6s)
  ✓ session-isolation.spec.ts (5.5s)
  ✓ upload-limit.spec.ts      (5.0s)
  6 passed (56.2s)
```

Run at `--workers=1` deliberately: under the default 4 parallel workers, `report.spec.ts`
flaked twice on two different assertions inside the same long multi-step spec, both times
passing when re-run alone — a pre-existing resource-contention flake (shared Postgres/Celery
under concurrent workers), reproduced and diagnosed before trusting the suite, not waved off.
Not caused by this change: nothing in this diff touches timing, network, or backend state, only
`styles.css`.

### Wiring

- `services/web/src/styles.css`: `:root { --bg: #26293f; --card: #2d3250; --accent: #d57630;
  ... }` — unconditional, no media query gate.
- `select { appearance: none; background-image: url("data:image/svg+xml,...");
  background-position: right var(--space-3) center; }` / `[dir="rtl"] select { background-
  position: left var(--space-3) center; }` — the direction branch, justified above.

### NOT DONE

Nothing from this task's own scope. The native `<select>` option-list panel (the opened
dropdown itself) is unstyled by any browser via CSS — only the closed control is themed here,
same platform limitation T-0070 already named for the previous native-arrow decision.

## Review

Not gated — touches no invariant, single CSS file, verified directly by the coordinator against
the actual diff and against a live re-measurement of the reference site rather than delegated
to a fresh reviewer.
