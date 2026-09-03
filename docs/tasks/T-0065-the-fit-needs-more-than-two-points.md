# T-0065 — The memory model is a two-point line, and the point that could corroborate it disagrees

**Phase:** 3   **Status:** open
**Touches invariants:** the evidence standard itself.

## Why

Found by the T-0033 review. T-0033's ceiling is derived rather than chosen, which was the point, and
the derivation is written down and reproducible. But three of its links are weaker than the finished
number looks, and they are worth strengthening before anyone builds on it:

- **The fit is a two-point line.** Two points always fit a line exactly, so there is no residual and
  no corroboration. The shape of the relationship between model size and peak RSS is assumed, not
  measured.
- **The one point that could corroborate it contradicts it.** Duplex measures 173MB where the fit
  predicts 114MB, and it was excluded by argument rather than by measurement. The reviewer then ran
  the committed script on a **469-byte** model and got 148MB peak RSS against the fit's 87MB
  intercept — so the linear form is known to be wrong at the low end. It is conservative there,
  which is why nothing is unsafe today; but a model known to be wrong where we can check it is a
  weak basis for extrapolating where we cannot.
- **The third point is a self-similar duplicate**, carrying 4x Schependomlaan's evaluated entities
  for 2x its bytes. Its RSS-per-byte is not a real model's, so it is not independent evidence about
  real models.

Two constants are also picked rather than measured: the `~150MB` Celery parent reserve, which the
committed script never measures (it measures a standalone subprocess, not a forked prefork child of
a Django+Celery parent), and the 80% allocator/GC safety factor. **Both err conservative**, so
neither is a live risk — this task is about knowing the number rather than trusting it.

## Scope

**Changes**

- More measured points, spanning real models rather than self-similar inflations of one, so the fit
  has a residual and the relationship's shape is evidence instead of assumption.
- The parent reserve measured in the configuration it actually runs in — a prefork child under the
  Celery parent, not a standalone subprocess.
- The safety factor justified or replaced by something derived.
- Where the relationship is genuinely not linear, say so and use what fits. The conservative
  direction is fine; claiming a linear law that the data contradicts is not.

**What explicitly does not change**

- The measurement script's basic approach, which the reviewer executed and confirmed reproduces its
  pasted output.
- The ceiling, unless the better-supported model moves it — in which case moving it is the point, and
  `docs/decisions.md` records why.

## How to prove it ran

`make verify`, then the new measurements pasted with the fit's residuals, including the low-end point
that currently contradicts it. State plainly which of the previous derivation's links this closes and
which it leaves open.

## Evidence

## Review
