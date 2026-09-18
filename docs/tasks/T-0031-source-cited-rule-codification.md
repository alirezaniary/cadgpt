# T-0031 - Source-cited rule codification

**Phase:** Regulation corpus 8  **Status:** open

## Purpose

Translate the completed Persian Luna transcript into deterministic IDS rules while
retaining a direct PDF/page/transcript citation. The existing workflow is:

```text
PDF -> 10-page slices -> PaddleOCR draft -> Luna transcript JSON
    -> page projection -> rule candidates -> IDS validation/compilation
```

No second OCR pass, source-graph re-anchoring, or manual review queue is required for the
current transcript checkpoint.

## Citation contract

Every candidate and compiled artifact carries:

```json
{
  "document_key": "volume-10-edition-1401",
  "document_sha256": "<sha256>",
  "pdf_page": 586,
  "page_id": "<page-key>",
  "exact_text_fa": "<exact Persian transcript text>",
  "exact_text_sha256": "<sha256>",
  "transcript_sha256": "<sha256>",
  "source_node_ids": [],
  "source_span_ids": []
}
```

Structural node/span arrays are optional. The PDF name, English machine `document_key`,
numeric page, transcript record/source text, and hashes are sufficient evidence. A
cross-page sentence stores every page key in `source_page_ids` on its candidate.

## Two-part flow

### Part 1 - Page and transcript preparation

Create one `pdf_document` row per PDF and one `pdf_page` row per physical page. Each page
stores native extraction, Paddle text/result, and the page-specific Luna transcript JSON.
The complete ten-page Luna response is kept once in immutable file/object storage; its URI
and hash are recorded on every related page row. Previous responses and incoming runs stay
in files and are not inserted as run/job history.

### Part 2 - Candidate to rule

Read the page transcripts in order, carrying a sentence across adjacent pages when needed.
Create one `rule_candidate` row only for an actionable requirement. Informational records,
headings, definitions, references, and unresolved statements do not become candidates.

Validate the candidate's IDS-shaped JSON using the standard facets:
`entity`, `partOf`, `classification`, `attribute`, `property`, and `material` under
applicability and requirements. Record the implementation type (`native_ids`,
`derived_ids`, `decision_table`, `formula_evaluator`, or `unsupported`) and validation
result on the candidate row. Compile valid native candidates deterministically to IDS and
store artifact URIs/hashes on that same row.

## Database contract

The PostgreSQL projection intentionally has only three tables:

1. `pdf_document`: PDF name/path/hash, English/numeric edition identifiers, page count,
   and display metadata.
2. `pdf_page`: one row per physical page; native/Paddle extraction fields, page-specific
   Luna JSON, and the complete ten-page response URI/hash.
3. `rule_candidate`: actionable extraction result linked to its document and primary page,
   with cross-page source keys, exact quote/hash, IDS JSON, validation state, and compiled
   artifact hashes.

The projection uses natural `document_key`/`page_key` foreign keys, so these rows are
directly insertable; generated database IDs are not part of the file-to-database contract.

There are no database tables for candidate evidence, source spans, legal assertions,
manual review, transcript revisions, runs/jobs, or release membership. Raw PDFs, Paddle
payloads, Luna responses, extraction responses, and compiled release files remain in
content-addressed storage. The database can be rebuilt from those files and the current
page/candidate projection.

## Completion checks

- Every physical page has a `pdf_page` row, including pages with no rule.
- Every candidate source page key exists in `pdf_page` for the same document.
- Exact source text and transcript hashes verify before compilation.
- Only supported IDS facets and IFC versions reach native IDS compilation.
- Derived, table, formula, and unsupported candidates remain explicitly classified.
- A second compile from identical candidate input is byte-identical.
- Compiled IDS and sidecar files retain the source citation.

## Implementation map

| Concern | Implementation |
| --- | --- |
| Page/document projection | `rule_projection.py`, `sql/rule_projection.sql` |
| Page/transcript contracts | `transcription.py`, `luna_transcript.py` |
| Candidate extraction | `provisional_batch.py`, `provisional_rule.py` |
| IDS-shaped rule IR | `rule_ir.py`, `rule_normalization.py` |
| IDS compilation | `rule_compiler.py`, `ids_compiler.py` |
| Optional source-graph audit | `source_reanchor.py` |

## Review

This task establishes the boundary where Persian transcript evidence becomes a deterministic
rule candidate and then a compiled IDS artifact. The three-table page-first projection is
deliberately small; more tables require a new concrete query or retention requirement.
