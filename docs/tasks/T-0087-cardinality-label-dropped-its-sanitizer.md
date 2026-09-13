# T-0087 — `cardinality_label`'s output reaches the report unsanitized

**Phase:** 3   **Status:** open
**Touches invariants:** none directly — not exploitable via any reachable input today, but
the report-generation module's existing sanitization discipline was silently narrowed.

## Why

Found by T-0055's review. Before T-0055, the "N elements matched · &lt;cardinality&gt;" line in
`services/api/cadgpt/apps/review/services/report_markdown.py` passed `spec["cardinality"]`
through `_sanitize_text()` before interpolating it into the Markdown body. T-0055 replaced that
call with `cardinality_label(spec["cardinality"])`
(`services/api/cadgpt/apps/review/requirements.py`), whose unrecognised-token branch returns
the input **raw** — `cardinality_label("x\n## Forged heading")` reproduces the string verbatim,
which would open a new Markdown block mid-document, exactly the injection class
`_sanitize_text` and its three existing tests exist to prevent.

Not reachable today: `spec["cardinality"]` is sourced from `ifctester`'s `ids.py:329-336`
`get_usage()`, derived from `minOccurs`/`maxOccurs` — a closed vocabulary of three values, all
of which now match a known token and return through the translated branch, not the raw
fallback. (The unvalidated `setattr` the reviewer found in `facet.py:105` feeds
*requirement*-level cardinality, a different field this file does not render.) So this is a
real narrowing of a defensive property, not a live vulnerability.

## Scope

- Wrap `cardinality_label(...)`'s call site in `report_markdown.py` with `_sanitize_text(...)`,
  same as every other interpolated field in that module — restoring the sanitization T-0055
  incidentally dropped, without changing `cardinality_label`'s own translation logic.
- A test asserting the sanitizer still runs on this field specifically (a Markdown-control-
  character input to the cardinality line renders sanitized), matching the existing pattern
  for the module's other three `_sanitize_text` tests.

## How to prove it ran

`make verify` with the new test included, and a before/after showing an adversarial
cardinality-shaped string (a known token still translates correctly; an unrecognised one no
longer reaches the document raw).

## Evidence

## Review
