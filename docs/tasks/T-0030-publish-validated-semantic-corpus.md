# T-0030 - Publish the validated semantic corpus and deferred-review ledger

**Phase:** Regulation corpus 7   **Status:** open
**Touches invariants:** I1, import contracts

## Why

Validated source evidence and semantic candidates are not useful to downstream tools until they
are released through one deterministic, versioned contract. Publish a machine-consumable corpus
that preserves Persian source semantics, English glosses, formulas, tables, document relationships,
and exact provenance while structurally excluding every unresolved or contradicted assertion. The
same release must state what is missing so partial coverage can never be mistaken for complete legal
compliance knowledge.

## Scope

- Add `publish-corpus` and `corpus-check`. They consume re-attested T-0029 validation, T-0028
  extraction, T-0027 structure, T-0026 transcription, T-0025 acquisition, and catalog receipts.
  Mixed cohort/configuration identities, missing upstream records, or tampering fail closed.
- Define strict versioned JSON Schemas and emit a release directory containing at minimum:
  `manifest.json`, `documents.json`, `structure.jsonl`, `semantics.jsonl`, `formulas.jsonl`,
  `tables.jsonl`, `relations.jsonl`, `coverage.json`, and `deferred-review.jsonl`. Partitioned
  per-document files may supplement these canonical indexes but may not replace complete corpus
  accounting.
- Preserve catalog order, Persian and English titles, editions, legal/document kinds, amendment,
  appendix, explanatory, supersession, and edition relationships. Web contradictions and newly
  discovered official publications remain versioned findings; the release identifies the exact
  43-document cohort and never calls it the current complete INBR corpus.
- Publish only semantic records whose source anchors, structure, quantities, references, units,
  tables, formulas, blind-pass reconciliation, independent validation, and applicable official-web
  checks have terminal accepted results. Any blocking unknown, contradiction, unsupported field,
  OCR ambiguity, formula mismatch, or legal-relationship uncertainty excludes the affected record.
- Keep source Persian derived from spans, not copied from model responses. Store English semantic
  glosses separately with model/pass/validator provenance and explicit translation status. A
  translation conflict cannot change or hide the Persian record.
- Publish formula records with anchored source/crop references, raw and Unicode display forms,
  LaTeX, Presentation MathML, verified Content MathML where available, scoped variables/constants,
  printed units, and unambiguous UCUM mappings. A formula lacking verified semantic form may remain
  as source evidence but cannot back a machine-evaluable formula rule.
- Represent semantic relations explicitly: subject, predicate/property, modality, comparison,
  value/range/set, unit, applicability conditions, exceptions, dependencies, internal/external
  references, table/formula links, and source hierarchy. Preserve `unknown` rather than omitting a
  required field in a way that looks known.
- Emit stable release-local IDs and complete backreferences to source document/page/span/region
  identities. The release must support resolving any published field to primary PDF evidence and
  every model/validator/web decision that affected it without shipping the PDF itself.
- Produce a coverage manifest by document, page, structural node, semantic kind, and validation
  outcome. Distinguish `published`, `source_only`, `needs_review`, `rejected`, `failed`, and
  `not_machine_actionable`; totals reconcile exactly with upstream records. Coverage statements
  must not convert absence of a published rule into an assertion that no rule exists.
- Produce an append-only deferred-review ledger containing every blocked item, severity/reason code,
  affected IDs, evidence links, alternative candidates, deterministic failures, web conflicts, and
  the minimum human decision needed later. Publication runs without human input and does not drop
  or collapse repeated flags.
- Canonicalize JSON/JSONL ordering and bytes, hash every file, build a Merkle-style release manifest
  over file hashes, and retain content-addressed immutable release history plus a no-clobber index.
  Two runs from the same inputs are byte-identical and reuse all files without changing mtimes.
- Store release data outside Git under a private caller-owned root. Never add PDFs, renders, OCR,
  crops, model responses, snapshots, generated corpora, or review ledgers to the repository.
- Keep this release semantic and jurisdictional data beside, not inside, `cadgpt_engine`. Do not
  compile IDS or claim a building/model complies. A later compiler may consume this contract after
  separate applicability and ratification work.

## Tests

- Schema fixtures cover all document relationships, structural/semantic kinds, quantities, units,
  tables, formulas, translations, evidence backreferences, coverage states, and review reasons.
- Publication rejects any record with unresolved blocking validation, missing or invalid anchors,
  model-authored verbatim evidence, unverified Content MathML, ambiguous unit mapping, mixed cohort
  identity, unaccounted upstream record, duplicate ID, unknown field, or inconsistent count.
- Referential-integrity tests resolve every published relation, source anchor, formula/table link,
  variable definition, provenance record, file hash, and deferred-review target.
- Coverage tests prove all 43 documents and 5,892 pages reconcile across source-only, published,
  review, rejected, failed, and not-machine-actionable states without overstating completeness.
- Corpus-check inventories the entire release root and rejects extra, missing, tampered, symlinked,
  reordered, partially written, or history/index-conflicting artifacts.
- Two clean publication runs produce byte-identical files and release root hash; the second run
  reuses every artifact without changing mtimes. Interrupted publication resumes safely.
- Import contracts prove no corpus data, jurisdiction logic, OCR/model/network dependency, or
  publication code enters `cadgpt_engine`.

## How to prove it ran

```sh
make verify

publication_root=$(mktemp -d /tmp/cadgpt-inbr-publication.XXXXXX)

uv run cadgpt-regulations publish-corpus \
  --validation /tmp/cadgpt-inbr-validation.FINAL/semantic/validation.json \
  --validation-root /tmp/cadgpt-inbr-validation.FINAL/semantic \
  --output-root "$publication_root"

uv run cadgpt-regulations corpus-check \
  "$publication_root/manifest.json" \
  --root "$publication_root"
```

The evidence must show:

- the release identifies and accounts for exactly the requested 43 PDFs and all 5,892 pages while
  explicitly reporting that newer/unmapped official documents prevent a current-complete claim;
- every published semantic/formula/table/relation field resolves through validation and model/web
  provenance to exact source spans or regions, with no model-authored verbatim text;
- every blocking uncertainty is absent from `semantics.jsonl` and present in
  `deferred-review.jsonl`; no failure or review item disappears from coverage totals;
- formulas use the layered raw/Unicode/LaTeX/Presentation MathML/verified Content MathML contract,
  with unresolved glyphs, symbols, operators, or units excluded from evaluable rules;
- document order, editions, appendices, amendments, explanatory relationships, and official-web
  drift survive in the published graph;
- canonical hashes, counts, referential integrity, full root inventory, and upstream receipt
  identities pass `corpus-check`;
- a second full publication run is byte-identical and rewrites nothing.

## Evidence

Not run yet.

## Review

Required because this task is the final publication boundary and milestone end of the regulation
corpus workstream.
