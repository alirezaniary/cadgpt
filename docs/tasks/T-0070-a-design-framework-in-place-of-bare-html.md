# T-0070 — A design framework, RTL-Persian-first, in place of bare HTML

**Phase:** 3   **Status:** done
**Touches invariants:** none. Dual-language stays exactly as it is — this changes which
direction the design is authored *from*, not which languages the product serves.

## Why

Confirmed by the product owner after seeing T-0067's new screens rendered: the frontend has no
design system. `styles.css` is two structural classes (`card`, `centered`) plus raw browser
defaults on every `input`, `select`, and file picker — that predates T-0067 (`ReviewsPage`
already looked this bare) and T-0067 correctly matched it rather than making two screens pretty
in isolation. The product owner's words: "garbage and hideous."

The direction settled in conversation, not to be re-asked: **RTL Persian is the primary,
native design target — not an LTR design mirrored for RTL.** The app already has the
mechanics for this right (`services/web/src/i18n/index.ts`'s `directionFor`, `styles.css`'s
logical-properties discipline, `dir` flipping on the root, Vazirmatn already the Persian font
stack) — what's missing is a visual language to hang off that mechanism, not the mechanism
itself. English support is unchanged: same `gettext`/i18next pipeline, same two locales, no
change to `docs/decisions.md`'s multinational-tenant stance. Only the design's point of origin
moves from LTR to RTL.

Budget: "nothing expensive but good enough." No component library, no build-tool change, no
new runtime dependency. A token layer and a small set of primitive component styles, in the
same plain-CSS-with-logical-properties idiom `styles.css` already uses.

**Reference:** extract usable design characteristics — color, type, spacing, shape, tone — from
`https://zohal.io/`, an existing site the product owner pointed at as the quality bar. Not a
clone: extract the *characteristics* (palette logic, type scale, corner radii, density, how it
handles emphasis and hierarchy) and adapt them to this app's own content (forms, tables,
three-valued pass/fail/indeterminate pills, a report view) — none of which zohal.io has an
equivalent of, so this is translation, not copying.

## Scope

**Research first, in the task's own evidence, before writing CSS:**

- Fetch and examine `https://zohal.io/`. Record concretely: the color palette and how it's used
  (not just hex values — what's background vs. accent vs. text, how much contrast, how
  saturated), the type scale (how many sizes, what weights, what the hierarchy looks like), the
  spacing rhythm (tight or airy, what unit it seems built on), corner radii and border treatment,
  and anything distinctive about tone (is it dense and technical, or generous and calm). If the
  site cannot be reached or scraped meaningfully, say so plainly and name a fallback reference
  rather than inventing characteristics and attributing them to a site you didn't actually see.

**Then, build:**

- A token layer extending `:root` in `services/web/src/styles.css` (or a new file it imports,
  your call) — color, spacing scale, radius, type scale — replacing the current ad hoc values
  (`--radius: 8px` alone, font sizes scattered as magic numbers through the file: `0.85rem`,
  `0.78rem`, `1.7rem`, etc.) with a real scale applied consistently. Keep the existing
  `--pass`/`--fail`/`--indeterminate` semantic slots and the dark-mode block — this is a design
  pass on top of the working three-valued color system, not a replacement of it.
- The RTL-native point of origin means: author spacing, alignment and type primarily for the
  `dir="rtl"` / `fa` reading order, using the logical properties already in place
  (`margin-inline`, `padding-block`, `inset-inline-start`, etc. — don't introduce a physical
  `margin-left`/`right` anywhere, that would be a regression against what's already correct
  here) — and confirm English still renders correctly mirrored, it does not get a second,
  separate set of rules.
- Apply the new token layer and primitives to the existing screens: `SignInPage`,
  `RegisterPage`, `CreateWorkspacePage`, `ReviewsPage`, and the report view. Every one of these
  today uses browser-default `input`/`select`/file-input styling — that's the most visible part
  of "hideous" and has to change, not just the tokens underneath it.
- Vazirmatn is already referenced (`:lang(fa) body`) — confirm it's actually loading (check
  whether it's a system-installed font, a bundled asset, or missing entirely today) and fix
  whichever it turns out to be; a font-family declaration for a font nothing serves is the same
  as not declaring it.

**What explicitly does not change**

