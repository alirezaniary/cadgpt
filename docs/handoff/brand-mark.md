# Handoff: the brand mark's ground

Story: `docs/product/user-stories/brand-mark.md`
Flow: `docs/ux/flows/brand-mark-surfaces.md`
Preview: `design-previews/brand-mark/index.html` (+ `topbar-balance.html`)
Design tokens: `docs/design/DESIGN.md`

## The decision, in one line

The mark keeps its own two colors and gets a **near-white plaque** to sit on — the light ground
it was drawn for — plus a **trimmed viewBox**, because 59% of the shipped asset's box is empty.

## Component inventory

| Component | Class | States | Notes |
|---|---|---|---|
| Brand mark | `.brand-mark` | none | The `<img>` itself. Sizes are set by the plaque, not here. |
| Brand plaque | `.brand-plaque` | none | The tile. `background: var(--brand-plaque)`, `border-radius: 28%`, grid-centred. **New.** |
| Brand lockup | `.brand-lockup` | none | `display: flex`, `align-items: center`, `gap: var(--space-2)`. Binds mark to wordmark so they are one object, not two flex children at the bar's generic gap. **New.** |
| — topbar size | `.brand-plaque` default | — | `2.25rem` tile, mark at 78% |
| — auth size | `.brand-lockup--lg .brand-plaque` | — | `2.5rem` tile, mark at 78% |
| Account avatar | `.avatar` | unchanged | Deliberately left alone — see "Rejected alternatives". |

## Token additions

One new token, added to `:root` in `services/web/src/styles.css` and to `docs/design/DESIGN.md`:

| Token | Value | Role |
|---|---|---|
| `--brand-plaque` | `#f2f5ff` | The light ground the two-tone mark sits on. Same value as `--accent-fg`, deliberately named separately — one is "text on an accent fill", the other is "the brand's ground", and they are free to diverge. |

No other token changes. `--accent` is **not** touched (see "Surfaced, not fixed").

## Assets

| Path | What it is | How it is produced |
|---|---|---|
| `cadgpt-logo.svg` (repo root) | Master. Untouched, C2PA manifest intact. | supplied |
| `services/web/public/cadgpt-mark.svg` | **New.** The six paths byte-identical, `viewBox="148 148 728 728"`. | derived from the master; the box is **square around the crosshair intersection**, sized to the longest arm — *not* the bbox, see below |
| `services/web/public/favicon.png` | 64×64, plaque baked in (the browser's tab strip is a ground CSS cannot reach). Mark at 80% — larger than in-product, because at 16px there are no pixels to give away. | `scripts/build_brand_assets.py` |
| `services/web/public/cadgpt-logo.png` | **Deleted.** Nothing references it once the three components use the SVG. | — |

## Markup changes

**`app/ProtectedShell.tsx`** — the mark and the wordmark become one lockup:

```
<span class="brand-lockup">
  <span class="brand-plaque"><img src="/cadgpt-mark.svg" alt="" class="brand-mark"></span>
  <strong>CADgpt</strong>
</span>
```

**`features/auth/SignInPage.tsx`, `RegisterPage.tsx`** — the same lockup, larger, **as the `h1`**,
replacing the stacked mark-then-heading pair. One brand statement, one lockup shape everywhere:

```
<h1 class="brand-lockup brand-lockup--lg">
  <span class="brand-plaque"><img src="/cadgpt-mark.svg" alt="" class="brand-mark"></span>
  CADgpt
</h1>
```

`alt=""` stays on both: the wordmark beside the mark is already the accessible name, and a
second one would make every screen reader say it twice.

`.brand-mark-lg` is deleted — nothing uses it once the auth cards use the lockup.

## Acceptance criteria (from the story)

- [ ] Sign-in shows a complete logo, both tones, as the card's focal point.
- [ ] The topbar mark reads at small size and sits with the wordmark as one lockup.
- [ ] The favicon is identifiable in a light **and** a dark tab strip.
- [ ] Every surface uses the master SVG's own colors — verified by sampling, not by assertion.
- [ ] The change reads as a composition decision applied consistently.

## Rejected alternatives, with the reason

- **Recolor the mark for dark grounds** (the 2026-09-11 pass, and its better-executed cousin, a
  true reversed colorway with the brackets knocked out). Rejected: it is the move already
  rejected once; it costs a second in-product colorway; and the reversed favicon *dies on a
  light tab strip*, so it does not even solve every surface. Preview §2 and the favicon tuning
  strip are the evidence.
- **Accent-filled plaque.** Inverts the defect — the blue crosshair vanishes into a blue ground.
- **Lifting the account avatar to balance the bar** (`topbar-balance.html`). Moot, and instructive:
  the preview stylesheet had `.avatar` as `--accent-soft`, but the shipped rule is a solid
  `--accent` fill. The real container showed the bar already balanced. No change needed; the
  preview has been corrected.
- **Squaring the trim on the artwork's bounding box.** Shipped first, rejected on sight: the mark's
  arms are unequal (299 left / 349 right, 363 up / 295 down from the crosshair), so a bbox-centred
  tile pushes the intersection 12px right and 17px high at 512px and the mark reads as sliding out
  of its tile. Both strokes run at exactly x=512/y=512 — the master was already optically centred.
  Centre on the crosshair; size to the longest arm.
- **Baking the plaque into the SVG.** The mark must stay plaque-free for the exported/printed
  report, where a white tile on white paper is meaningless. The plaque is a wrapper, on purpose.

## Surfaced, not fixed — needs a product decision

`--accent` (`#3165ea`) against `--card` is **2.48:1**. `docs/design/DESIGN.md` records 3.84:1,
which was the *orange* accent, never updated when the accent was swapped to the logo's blue. The
swap was made so the mark would not read as a mismatched import — a reason this work removes,
since the mark now has its own ground. Affected: the "ساخت حساب کاربری" link, `.table a:hover`,
and the active workspace row in the account menu. Same hue and saturation reaches 3:1 at
`#4776EC` and 4.5:1 at `#7699F1`. **Not changed here** — recolouring the app's CTA is a product
decision, not a side effect of a logo task.
