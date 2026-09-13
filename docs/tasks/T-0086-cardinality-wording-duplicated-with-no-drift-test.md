# T-0086 — cardinality wording is duplicated across two files, with nothing to catch drift

**Phase:** 3   **Status:** open
**Touches invariants:** none — a maintainability gap, not a correctness defect today.

## Why

Found by T-0055's review. `cardinality_label()`
(`services/api/cadgpt/apps/review/requirements.py`, added by T-0055) and
`ReportView.tsx`'s existing `report.cardinality.<token>` keys (`services/web/src/i18n/fa.json`,
added by T-0036) carry the same three Persian words — required/optional/prohibited — as two
independent literals. The task file, the `.po` file's own comments, and this observation all
assert the two are "word-for-word identical" today (verified byte-for-byte by the reviewer),
but nothing enforces that going forward: editing one wording without the other drifts the
screen and the downloaded file apart silently, with every test still green.

This codebase already has the pattern for exactly this situation.
`test_report_view_severity_rank_matches_the_engine`
(`services/api/cadgpt/apps/review/tests/test_report_markdown.py:483`, from T-0052) reads the
frontend's own source file and asserts it against the backend's, ten lines above where
T-0055's new tests were added.

## Scope

- A test, backend or frontend (whichever side can more easily read the other's source file,
  following `test_report_view_severity_rank_matches_the_engine`'s own pattern), asserting the
  three cardinality words in `services/api/cadgpt/locale/fa/LC_MESSAGES/django.po`'s
  `msgctxt "specification cardinality"` entries match `services/web/src/i18n/fa.json`'s
  `report.cardinality.*` values, for all three tokens.
- Do not introduce a third source of truth (a shared JSON file, a generated constant) unless
  reading one side's file from the other's test suite turns out to be impractical — check
  T-0052's precedent first.

## How to prove it ran

`make verify` with the new test included, plus a mutation check: change one wording on one
side only, show the new test fail, restore it, show it pass. Paste both.

## Evidence

## Review