- No new npm dependency (no Tailwind, no MUI, no icon library) — "nothing expensive" means the
  existing plain-CSS approach, done properly, not a framework swap.
- No change to English support, the i18n pipeline, or `docs/decisions.md`'s multinational
  stance — confirmed with the product owner, do not re-raise it.
- No new screens, no new user flows — this is a visual pass over what T-0067 and earlier tasks
  already built.
- Component *behavior* (validation, error handling, the T-0068/T-0069 findings already queued)
  is out of scope here — this task is what things look like, not what they do.

## How to prove it ran

`make verify`, then real rendered evidence in both directions: screenshot the sign-in, register,
create-workspace, reviews, and a real report view (reuse the existing e2e fixtures — three
doors, pass/fail/indeterminate) in `fa`/RTL first, since that's now the primary target, and in
`en`/LTR second, showing the mirror is clean and nothing physical leaked through. Before/after
comparison against the current screenshots already in `services/web/e2e/screenshots/` so the
improvement is visible, not asserted. Run the existing e2e suite (`onboarding.spec.ts`,
`report.spec.ts`, `session-isolation.spec.ts`, etc.) unmodified in behavior — a design pass that
breaks an existing passing spec because it removed something the spec was asserting on (a label,
a role, a test id) is a regression, not a redesign, and must be fixed as one.

## Evidence

### Research, before any CSS was written

Fetched `https://zohal.io/` for real (`WebFetch`, then a raw `curl` for its actual HTML/CSS —
`WebFetch`'s markdown-only summary cannot report a hex value, so both were used: `WebFetch` for
tone, the raw response for the concrete design tokens the task asks for). The site loaded and
was meaningfully inspectable — not a partial or blocked fetch — so nothing here is invented.

**It is Farsi-native, not a mirrored LTR site**, which is the whole premise of "extract from an
RTL-Persian reference": `<html lang="fa" dir="rtl" class="mx-auto overflow-x-hidden
font-iranYekan">`. زحل (Zohal) is an identity-verification/banking-API B2B product (Next.js +
Tailwind + Mantine, confirmed from the served `_next/static/css/*.css` bundles), so its content
shape — metrics, verticals, cards — differs from this app's, exactly as the task expected
("translation, not copying").

- **Palette.** Not a flat brand blue. A custom, deep navy-indigo `primary` scale is used for
  both text and large surfaces — `primary-0 #f2f3f8` (near-white, cool-tinted) down to
  `primary-9 #0f1019` (near-black navy) — with the accent/CTA colour living at a *fractional*
  shade, `primary-6.5 #2d3a5d`, bordered one step darker at `primary-7 #2d3252`: the accent and
  its border are two adjacent shades of the same hue, not a separate bright "brand blue" bolted
  on. A warm secondary accent appears sparingly (`secondary-3 #f5b078` peach/orange,
  `secondary-6 #d57630`). Semantic status colours are a *third*, entirely separate scale (toast
  `success #39ac65` green, `warning #eab308` amber, `error #df2040` red, `info #0284c7` blue) —
  confirmation that a serious product keeps brand colour and status colour apart, which this
  app's `--pass`/`--fail`/`--indeterminate` already did; zohal.io is evidence for keeping that
  separation, not a reason to touch it. A `neutral` scale close to stock Tailwind gray runs the
  low-emphasis surfaces and body text, kept apart from the navy brand scale.
