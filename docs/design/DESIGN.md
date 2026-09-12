# Design tokens

Reconstructed from `services/web/src/styles.css` on 2026-09-06, after the fact — T-0070/T-0071
established this visual language and no token file was written at the time. Every value below
is read out of that stylesheet, not proposed here. `styles.css` remains the implementation;
this file is the index a new screen checks itself against before inventing a value.

**One theme, no light variant.** The identity is RTL-Persian-first dark navy, measured from
zohal.io's own computed styles (T-0071). There is no `prefers-color-scheme` branch and no
toggle: the semantic tints below are the ones already tuned for a dark surface.

## Color

| Token | Value | Role |
|---|---|---|
| `--bg` | `#26293f` | Page field |
| `--card` | `#2d3250` | Raised layer — `.card`, `.topbar`, `.report`, menu panel |
| `--fg` | `#e7e9f2` | Body text |
| `--muted` | `#9aa1ba` | Secondary text, labels, table headers |
| `--line` | `#3c4160` | Borders and separators |
| `--accent` | `#3165ea` | Primary CTA fill, links |
| `--accent-strong` | `#2450c4` | CTA hover |
| `--accent-soft` | `rgba(49,101,234,0.18)` | Focus ring, row hover, menu-item hover |
| `--accent-fg` | `#f2f5ff` | Text on an accent fill |
| `--brand-plaque` | `#f2f5ff` | The light ground the brand mark sits on — `.brand-plaque` |
| `--pass` / `--pass-bg` | `#4fd396` / `#113023` | PASS |
| `--fail` / `--fail-bg` | `#ef6a72` / `#3a1618` | FAIL |
| `--indeterminate` / `--indeterminate-bg` | `#e0b451` / `#382a10` | INDETERMINATE |

The three status colors are equal citizens. INDETERMINATE is rendered at the same weight as
the other two everywhere it appears — `.counts` is three columns and never two — because the
product's whole value-add over raw `ifctester` is that the third value cannot be read past.

### Measured contrast

Computed from the hex values above (WCAG 2.1 relative luminance), 2026-09-06:

| Pair | Ratio | AA body text (4.5:1) |
|---|---|---|
| `--fg` on `--bg` | 11.78:1 | pass |
| `--fg` on `--card` | 10.30:1 | pass |
| `--muted` on `--bg` | 5.56:1 | pass |
| `--muted` on `--card` | 4.86:1 | pass |
| `--accent-fg` on `--accent` (button label) | 4.61:1 | pass |
| `--pass` on `--pass-bg` | 7.54:1 | pass |
| `--indeterminate` on `--indeterminate-bg` | 7.18:1 | pass |
| `--fail` on `--fail-bg` | 5.33:1 | pass |
| `--fg` on a hovered table row | 7.10:1 | pass |
| **`--accent` on `--card`** | **2.48:1** | **fails** |
| **`--fail` on `--card`** | **4.14:1** | **fails** |

**Recomputed 2026-09-12.** The accent rows above had never been updated after the accent was
swapped from the old orange to the logo's blue on 2026-09-11 — they recorded the orange's
numbers. The real figures are worse: `--accent` on `--card` is **2.48:1**, which fails the 3:1
non-text floor and not merely AA for text. It is `.link-button` (the "Create account" link inside
the sign-in card), `.table a:hover`, and `.user-menu-panel button.active`. `--fail` on `--card` is
`.error`, which is how every form failure in the app is worded, and is the one a person reads
while something has already gone wrong. Neither is fixed here — recording the measurement is what
this file is for, and the fix is a task of its own. For whoever takes it: at the same hue and
saturation, `#4776EC` reaches 3:1 and `#7699F1` reaches 4.5:1. See `docs/decisions.md`,
2026-09-12.

The brand mark's own two tones are the reason `--brand-plaque` exists: navy `#1B1456` is 1.15:1
on `--bg` and 1.31:1 on `--card`, and the blue `#3165EB` is 2.85:1 and 2.49:1 — **both** under
3:1. On `--brand-plaque` they are 15.05:1 and 4.60:1, and the plaque itself is 13.10:1 / 11.45:1
against the two surfaces it sits on, so the tile has a defined edge without a border.

`--line` on `--card` is 1.26:1, which is correct: a separator is not text and 3:1 does not
apply to a decorative rule.

## Type

Family: `system-ui` stack, with **Vazirmatn** (self-hosted, two subsets, variable 400–700)
taking over under `:lang(fa)`. Identifiers — email, IFC class, GlobalId — carry `.ltr` and read
left-to-right inside the right-to-left page.

