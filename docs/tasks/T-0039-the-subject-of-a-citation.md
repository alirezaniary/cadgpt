# T-0039 — The subject of a citation: structured in the engine, worded in the service

**Phase:** 3 — What the first real user needs   **Status:** open
**Touches invariants:** I5, and `CLAUDE.md`'s gettext rule. **Reviewer-gated.**

## Why

Two findings from the T-0027 review, and they are the same defect wearing two hats: T-0027
made the *predicate* of a citation structured and localizable and left the *subject* as English
prose written into the stored document by the engine.

**The attribute name can itself be a restriction, and then the dict repr comes back.**
`_facet_subject_name` in `packages/engine/src/cadgpt_engine/check.py` accepts `name`/`baseName`
only when `isinstance(..., str)`. But `Facet.parse` (`ifctester/facet.py:104-113`) is generic:
**any** parameter becomes a `Restriction` when the IDS writes `<xs:restriction>` under it,
including `name`. Reproduced on the real path:

```
SPEC: Restricted attribute name
    stored basis:     {"facet_type":"attribute","name":null,"cardinality":"required","comparisons":[]}
    requirement_text: "The {'enumeration': ['OverallWidth', 'OverallHeight']} shall be provided"
```

`basis.name` is `null`, the sentence falls back to `description`, and the reader gets the Python
dict repr T-0027 exists to eliminate — as the primary, untranslatable line. The `isinstance`
guard is the right *defensive* shape, since it degrades rather than raising; what is wrong is
that it drops the data instead of carrying it.

**And the applicability line is untranslated English in the stored document.**
`_specification` builds `" and ".join(f.to_string("applicability") for f in spec.applicability)`
and `ReportView.tsx:175-179` renders it straight to the DOM. That is verbatim the defect
T-0027's own "Why" section opens with, reintroduced on a new field. The joiner `" and "` is
separately hardcoded English *inside the engine*, so a two-facet applicability reads
English-joined even in Persian. T-0027's builder disclosed this and justified it by that task's
no-renderer-registry ban, which was a defensible scope call — this is the task that closes it.

## Scope

The shape is the one `reason_code`/`reason_label` and now `basis`/`requirement_text` already
established. Do not invent a third mechanism.

**Changes**

- `packages/engine/src/cadgpt_engine/report.py`, `check.py` — carry the attribute name's own
  restriction rather than dropping it to `None` (a `name_comparisons`, or whatever fits the
  existing `Comparison` shape), and give `SpecificationOutcome` a **structured** applicability
  beside or in place of `applicability_description`. Wire-format change: bump
  `REPORT_SCHEMA_VERSION`, and keep the existing string field as the fallback for documents
  already stored at the current version.
- `services/api/cadgpt/apps/review/` — the wording, through `gettext`, beside the existing
  requirement wording. **Start with `Entity`**, the only applicability facet the shipped
  fixtures exercise; every other facet type falls back to the string the engine already
  produces. Do not build a registry for facet types no fixture exercises.
- `services/web/` — render the localized subject, falling back as today.
- Both i18n catalogues, and `services/api/cadgpt/locale/fa/LC_MESSAGES/django.po`.

**Does not change:** the predicate rendering T-0027 built, the fallback contract, any status or
count. Do not implement margin.

## How to prove it ran

A committed fixture whose IDS puts an `<xs:restriction>` under the attribute *name*, and one
with a two-facet applicability. Then, as T-0027 proved its own claim: **the same stored document
rendered in both languages**, pasted from the API response — one document, two renderings, for
the subject line as well as the predicate. A single-language paste does not prove this task.

`make verify`; `make up` with the containers rebuilt; `make e2e` asserting the localized subject
from the browser; a screenshot you have opened; and a mutation proof per new assertion.

## Evidence

<!-- the builder writes this -->

## Review