- **Type.** A small, real scale actually in use on the page: `text-xs 0.75rem/1rem`,
  `text-sm 0.875rem/1.25rem`, `text-xl 1.25rem/1.75rem` — roughly 1.1–1.15× steps, generous
  line-heights (1.33–1.4× the font size), `font-bold` (700) the only weight seen on the page
  itself (Mantine's own base sheet separately defines a `--mantine-heading-font-weight: 700`).
- **Spacing.** Airy, not tight: `py-10` (2.5rem) section padding, `p-6` (1.5rem) card padding,
  `gap-y-4` (1rem) the single most common stack gap — all on a 4px/0.25rem base unit (Tailwind's
  default rhythm, unmodified).
- **Radius and border.** `rounded-xl` (0.75rem) is the *single most-used* utility class on the
  page (29 occurrences, more than any other) — a generously rounded, soft-cornered look, plus
  `rounded-full` for pills. Borders are thin and low-contrast; a single restrained
  `box-shadow: 0 2px 8px rgba(0,0,0,.18)` is scoped to one utility, literally named
  `shadow-header`, and used sparingly rather than on every surface.
- **Tone.** `WebFetch`'s independent read: "a blend of technical competence with approachable
  professionalism … trustworthy and current rather than playful," generous section spacing,
  repeated structured card modules (metrics, verticals) for scannability — a technical B2B
  register, not a marketing gloss. Consistent with what this product needs: a compliance tool,
  not a landing page.
- **Typeface delivery — the most directly reusable finding.** Zohal self-hosts its own Persian
  typeface, IRANYekanX, weights 300–900, as `woff2`+`ttf` under `/fonts/`, declared via
  `@font-face` in its own bundled CSS — never a bare `font-family` hoping a system has it
  installed. This is the direct precedent for the Vazirmatn fix below: the correct answer to
  "Persian on the web" is a self-hosted webfont, not a system-font gamble.

Translation into this app's tokens (not a copy — no color value below is zohal's own; the
*characteristics* are what moved): a deep navy-indigo accent in place of the old flat
`#2b5ce6`, `rounded-xl`-scale radii in place of the old flat `8px`/`6px`, a 4px-based spacing
scale in place of scattered rems, a small real type scale, and Vazirmatn actually self-hosted
in place of a name with nothing serving it.

### What was built

- **`services/web/src/styles.css`** — token layer added to `:root` (accent scale, an 8-step
  4px-based spacing scale `--space-1`…`--space-10`, a 4-step radius scale
  `--radius-sm/md/lg/pill`, a 7-step type scale `--text-xs`…`--text-2xl`, a weight scale, two
  shadow tokens) and every scattered magic number in the file (`0.85rem`, `0.78rem`, `0.9rem`,
  `0.87rem`, `0.82rem`, `1.7rem`, `font-weight: 620`/`680`, the bare `999px`, the bare `6px`)
  replaced by a token. **Untouched, exactly as instructed:** `--pass`/`--pass-bg`/`--fail`/
  `--fail-bg`/`--indeterminate`/`--indeterminate-bg` and the whole
  `@media (prefers-color-scheme: dark)` block's *existing* lines — `git diff` on those specific
  lines is empty; the dark block only gained new lines for the new tokens (accent, shadows),
  never a change to a line that was already there.
- **Vazirmatn, actually self-hosted.** Confirmed before touching anything: `grep -r vazirmatn`
  across the frontend found only the bare `font-family: Vazirmatn, Tahoma, …` in `:lang(fa)
  body` — no bundled asset, no webfont import, nothing serving it; on any machine without the
  font already installed (i.e. almost everywhere) it silently fell through to Tahoma. Fixed by
  vendoring two real font files, `services/web/src/assets/fonts/vazirmatn-{arabic,latin}.woff2`
  (pulled from Google Fonts' own hosting — Vazirmatn is SIL OFL, freely redistributable — then
  committed into the repo so the glyphs are served from this origin, not a runtime dependency
  on `fonts.googleapis.com`), and two `@font-face` rules in `styles.css` with `font-weight: 400
  700` (a range, not four duplicate blocks: Google served byte-identical files across every
  static weight request, which is how a variable font is served progressively). `vite build`
  resolves the `url()` references, content-hashes the files and copies them into `dist/assets`
  — confirmed in the build output below, and confirmed actually served over HTTP from the
  running container (also below), not just present in the bundle.
- **Primitives.** `input`, `select`, `button`, `input[type="file"]` (via the real, broadly
  supported `::file-selector-button` pseudo-element — no fake JS-driven file button) all
  restyled off the token layer: consistent border/radius/padding, focus-visible rings, hover
  and active states. `.pill` gained a `currentColor` dot (`::before`, generated content — not
  part of `textContent`, so `toHaveText("Fail")` in `report.spec.ts` is unaffected, confirmed by
  the full suite run below). `.card`/`.report` gained a soft shadow and the larger radius;
  `.topbar` gained the "shadow-header"-style restrained shadow zohal.io itself names that way.
  `h1`–`h4` gained real sizes from the type scale (previously unset — raw browser-default
  heading sizes, one of the "hideous" symptoms named in the task).