| Token | Value | Used by |
|---|---|---|
| `--text-xs` | 0.75rem | Pill, table header, count label, menu label |
| `--text-sm` | 0.8125rem | `h4`, labels, breadcrumbs, entity table, `.error` |
| `--text-base` | 0.9375rem | Body, inputs, buttons, tables |
| `--text-md` | 1rem | `.spec__head strong` |
| `--text-lg` | 1.125rem | `h3`, topbar wordmark |
| `--text-xl` | 1.375rem | `h2` |
| `--text-2xl` | 1.75rem | `h1`, `.count__value` |

Weights: `--weight-regular` 400, `--weight-medium` 500, `--weight-semibold` 600,
`--weight-bold` 700. Body line-height 1.55; `--leading-tight` 1.3.

## Spacing

A 4px base. `--space-1` 0.25rem, `-2` 0.5, `-3` 0.75, `-4` 1, `-5` 1.25, `-6` 1.5, `-8` 2,
`-10` 2.5rem. Page gutter and card padding are both `--space-6`; a card's internal rhythm is
`--space-5`; a field's label-to-control gap is `--space-1`.

## Radius and depth

`--radius-sm` 0.5rem (inputs, buttons), `--radius-md` 0.75rem (menu panel, `.spec`),
`--radius-lg` 1rem (`.card`, `.report`, `.count`), `--radius-pill` 999px (`.pill`, avatar).
`--shadow-card` and `--shadow-header` carry real spread and opacity — soft light-mode shadows
are invisible against this background.

## Layout

`.page` is a `72rem` max-inline-size grid, `--space-6` gutter, centred with `margin-inline`.
`.breadcrumbs` repeats that width and gutter so the trail lines up with the card beneath it.
`.centered` is the full-height single-card frame the auth and first-workspace screens use, over
a radial `--accent-soft` wash.

**Written in logical properties throughout.** `inline-start`, `margin-inline`, `padding-block`
— never `left`/`right` — so the interface mirrors when `dir` flips and no component knows which
way the page runs. The one deliberate exception is `select`'s chevron: CSS never gave
`background-position` logical keywords, so it is drawn physically and flipped under an explicit
`[dir="rtl"]` rule.

## Components already established

Reuse these before writing a new one.

| Component | Class / file | States |
|---|---|---|
| Status pill | `StatusPill.tsx`, `.pill--{pass,fail,indeterminate}` | the three values; label always shown, never colour alone |
| Card | `.card` | the single container for every form and panel |
| Page head | `.page__head` | heading + one primary action, wraps on narrow |
| Primary button | `button` | default, `:hover`, `:active`, `:focus-visible`, `:disabled` |
| Navigation styled as a button | `.button-link` | for a `<Link>` that reads as the primary action |
| Text button | `.link-button` | inline actions inside prose |
| Changelist table | `.table` | header, hover row, `.active` row; whole row is clickable |
| Field | `.field` + `label` + `input`/`select` | real `<label htmlFor>`, never placeholder-only |
| File field | `input[type=file]::file-selector-button` | styled natively, no fake JS button |
| Breadcrumbs | `Breadcrumbs.tsx`, `.breadcrumbs` | hidden on `/projects`; trailing crumb is `aria-current="page"` |
| Brand lockup | `.brand-lockup`, `.brand-plaque`, `.brand-mark` | one shape, two sizes — topbar (2.25rem tile) and auth `h1` (`--lg`, 2.5rem). Mark at 78% of its tile, `border-radius: 28%` so both sizes are the same shape. Never `--radius-pill`: the avatar is the pill. |
| Account menu | `.user-menu*` | closed, open; outside-click and Escape close it |
| Count tile | `.count--*` | three, always three |
| Report block | `ReportView.tsx`, `.report`, `.disclosure`, `.coverage`, `.specs`, `.entities` | see `docs/ux/flows/review-and-report.md` |
| Notice / error | `.notice`, `.error` | `.notice` is amber and informational; `.error` is a failure |

## Responsive

There is not one `@media` query in `styles.css`. What holds up under narrowing does so
intrinsically: `.page` and `.report` are `max-inline-size` with `margin-inline: auto`,
`.page__head` and `.row` are `flex-wrap: wrap`, `.card` is `min-inline-size: min(24rem, 100%)`,
and `.counts` is a three-column grid of `minmax(0, 1fr)`.

Two known weak points, both untested below 768px at the time of writing: `.counts` never
collapses to fewer than three columns, and `.entities` sets fixed per-column widths summing to
roughly 37.5rem plus an auto column, inside a `table-layout: fixed`. Neither has been checked
on a phone. That is a statement of what is unverified, not a claim that it breaks.
