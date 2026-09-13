# T-0089 — the Detail-column caption attributes upstream's wording to the wrong component

**Phase:** 3   **Status:** open
**Touches invariants:** I5 (a resolvable basis, worded honestly) — the caption itself is now
one of the "explains itself" sentences it applies to, and it misidentifies its own subject.

## Why

Found by T-0055's review. T-0055 added a caption above the Specifications section:
`gettext("Where shown, the Detail column is the checking engine's own wording, in English.")`
(`services/api/cadgpt/apps/review/services/report_markdown.py:327-329`). The sentence it
describes — `entity.detail` — is `ifctester` 0.8.5's hardcoded English text (confirmed by
T-0055's own upstream check: no gettext/i18n anywhere in the installed package, every
`Result.to_string()` override a raw English f-string). But the report's own header line reads
`Engine 0.2.0`, naming `cadgpt_engine` — our own package. A reader trying to trace the Detail
sentence to its source is pointed at the wrong component: told it is "the checking engine's"
wording when it is upstream `ifctester`'s.

Minor secondarily: the caption renders unconditionally under `## Specifications` ("Where
shown" hedges it, but it still appears once even for a report with no Detail column content at
all, e.g. a report with only prohibited-cardinality zero-evaluation requirements).

## Scope

- Reword the caption to name `ifctester` (or "the upstream IFC-checking library" if naming a
  third-party package by name is not this module's convention — check how `docs/decisions.md`
  or existing report text refers to `ifctester` elsewhere, if at all) rather than "the checking
  engine", so the attribution is accurate rather than pointing at `cadgpt_engine`.
- Consider gating the caption on whether any requirement in the report actually has non-empty
  `entity.detail` values, so it does not appear in a report where it describes nothing. Only in
  scope if it is a small conditional near the existing render loop — not worth restructuring
  the renderer over.

## How to prove it ran

`make verify`, then a real generated file (either language) showing the corrected caption
text, and — if the conditional is added — one file where the caption appears (a report with
failed/indeterminate detail text) and one where it does not (a report with no Detail content),
both pasted.

## Evidence

## Review