- **`select` keeps its native `appearance` — a deliberate call, not an oversight.** A custom
  dropdown arrow has to flip sides between `rtl` and `ltr` (it belongs at the inline-end, which
  is a physical position), and the browser already places its own arrow correctly for whichever
  direction the page is in, for free. Restyling only the box (border/radius/padding/background)
  gets `<select>` off "raw browser default" without re-solving a problem the platform already
  solves — the same "inherit before writing" call this codebase makes everywhere else. Recorded
  here, not hidden, since it's a real design decision with a real alternative (a `:dir()`-keyed
  custom chevron) that was considered and rejected.
- **`.field` wrapper** added around each label+input pair in `SignInPage.tsx`, `RegisterPage.tsx`
  and `CreateWorkspacePage.tsx` (three small, mechanical edits — a `<div className="field">`
  around markup that already existed, nothing else changed) so a label sits tight to its own
  input while `.card`'s own gap separates one field from the next — previously every child of
  `.card` (heading, paragraph, label, input, button) shared one flat gap, which is why the forms
  read as an undifferentiated stack. `getByLabel(...)` in every existing spec is unaffected
  (label/input association is via `htmlFor`/`id`, not DOM adjacency) — confirmed by the full
  suite run below.
- **`ReviewsPage.tsx` and `ReportView.tsx` — zero changes.** Both already used the class names
  the new CSS targets (`section.card`, `li.review`, `li.spec`, `section.report`,
  `.count--pass`/`.count--fail`/`.count--indeterminate`, `.pill`, `.notice`, `.entities`, native
  `input`/`select`/`button`), so the whole visual pass on these two screens is the primitives
  layer alone — exactly the "primitives, not per-page CSS" architecture the file already
  implied. No test-relevant tag, class, `data-testid`, role or accessible name was touched
  anywhere (checked against every `getBy*`/`.locator(...)`/`data-testid` in all five existing
  specs before editing, listed below under Wiring).

### `make verify`

```
$ make verify
uv run ruff check .              -> All checks passed!
uv run ruff format --check .     -> 172 files already formatted
uv run mypy packages/engine/src services/api/cadgpt -> Success: no issues found in 156 source files
uv run lint-imports --no-cache   -> Contracts: 5 kept, 0 broken.
uv run pytest                    -> 235 passed, 32 warnings in 4.76s
cd services/web && pnpm install --frozen-lockfile && pnpm run verify
  eslint .          -> clean
  tsc -b --noEmit   -> clean
  tsc -b && vite build:
    dist/index.html                                0.40 kB
    dist/assets/vazirmatn-latin-BFexNX-K.woff2    34.52 kB
    dist/assets/vazirmatn-arabic-Cafbb7Zc.woff2   46.31 kB
    dist/assets/index-DL1GmoTm.css                 8.73 kB │ gzip:  2.44 kB
    dist/assets/index-C4z0KdOQ.js                315.54 kB │ gzip: 97.74 kB
    ✓ built in 2.10s
$ echo $?
0
```

No Python file changed in this task (pure frontend CSS/asset/three-small-TSX-edit pass), so
`ruff`/`mypy`/`contracts`/`pytest` are the pre-existing baseline re-run clean; `web-verify` is
the gate this task could plausibly break, and it is green, including the two font files
actually appearing as separate, content-hashed build outputs — proof `vite`'s asset pipeline
picked up the `url()` references in `styles.css` rather than them being dead code.

### Real path

`docker compose -f deploy/compose.yaml up --build -d web` against the running `make up` stack
(`api` also recreated as a dependency, same pattern every prior task in this history shows).

**The font fix actually loads, confirmed over HTTP against the running container, not just
present in the build:**

```
$ curl -s http://localhost:8080/ | grep -oE 'assets/index-[^"]*\.css'
assets/index-DL1GmoTm.css
$ curl -s http://localhost:8080/assets/index-DL1GmoTm.css | grep -oE 'assets/vazirmatn-arabic-[^)]*\.woff2'
assets/vazirmatn-arabic-Cafbb7Zc.woff2
$ curl -s -o /dev/null -w "%{http_code} %{content_type} %{size_download}\n" \
    http://localhost:8080/assets/vazirmatn-arabic-Cafbb7Zc.woff2
200 font/woff2 46308
```

