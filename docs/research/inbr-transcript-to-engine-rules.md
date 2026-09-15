# INBR transcript to executable rules

## Current workflow

The completed Persian Luna transcript JSON is the source checkpoint. It already carries
the PDF identity, PDF page number, page-specific text, and transcript hashes produced by
the existing 10-page-slice -> PaddleOCR -> Luna process. Rule work does not run another
OCR pass or require structural span re-anchoring.

The workflow has two parts:

```text
Part 1: source preparation
PDF -> one pdf_page row per physical page
    -> native PDF text and/or Paddle text
    -> page-specific Luna transcript JSON
    -> complete ten-page Luna responses kept as immutable files

Part 2: rule production
page transcript records -> actionable rule candidates
                     -> IDS facet validation and deterministic compilation
```

Not every transcript record is a candidate. Headings, definitions, references,
informational text, and records that cannot be expressed safely remain source data and do
not become rules. Candidate extraction and rule compilation are separate steps: the first
preserves the source statement, and the second validates its IDS mapping.

## Source citation

Every candidate or compiled rule keeps the document key, PDF page, page key, transcript
hash, exact Persian source text, and exact-text hash. `source_node_ids` and `source_span_ids`
may be retained as optional audit metadata, but they are not required for transcript-backed
rules. A sentence that crosses a page boundary stores all source page keys in the candidate
row.

Machine identifiers use English and ASCII numbers, for example
`volume-10-edition-1401`, `volume_number=10`, and `edition_year=1401`. Persian titles and
edition labels are display metadata only.

## IDS candidate shape

`rule_candidate.ids_specification` stores an IDS-shaped JSON object. The supported IDS
facet names are:

- applicability: `entity`, `partOf`, `classification`, `attribute`, `property`, `material`;
- requirements: `entity`, `partOf`, `classification`, `attribute`, `property`, `material`.

The candidate also records `implementation_type`: `native_ids`, `derived_ids`,
`decision_table`, `formula_evaluator`, or `unsupported`. A candidate is never silently
turned into an invented IDS rule. Unsupported or incomplete mappings remain in the same
row with a reason and validation payload.

## Three-table database projection

The database is a small queryable projection. It is not the history store and it is not a
manual review workflow. The only tables are:

### `pdf_document`

One row per PDF with `document_key`, `pdf_name`, `file_path`, `source_sha256`,
`volume_number`, `edition_year`, `edition_code`, page count, and display metadata.

### `pdf_page`

Exactly one row per physical PDF page. It contains the page number and key, native text and
layout JSON when available, Paddle text and result JSON when available, page-specific Luna
transcript JSON/text and hash, and the URI/hash of the complete ten-page Luna response.
The page row is present even when the page produces no rule candidate.

### `rule_candidate`

One row per actionable extraction result. It points to the document and primary page,
stores source page keys for cross-page text, source quote and hashes, extraction JSON/file
hash, IDS-shaped JSON, implementation type, validation status, and compiled IDS/sidecar
URIs and hashes. A transcript record that is not actionable has no candidate row.

There are intentionally no database tables for runs/jobs, candidate evidence, legal
assertions, source spans, transcript revisions, manual review, or release membership.
Incoming and previous Luna/extraction runs stay as immutable files. The database stores
the current useful page and candidate projection; the files preserve raw history.

## Projection API

`build_page_projection_rows()` imports every physical page from the existing transcription
manifest, including pages with no candidate. `build_projection_rows()` adds document/page
rows from compiled candidates and emits only three output collections:
`pdf_documents`, `pdf_pages`, and `rule_candidates`. When a complete page manifest is
available, pass it as `page_source` so all pages are validated and retained. Cross-page
candidate page keys must already exist in that page source and belong to the same document.
The natural ASCII `document_key` and `page_key` values are the foreign keys emitted by the
projection, so rows can be inserted without resolving generated numeric IDs first.

## Deterministic validation and compilation

The candidate stage preserves exact source text and source page identity. The compiler then
checks the canonical rule JSON, IDS facets, IFC versions, values, cardinality, and supported
implementation type. Valid native candidates produce deterministic `.ids` and sidecar files;
derived, table, formula, and unsupported candidates are marked explicitly. The compiler is
network-free and does not call an LLM.

The engine consumes the immutable compiled artifacts. It does not query candidate rows or
call Luna at evaluation time.

## Standards boundary

buildingSMART IDS supplies the applicability and requirement facet vocabulary. IFC supplies
the entity/property model. IDS does not express arbitrary geometry, formulas, aggregates,
or legal precedence; those candidates remain derived or unsupported until a deterministic
observation/implementation exists. UCUM may be used for verified units and RFC 8785-style
canonical JSON hashing may be used for stable fingerprints.

## Evidence and tests

The source-cited compiler tests use the INBR Volume 10/page 586 fixture. The optional
source-graph re-anchor code remains an audit utility only. The SQL projection contract is
covered by `tests/test_rule_projection_sql.py`; page/candidate projection and cross-page
validation are covered by `tests/test_rule_projection.py`.
