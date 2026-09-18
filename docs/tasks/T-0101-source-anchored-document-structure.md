# T-0101 - Reconstruct source-anchored document structure and mathematical evidence

**Phase:** Regulation corpus 4   **Status:** superseded
**Touches invariants:** I1, import contracts

> **Superseded 2026-09-19 by `docs/tasks/T-0031-source-cited-rule-codification.md`.** That
> design's citation contract makes structural node and span arrays optional: the document
> identity, PDF page, transcript record, and hashes are sufficient evidence. Demonstrated on
> 2026-09-19 — a `citation_status: "verified"` citation was produced from a real chunk-313
> transcript revision with `source_node_ids: []` and `source_span_ids: []`, compiled to a real
> `.ids`, and parsed by `ifctester`. `source_reanchor.py` remains available as an optional
> audit. See `docs/decisions.md`, 2026-09-19.

## Why

T-0100 makes every source page addressable as immutable text, pixels, and OCR evidence, but later
semantic workers cannot safely reason over a flat page stream. Build the deterministic structural
layer that preserves reading order, hierarchy, printed clause identifiers, definitions, tables,
figures, formulas, page labels, and cross-page continuations without allowing a heuristic or model
to invent verbatim evidence. This is the source graph that ten-page Luna bundles and all later
assertions must reference.

## Scope

- Add `cadgpt-regulations structure` and `structure-check`. They consume only a successfully
  re-attested T-0100 transcription receipt and its artifact root, continue through individual
  document/page failures, and account for every selected document and page in a terminal state.
- Define strict JSON Schemas for the corpus structure manifest, per-document source graph, tables,
  figures, formula evidence, symbols, units, page-label maps, and continuation edges. Reject unknown
  fields recursively and bind every record to the catalog key, source SHA-256, PDF page, T-0100
  configuration identity, and exact source span or pixel-region anchors.
- Generate stable IDs from attested source identity, structural kind, source order, and anchors.
  Heading text, translated text, OCR text, or model output must never determine identity. Repeated
  captions and repeated clause labels remain distinct by source position.
- Reconstruct one ordered tree using explicit node kinds: `part`, `chapter`, `section`, `clause`,
  `subclause`, `paragraph`, `list_item`, `definition`, `note`, `exception`, `example`, `table`,
  `figure`, `equation`, and `annex`. Preserve unclassified blocks rather than forcing a type.
  Record parent, ordered children, exact label spans, body spans, page extent, and continuation
  edges. Detect impossible cycles, duplicate ownership, gaps, and overlapping non-shared anchors.
- Preserve both PDF page numbers and observed printed labels. Front matter, Roman or Persian
  numerals, repeated labels, missing labels, and page-number offsets must be explicit mappings with
  confidence/reason codes; they must not be guessed into a monotonic sequence.
- Detect clause and heading candidates from positioned evidence, typography, whitespace, known
  Persian/Latin numbering patterns, and the document's table of contents. Deterministic evidence
  may confirm a structure; ambiguous candidates remain `needs_review`. Do not use inference or the
  network in this task.
- Reconstruct table candidates as ordered rows/cells with row/column spans, raw cell text, source
  regions, and continuation links across pages. Preserve a table as a region plus unclassified
  blocks if grid recovery is uncertain; never flatten it into prose and claim success.
- Preserve figures, captions, legends, callouts, and referenced labels as anchored regions. Do not
  interpret diagrams or convert their contents into rules here.
- Represent each formula candidate with exact span/region anchors, immutable crop hash, raw
  transcription, Unicode display text, LaTeX, Presentation MathML, and optional Content MathML.
  Content MathML is publishable only after parser round-trip and token reconciliation against the
  source. Record parse diagnostics and unresolved glyphs rather than repairing them. `LRFD`, `ASD`,
  units, isolated numbers, and prose references are not formulas.
- Store variables, named constants, and units separately with definition spans. Retain printed unit
  spelling and add a UCUM code only for unambiguous mappings. A symbol reused with different scope
  receives separate scoped records.
- Emit deterministic ten-page structural bundles for the next task. Bundles contain only stable
  IDs, source-derived text views, page/render references, structure candidates, and byte accounting;
  they do not contain semantic rules or translations. They preserve T-0100 fallback boundaries and
  never exceed its configured transport ceiling.