**A real browser walkthrough**, driven with Playwright against `http://localhost:8080` (same
target `playwright.config.ts` points every spec at), registering a brand-new account with no
seeded state (same pattern as `onboarding.spec.ts`), creating a first workspace, uploading the
real `door_width.ids` rule set and the real `three_doors.ifc` fixture (the same fixtures
`report.spec.ts` uses), running a check, and opening the report — once with
`localStorage.language = "fa"` (primary target, RTL), once with `"en"` (LTR mirror). Full
sequence: sign-in → register → create-workspace → reviews (rule-set upload + review creation,
including the file picker mid-selection) → report, both languages, twelve screenshots total,
committed at `services/web/e2e/screenshots/t0070/{fa,en}-{1-signin,2-register,
3-create-workspace,4-reviews,4b-file-picker,5-report}.png`. Real counts on the report screen in
both languages: **1 pass / 1 fail / 1 indeterminate** — the same three-doors fixture shape
`report.spec.ts` established, reached here from a cold start in each language.

Confirmed concretely from the captured screenshots, not asserted: `dir="rtl"` renders the fa
run with the whole layout mirrored (topbar order, card alignment, table columns, filter
checkboxes, the disclosure's inline-start border) and Persian text shaped correctly by the
now-actually-loading Vazirmatn; the en run is a clean mirror back to LTR with no physically
stuck-over element (no ltr-only fragment survives on the wrong side, no filter/table column
misaligned) — before/after both directions is the twelve screenshots above set against the
task's own baseline images already committed at `services/web/e2e/screenshots/{onboarding-*,
report,isolation-*}.png`, e.g. `onboarding-3-reviews-shell.png` before vs.
`t0070/en-4-reviews.png` after: flat `8px` cards/`#2b5ce6` buttons vs. the new
`rounded-xl`-scale cards, soft shadows and deep-navy accent, same screen, same data shape.
(Running the existing suite below, unmodified, also regenerated its own committed screenshots
at their original paths — `onboarding-*.png`, `isolation-*.png`, `report.png` — since those
specs always write to fixed paths every run; those now show the new design directly, which is
additional, not substitute, evidence.)

A dark-mode sanity screenshot (`prefers-color-scheme: dark`, throwaway — not committed) was
also driven, to check the new dark-mode token additions (accent, shadows) — light-indigo
accent button with dark text reads cleanly against the dark card, the radial-gradient backdrop
on `.centered` is a barely-visible dark vignette rather than a stray glow. No existing
`--pass`/`--fail`/`--indeterminate` dark value was touched, confirmed by `git diff` showing
those lines absent from the diff.

**One genuine finding surfaced and fixed during this walkthrough, unrelated to the CSS itself:
a screenshot-timing bug in the throwaway driver script, not a product bug.** The first capture
of the register screen showed the "back to sign in" link with a solid navy fill behind it,
looking like a stray focus/selection artifact. Diagnosed live with `getComputedStyle` /
`:matches()` checks against the running page rather than guessed at: it was a real `:hover`
state — Playwright's simulated mouse cursor stays parked at the coordinates of the last click,
and the "back to sign in" link renders in roughly the same screen position as the "create
account" link that had just been clicked to reach that screen, so the *next* frame legitimately
was hovering it. `getComputedStyle` also showed the colour was still mid-transition
(`background 0.15s ease`) a mouse-move later, because the screenshot fired before the CSS
transition had settled. Fixed in the driver only (`page.mouse.move(0,0)` + a 250ms settle before
every shot) — nothing in `styles.css` changed for this, since there was nothing wrong with it.

**The existing suite, unmodified in behavior, re-run against the freshly rebuilt container:**

```
$ npx playwright test --project=chromium --reporter=list
Running 6 tests using 4 workers
  ✓  session-isolation.spec.ts:36   signing out clears the previous user's cached tenant and
     rule-set data before the next person signs in on the same tab (12.8s)
  ✓  onboarding.spec.ts:24          a brand-new person registers, creates a workspace and
     starts a review, entirely in the browser (13.3s)
  ✓  report-recovery.spec.ts:47     the recovery button's own POST is what moves a pending
     report to failed (17.0s)
  ✓  upload-limit.spec.ts:13        the model size ceiling is stated at upload time, in
     English and Persian (5.4s)
  ✓  session-isolation.spec.ts:118  the workspace dropdown never renders with zero options
     while the tenant list is still loading (5.9s)
  ✓  report.spec.ts:40              a real check run reproduces 1 pass / 1 fail / 1
     indeterminate in the browser (20.6s)
  6 passed (22.3s)
```

