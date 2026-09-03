# T-0027 - Reconstruct source-anchored document structure and mathematical evidence

**Phase:** Regulation corpus 4   **Status:** open
**Touches invariants:** I1, import contracts

## Why

T-0026 makes every source page addressable as immutable text, pixels, and OCR evidence, but later
semantic workers cannot safely reason over a flat page stream. Build the deterministic structural
layer that preserves reading order, hierarchy, printed clause identifiers, definitions, tables,
figures, formulas, page labels, and cross-page continuations without allowing a heuristic or model
to invent verbatim evidence. This is the source graph that ten-page Luna bundles and all later
assertions must reference.

## Scope

- Add `cadgpt-regulations structure` and `structure-check`. They consume only a successfully
  re-attested T-0026 transcription receipt and its artifact root, continue through individual
  document/page failures, and account for every selected document and page in a terminal state.
- Define strict JSON Schemas for the corpus structure manifest, per-document source graph, tables,
  figures, formula evidence, symbols, units, page-label maps, and continuation edges. Reject unknown
  fields recursively and bind every record to the catalog key, source SHA-256, PDF page, T-0026
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
  they do not contain semantic rules or translations. They preserve T-0026 fallback boundaries and
  never exceed its configured transport ceiling.
- Store all generated graphs, crops, tables, formula files, bundles, receipts, and diagnostics
  outside Git beneath a caller-created private output root. Apply no-symlink, no-clobber,
  content-addressed history, re-attestation, interruption recovery, and same-owner rules inherited
  from T-0025/T-0026.
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

structure_root=$(mktemp -d /tmp/cadgpt-inbr-structure.XXXXXX)

uv run cadgpt-regulations structure \
  --transcription /tmp/cadgpt-inbr-transcription.FINAL/transcription.json \
  --root /tmp/cadgpt-inbr-transcription.FINAL \
  --output-root "$structure_root"

uv run cadgpt-regulations structure-check \
  "$structure_root/structure.json" \
  --root "$structure_root" \
  --transcription-root /tmp/cadgpt-inbr-transcription.FINAL
```

The evidence must show:

- 43/43 documents and 5,892/5,892 pages are represented exactly once in terminal records;
- every structural node, table cell, figure, formula, symbol, unit, and page label resolves to valid
  T-0026 source spans or pixel regions, with no model-authored verbatim evidence;
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

## Review

Required because this task defines the source graph and formula evidence boundary consumed by model
extraction and touches I1/import contracts.
