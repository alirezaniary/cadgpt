# T-0110 — A citation that quotes the sentence, not the whole page

**Phase:** Regulation corpus 8 — source-cited rule codification   **Status:** open
**Touches invariants:** never assert compliance we did not establish

## Why

The compiled `.ids` produced from real corpus data on 2026-09-19 carries this in its
`instructions` attribute, which is the field a designer reads to see *why* a rule applies:

```
متن دقیق فارسی: «مبحث پازدهم
جدول ب لست الات تع سی ا سمان موش بن
الت نی ا رسان ه کوک بلى - کیر تسارد کاربیره بند مرتبط
...
```

— roughly three thousand characters, the entire transcript section for that page, for a single
rule about a single quantity. It is not false: `provisional_batch.py` builds the transcript
revision from the source record's whole `text_fa` (`provisional_batch.py:93`), and
`make_transcript_citation` re-attests that exact string, so `exact_text_sha256` is honest. But
the rule's own justification is one clause inside it, and the artifact does not say which. A
citation that points at a page and says "somewhere in here" is weaker than the product claims
when it says every rule is traceable to an exact citation.

The same run surfaced a second, smaller overstatement: `citation.citation_description` renders
`صفحه چاپی {pdf_page}` — "printed page N" — by falling back to the PDF page number when
`printed_page_label` is null (`citation.py:35`). The PDF page and the page printed on the paper
are different numbers in a scanned book, and the corpus has 5,892 pages with the label largely
absent. The artifact asserts a printed-page label that was never established.

Neither blocks a release, which is why this sits after T-0109 rather than before it. Both
weaken the one thing the corpus is for.

## Scope

- **Narrow the quoted span to the clause the rule came from.** The candidate already names its
  `source_record_id`; what it lacks is an offset into that record's text. The mechanism should
  be a character span (start, end) into the attested `text_fa`, carried on the candidate and
  re-verified at citation time by re-slicing the pinned transcript and re-hashing — so the
  narrow quote is provably a substring of the wide attested one and nothing is re-authored. The
  full-record text and its hash stay on the citation as the outer evidence; the span is added,
  not substituted.
- **Where a span is unavailable, keep the full record and say so.** A citation with no span
  must be distinguishable in the artifact from one with a span. Do not synthesise a span by
  string-searching the Persian text for a number — the OCR is unreliable enough (`مبحث پازدهم`
  for `مبحث پانزدهم` in the run above) that a fuzzy match would fabricate provenance.
- **Stop asserting a printed page label that does not exist.** `citation.py:35` must render the
  PDF page as the PDF page when `printed_page_label` is null, in wording that does not claim the
  printed page. Every user-facing string here goes through `gettext` per `CLAUDE.md`; the engine
  names the reason, the service supplies the wording.
- Files: `packages/regulations/src/cadgpt_regulations/citation.py`, `transcript_citation.py`,
  `provisional_batch.py`, `schemas/source-citation.schema.json`,
  `schemas/candidate-citation.schema.json`, and the surviving compiler from T-0105.

**Does not change:** the outer attestation. `document_sha256`, `transcript_sha256` and the
full-record `exact_text_sha256` keep their present meaning, because existing release manifests
hash them. Changing what a compiled `rule_id` hashes over invalidates every artifact hash in
the T-0109 release — if that is unavoidable, state it in the evidence and say what has to be
recompiled.

## How to prove it ran

`make verify`, then recompile one rule from the T-0109 release through the changed path and show
both artifacts side by side:

```sh
.venv/bin/python -m cadgpt_regulations.cli compile-native-rule \
  --rule <the same rule IR, now carrying a span> --output-root <root>/compiled
```

The evidence must paste: the `instructions` attribute before (thousands of characters) and after
(the clause), with its character count; the `description` attribute showing the PDF page no
longer described as a printed page; proof that the narrowed quote is a verbatim substring of the
attested full record and that its hash re-verifies; one rule for which **no** span was available
showing it kept the full record and is marked as such; and an `ifctester.ids.open()` parse of
both outputs.

## Evidence

<!-- the builder writes this -->

## Review
