# T-0090 — the file's date format is a real, undocumented divergence from the screen's

**Phase:** 3   **Status:** open
**Touches invariants:** none — a decision-logging gap, not a code defect.

## Why

Found by T-0055's review. T-0055 renders the report file's identifying line
(`Run &lt;uuid&gt; · Checked &lt;date&gt;`) as Gregorian, ASCII digits, fixed UTC, reasoned about
in `report_markdown.py`'s module docstring — a deliberate and defensible choice for a document
that must read as one unambiguous instant regardless of the reader's timezone or calendar. The
on-screen date formatting (`services/web/src/lib/dates.ts`) instead uses
`Intl.DateTimeFormat(i18n.language)`, i.e. the Persian calendar, in the browser's local
timezone.

This is a real, settled divergence between the two renderers of the same run's timestamp, and
CLAUDE.md's rule is that "when a decision is settled, append a paragraph to
`docs/decisions.md` so it survives context loss." The reasoning currently lives only in a
Python module's docstring, which the frontend engineer touching `dates.ts` next has no reason
to ever read.

## Scope

- A short paragraph in `docs/decisions.md` recording: the file states time as Gregorian/UTC and
  the screen as local-calendar/local-timezone, and why (an archived document needs one
  unambiguous instant readable regardless of where and when it is opened; the screen is read in
  the moment, in the reader's own context). No code change — this task is purely closing the
  decision-log gap CLAUDE.md requires.

## How to prove it ran

The paragraph exists in `docs/decisions.md`, dated, and quotes or paraphrases the same
reasoning currently only in `report_markdown.py`'s docstring.

## Evidence

## Review