- Store all generated graphs, crops, tables, formula files, bundles, receipts, and diagnostics
  outside Git beneath a caller-created private output root. Apply no-symlink, no-clobber,
  content-addressed history, re-attestation, interruption recovery, and same-owner rules inherited
  from T-0099/T-0100.
- Keep inference, crawling, legal interpretation, English translation, IDS generation, and
  jurisdiction-specific checking out of `cadgpt_engine`. This task creates source structure only;
  model extraction and official-web corroboration remain later tasks.

## Tests

- Fixtures cover RTL hierarchy, Persian and Latin clause labels, repeated labels, front matter,
  printed/PDF page offsets, cross-page paragraphs, nested lists, notes/exceptions, definitions,
  tables with merged and continued cells, figures/captions, watermarks, and rotated content.
- Formula fixtures cover fractions, roots, matrices, inequalities, subscripts, superscripts,
  Persian/Latin digits, decimal separators, negative signs, multiplication signs, units, and
  visually ambiguous glyphs. Exact source anchors and crops survive; valid Content MathML
  round-trips; ambiguous expressions quarantine instead of being normalized into a guess.
- Structure validation rejects missing/duplicate/out-of-order pages, orphan or cyclic nodes,
  duplicate anchors, out-of-bounds regions, source/configuration drift, invalid page-label maps,
  broken continuation edges, unknown fields, and unaccounted files.
- Two clean runs over the same evidence produce byte-identical manifests, graphs, crops, formula
  records, and bundles. The second run reuses all matching artifacts without changing mtimes.
- Tool crashes, corrupt page artifacts, formula-parser failures, and one-document failures become
  terminal records while processing continues. `structure-check` preserves the complete report and
  fails closed on any unaccounted, tampered, nonterminal, or publishability-blocking record.
- Import contracts prove regulations remain beside the engine and no OCR, parser, inference, or
  network dependency enters `cadgpt_engine`.

## How to prove it ran

```sh
make verify
make inbr-workspace

# Follow the durable structure sequence in docs/inbr-operations.md. It uses the explicit,
# content-addressed receipts under `.cadgpt/inbr/`, never /tmp.
```

The evidence must show:

- 43/43 documents and 5,892/5,892 pages are represented exactly once in terminal records;
- every structural node, table cell, figure, formula, symbol, unit, and page label resolves to valid
  T-0100 source spans or pixel regions, with no model-authored verbatim evidence;
- Volume 1 pages 11-20 preserve all 30 observed printed heading IDs in source order and connect
  cross-page continuations without inventing missing labels;
- the photographed clarification retains all three pages, including the routing-only second page,
  and quarantines uncertain small identifiers rather than guessing them;
- at least one continued table, watermarked page, mixed-content page, and formula-bearing page has
  its graph, render/crop references, and exact anchors demonstrated;
- every semantic formula has validated Content MathML, all formula displays reconcile with source
  tokens, and every unresolved formula or unit mapping appears in deferred review;
- ordered bundles cover the full corpus in ranges of at most ten pages, obey the byte ceiling, and
  are directly consumable by the next Luna extraction task;
- a second full run produces identical canonical outputs and reuses every matching artifact without
  rewriting it.

Failed or review records do not stop the unattended run, but they remain ineligible for semantic
publication. Full-corpus accounting and fail-closed validation are required before this task is
done.

## Evidence

Not run yet.

### Durable-workspace audit, 2026-09-18

An audit of `.cadgpt/inbr/` and of the external backup
`/media/alireza/09210865357/cadgpt-nonrepo-material-2026-09-16.zip` (44.9 GB, 134,773 entries,
read-only) established that no qualifying structure run exists and that none can currently be
produced, because T-0101's only input — a re-attesting full-corpus T-0100 transcription — does not
exist anywhere.

What is in the durable workspace today:

```sh
$ uv run cadgpt-regulations acquisition-check \
    .cadgpt/inbr/acquisition/revision-2026-09-07/acquisition.json \
    --root .cadgpt/inbr/acquisition/revision-2026-09-07 \
    --catalog packages/regulations/src/cadgpt_regulations/data/inbr_catalog.json
valid acquisition: 10/10 metadata, 43/43 PDFs, 5892 pages, 470674872 bytes
```