Zero specs edited to make this pass — `git diff --stat` on `services/web/e2e/*.spec.ts` is
empty. The one spec that asserts on a class this task touched heavily,
`report.spec.ts:238`'s `expect(wallCountRequiredSpec.locator(".pill--fail")).toHaveText("Fail")`,
passing confirms the `::before` dot added to `.pill` does not leak into `textContent`.

### Wiring

- **The font actually being served, not just declared** —
  `services/web/src/styles.css`: `src: url("./assets/fonts/vazirmatn-arabic.woff2")
  format("woff2");` inside an `@font-face` block, resolved by Vite's asset pipeline (registered
  build-wide, no per-file config needed — `services/web/vite.config.ts`'s default
  `@vitejs/plugin-react` + Rollup CSS handling already processes `url()` in any CSS reached from
  `main.tsx`'s `import "@/styles.css"`), confirmed present as
  `dist/assets/vazirmatn-arabic-Cafbb7Zc.woff2` in the build output above and confirmed served
  with `200 font/woff2` from the running container above — three independent confirmations
  (source, build output, live HTTP), not just one.
- **The token layer reaching real screens** — every one of `SignInPage.tsx`, `RegisterPage.tsx`,
  `CreateWorkspacePage.tsx` imports nothing new for styling (no new class framework, no new
  component library, per scope); they render `<div className="field">` wrapping existing
  `<label>`/`<input>` pairs, and `main.tsx`'s existing `import "@/styles.css";` is the only
  registration point CSS in this app ever needed — unchanged, still the same line, still the
  first and only global stylesheet import.
- **No new npm dependency** — confirmed: `git diff services/web/package.json` is empty, and
  `pnpm install --frozen-lockfile` inside `make verify` above passed, which fails outright if
  the lockfile and `package.json` disagree.
- **Existing screens' class names, unedited, still carrying the new styling** —
  `services/web/src/features/review/ReviewsPage.tsx` and
  `services/web/src/components/ReportView.tsx`: `git diff` on both files is empty; the visual
  change on both screens is entirely `styles.css` primitives reaching classnames
  (`section.card`, `li.review`, `section.report`, `.count--*`, `.pill`, `.spec`) that were
  already there before this task and are still exactly there now — confirmed by every
  `page.locator("section.card", ...)` / `li.review` / `li.spec` / `section.report` /
  `.count--pass .count__value` selector across all five existing specs resolving correctly in
  the full suite run above.

### NOT DONE

Everything in scope was built. Two deliberate, recorded non-changes, not gaps:

1. **`<select>`'s dropdown arrow is the browser's native one, not a custom RTL-aware chevron.**
   Explained above under "What was built" — the platform already gets this right for free in
   both directions, and building a `:dir()`-keyed custom arrow would be re-solving a solved
   problem for a purely cosmetic gain. If the product owner wants a fully custom `<select>` look
   later, that is a new, larger task (a listbox replacement, since native `<select>` styling has
   a hard ceiling), not a follow-up to this one.
2. **`input[type="file"]`'s native "Choose File" button text stays in the browser's own UI
   language** (English, in this Chromium build) even on the `fa`/RTL screens — visible in
   `t0070/fa-4-reviews.png` and `t0070/fa-4b-file-picker.png`. This is not a regression: it was
   true before this task too (nothing here could have changed it either way) and it is a
   platform limitation, not a CSS one — the file-picker *button's label string* is chrome the
   page cannot address at all, only its *appearance* (`::file-selector-button`, restyled here).
   Fixing it would mean replacing the native file input with a JS-driven fake one, which is a
   behavior change explicitly out of scope for this visual-only pass ("Component behavior … is
   out of scope here — this task is what things look like, not what they do").

Nothing was narrowed or skipped from the task's own scope list (token layer, RTL-native origin,
Vazirmatn fix, all five named screens, no new dependency, no i18n regression) — all five are
built and evidenced above.

## Review
