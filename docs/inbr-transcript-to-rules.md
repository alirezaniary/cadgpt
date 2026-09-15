# INBR Transcript to Rules

The completed Persian Luna transcript JSON is the downstream source checkpoint. It already
contains PDF identity, page number, exact Persian text, and transcript hashes from the
existing workflow:

```text
PDF -> 10-page slices -> PaddleOCR draft -> Luna transcript JSON
    -> page projection -> rule candidates -> IDS validation/compilation
```

No second OCR pass, source-graph re-anchoring, or manual review queue is required.

## Two parts

### 1. Page and transcript preparation

Create one `pdf_document` row per PDF and one `pdf_page` row per physical page. A page row
stores native PDF extraction/layout when available, Paddle text/result when used, and the
page-specific Luna transcript JSON/text/hash. The complete ten-page Luna response is kept
once as an immutable file; its URI/hash is recorded on the related page rows. Incoming and
previous runs remain files, not database job history.

Pages exist even when they produce no rule.

### 2. Candidate to standard rule

Read page transcripts in order, carrying sentences across adjacent pages when required.
Create one `rule_candidate` row only for an actionable requirement. Headings, definitions,
references, informational text, and unresolved statements do not become candidates.

Each candidate stores its document/page citation, exact Persian source text/hash, source page
keys, transcript hash, extraction payload/hash, and IDS-shaped JSON. Validate the candidate
against the IDS facet vocabulary under applicability and requirements:
`entity`, `partOf`, `classification`, `attribute`, `property`, and `material`.

Then compile valid native candidates deterministically to IDS and store IDS/sidecar URIs and
hashes on the same candidate row. Mark derived, table, formula, and unsupported cases
explicitly instead of inventing an IDS mapping.

## Three-table projection

The PostgreSQL projection contains only:

- `pdf_document`: PDF name/path/hash, English/numeric `document_key`, `volume_number`,
  `edition_year`, `edition_code`, page count, and display metadata;
- `pdf_page`: one row per physical page, native/Paddle fields, page-specific Luna JSON,
  and the complete ten-page response URI/hash;
- `rule_candidate`: actionable extraction linked to its document and primary page, with
  cross-page source keys, exact source/hash, IDS JSON, validation status, and compiled
  artifact hashes.

There are no database tables for runs/jobs, candidate evidence, source spans, legal
assertions, transcript revisions, manual review, or release membership. Raw PDFs, OCR,
Luna responses, extraction responses, and compiled files remain in content-addressed
storage. The projection is rebuildable from those files.
The page import consumes the complete transcription/page manifest, not only pages cited by
rules, so every physical page has a `pdf_page` row before candidates are attached.
Projection rows use the natural ASCII `document_key` and `page_key` foreign keys, so the
three output collections can be inserted directly without first resolving generated IDs.

Machine filters use English and ASCII numeric identifiers such as
`volume-10-edition-1401`; Persian titles/edition labels are display metadata only.

## Source citation

The minimum executable citation is document key, document hash, PDF page, page key, exact
Persian text, exact-text hash, and transcript hash. `source_node_ids` and `source_span_ids`
may be retained as optional audit metadata and never block transcript-backed compilation.
A sentence spanning pages keeps every page key in `rule_candidate.source_page_ids`; the
projection validates that every key exists for the same document.

## Code map

- `packages/regulations/sql/rule_projection.sql`: three-table PostgreSQL schema;
- `packages/regulations/src/cadgpt_regulations/rule_projection.py`: page and candidate rows;
- `packages/regulations/src/cadgpt_regulations/rule_compiler.py`: deterministic IDS output;
- `packages/regulations/src/cadgpt_regulations/source_reanchor.py`: optional audit utility.
