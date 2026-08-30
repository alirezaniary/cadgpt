# DEC-0008 — ThatOpen Engine (web-ifc) for the web overlay

**Status:** DECIDED
**Date:** 2026-08-30
**Decided by:** Lead
**Affects:** `web/`, `presentation`

## Problem
`prd.md` §5.8 leaves the viewer open: *"ThatOpen Engine (web-ifc) or xeokit-bim-viewer — both
open source, both load and save BCF viewpoints, both support 2D-in-3D markers and 2D plan
generation."* Leaving it open forks the presentation contract.

## Constraints
- The overlay is the primary output form in v0 — *"the overlay is the product"*. A findings list
  is a document an architect skims; errors shown on the thing they just finished is something
  they act on.
- It must reach anyone with no install.
- BCF viewpoint round-trip is required: BCF is the interchange format behind the report, the
  overlay and the in-model markers alike.
- I6: no vendor account, no hosted service in the path.

## Options
1. **ThatOpen Engine (web-ifc).** TypeScript-native, actively developed, loads IFC directly with
   no server-side conversion, BCF round-trip, component-based so we take only what we need.
2. **xeokit-bim-viewer.** Mature, strong large-model performance, and typically wants a
   conversion step into its own format — an extra pipeline stage and an extra artefact to keep
   in sync with the checked model.
3. Defer. Forks the presentation contract and costs a rewrite later.

## Decision
ThatOpen Engine. Decisive factor: **it loads the same IFC the engine checked**, with no
conversion step. The overlay showing a different artefact from the one that was checked is a
class of bug we simply do not want to own, in a product whose entire claim is traceability.

## Expected result
A finding's marker is placed by the IFC GUID the engine reported, with no identifier
translation anywhere in the path.

## Reopens if
Real-model performance in the browser is unacceptable on the model sizes Gate 3 reveals.
xeokit's conversion step buys performance, and that trade becomes worth making — with a
measurement, not an impression.

## Consequences accepted
Large models may load more slowly than a preconverted format. Measured on Gate 3's five real
models before any optimization work.