The T-0099 cohort is intact and valid. `.cadgpt/inbr/transcription/revision-2026-09-07` is not a
corpus run: its two transcription manifests summarise `documents_expected: 1` with 40 and 41 pages
respectively, and `.cadgpt/inbr/structure/structure.json` and `structure2/structure.json` are the
structure outputs of those one-document smoke runs (3.1 KB each). `.cadgpt/inbr/extraction`,
`extraction2`, `validation` and `publication` are empty directories.

The backup holds three transcription revisions and three structure revisions. Only
`transcription/revision-2026-09-09-paddle` has a transcription manifest at all
(`manifests/transcription/eefa9043….json`, `bundles: 668`, `documents_processed: 43`,
`pages_expected: 5892`, `pages_failed: 0`, `pages_needs_review: 4674`, `pages_ready: 1218`).
`transcription/revision-2026-09-06` (21.9 GB, 60,691 files) contains only `manifests/page-probe`
entries — `transcribe` never produced a manifest there, so it is an unfinished render stage, not a
transcription. `transcription/revision-2026-09-08-f6` and `f6-smoke-2026-09-08` are smoke runs.

The paddle revision was extracted in full (14.5 GB) alongside the acquisition receipt it binds to
(`revision-2026-09-06`, canonical SHA-256 `bd6be8d2546580bac2c059a2a5fd93a376f237b64f20c2af5c5e6ab67f158535`,
matching the manifest's `acquisition.receipt_sha256`) and checked with mainline code:

```sh
$ uv run cadgpt-regulations transcription-check \
    .../transcription/revision-2026-09-09-paddle/manifests/transcription/eefa90439f34920f139f6a1cedb6f96de49613549a9f4937857b948fccd680dc.json \
    --root .../transcription/revision-2026-09-09-paddle \
    --acquisition-root .../acquisition/revision-2026-09-06 \
    --catalog packages/regulations/src/cadgpt_regulations/data/inbr_catalog.json
- acquisition: ACQUISITION_INVALID: cannot inspect acquisition quarantine directory .../quarantine
- page-probe: PAGE_PROBE_INVALID: page probe schema error at configuration:
  Additional properties are not allowed ('paddle_device' was unexpected)
- transcription: TRANSCRIPTION_INVALID: transcription schema error at configuration:
  Additional properties are not allowed ('ocr_engine', 'paddle_det_model', 'paddle_device',
  'paddle_rec_model', 'paddle_text_det_limit_side_len', 'paddle_text_recognition_batch_size'
  were unexpected)
- output: OUTPUT_INVENTORY_INVALID: generated evidence inventory differs:
  unindexed=['ledger.json', 'ledger.lock', 'ledger/a0e11055….json'],
  missing=['pages/…/000005/render.png', …]
observed 43 documents and 5892 pages; 4 blocker(s)
```

The two schema blockers are structural: that corpus was produced by a PaddleOCR toolchain
(`paddleocr 3.7.0`, `paddlepaddle 3.3.1`, `arabic_PP-OCRv5_mobile_rec`, `paddle_device: gpu:0`)
whose configuration keys mainline's page-probe and transcription schemas reject outright. The
inventory blocker is two separate defects: a `ledger`/`ledger.json`/`ledger.lock` queue was written
into the immutable transcription root, and only 4,958 of 5,892 `render.png` page renders exist
(5,892 `page.json` and 5,892 `native.json` are present), so 934 pages have no immutable full-page
source render. T-0100 requires one per page. The revision is therefore not usable as T-0101 input
without a code change to T-0100's pinned toolchain contract, recovery of the missing renders, and a
reproducibility argument for GPU PaddleOCR that T-0100's "different pinned stack … proved by the
real path" clause would demand.

The backup's structure revisions cannot substitute. `structure/revision-2026-09-14` and
`revision-2026-09-15` are byte-identical to each other — 711 identical paths with identical sizes
and CRC32s, and inner mtimes dated 2026-09-13 — which is exactly the deterministic re-attest-and-
reuse behaviour this task requires and is good evidence the implementation's determinism works.
But neither directory contains a `structure.json` manifest (both hold only `bundles/` and
`graphs/`), so there is nothing for `structure-check`, `extract-jobs` or `semantic-publish` to
consume, and both were built over the rejected paddle transcription.

Conclusion: T-0101 remains `open` and unstarted in evidence terms. It is blocked on a
T-0100 transcription that re-attests under mainline code.

## Review

Required because this task defines the source graph and formula evidence boundary consumed by model
extraction and touches I1/import contracts.
