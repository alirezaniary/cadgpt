# T-0107 — The missing link: a candidate becomes a compiled IDS file

**Phase:** Regulation corpus 8 — source-cited rule codification   **Status:** open
**Touches invariants:** I1, three-valued, never assert compliance we did not establish

## Why

Every stage of T-0031's spine exists and runs. It was executed end to end against real corpus
data on 2026-09-19 — chunk 313, `volume-11-edition-1400`, PDF page 118:

```
provisional-batch                     -> 5 candidates, 10 transcript revisions on disk
make_transcript_citation              -> 10/10 revisions promoted to citation_status "verified"
compile-native-rule                   -> rules/<rule_id>/rule.ids + rule.json
rule-release                          -> releases/<release_id>/rules/<rule_id>.ids
ifctester.ids.open(<that .ids>)       -> parsed, 1 specification
```

But the stages are not joined. Two concrete breaks:

1. **`provisional_batch` stamps `citation_status` as `candidate` or `needs_review`**
   (`provisional_batch.py:131`), and `CANDIDATE_CITATION_STATES` in `provisional_rule.py:25`
   does not even contain `verified`. Meanwhile `rule-ir.schema.json` requires
   `citation_status: {"const": "verified"}` and `citation.validate_source_citation` rejects
   anything else. The function that bridges this — `transcript_citation.make_transcript_citation`,
   which rebuilds the citation from the pinned transcript revision and returns it `verified`
   after re-checking document identity, source hash, exact text and page — **is reachable only
   from `tests/`. No CLI command calls it.**
2. **The candidate carries no IFC target.** Of 5,378 candidate records across all drafts,
   **zero** have `entity` / `attribute` / `comparator` / `value`. They carry Persian prose:
   `rule_key`, `title_fa`, `statement_fa`, `implementation_type`, `classification`.

So the only thing standing between the corpus and real compiled rule files is a command that
joins a candidate to its verified citation and to an IFC mapping. This task builds that command
and proves it on one real document. T-0108 then authors the mapping at volume.

## Scope

- **A new CLI subcommand, `candidate-to-rule-ir`**, in
  `packages/regulations/src/cadgpt_regulations/cli.py`, plus its module. Inputs: a provisional
  batch directory (as written by `provisional-batch`), the mapping file described below, and an
  output root. For each candidate it: looks up the candidate's transcript revision, calls
  `make_transcript_citation` to obtain the `verified` citation, applies the mapping entry for
  that candidate's `rule_key` if one exists, and writes a `rule-ir-1.0.0` document ready for
  `compile-native-rule`.
- **The mapping file format** — this is the durable contract T-0108 will fill, so design it
  here and keep it small. Keyed by candidate identity (`rule_key` plus `document_key`, so two
  documents can use the same slug), each entry gives the IFC target the surviving compiler from
  T-0105 can express: entity, requirement kind, name, property set where applicable, comparator
  or bounds, value, unit, and `ifc_versions`. Ship it as a JSON schema alongside the others in
  `packages/regulations/src/cadgpt_regulations/schemas/`.
- **A candidate with no mapping entry is not an error and is never guessed at.** It is emitted
  as an unmapped record with a reason code, counted, and excluded from compilation. This is the
  three-valued discipline at the corpus boundary: a requirement we could not express is
  reported as not expressed, never quietly dropped and never approximated into something that
  will evaluate. The compiler must never see a rule whose IFC target was inferred.
- **I1 holds by construction:** the mapping is committed data authored ahead of time, read
  deterministically at compile time. No model is called from this command, and the import
  contract "Regulation corpus core has no service or framework dependencies" already forbids
  the frameworks; do not add an inference dependency to `cadgpt_regulations`.
- Tests under `packages/regulations/tests/` covering: a mapped candidate producing a valid rule
  IR; an unmapped candidate producing an unmapped record rather than an exception; a candidate
  whose transcript revision fails re-attestation being rejected outright.

**Does not change:** `provisional_batch.py`'s output shape, the citation contract, or
`rule_release.py`. This task adds the join; it does not alter either side of it.

## How to prove it ran

`make verify`, then the whole spine over **one real document from the authoritative index**
(T-0106) — every chunk belonging to that document, not one chunk, and with a hand-authored
mapping covering **at least one candidate of each `implementation_type` the surviving compiler
can express**, so the branch for each is exercised:

```sh
# for each chunk of the chosen document, per the T-0106 index
.venv/bin/python -m cadgpt_regulations.cli provisional-batch \
  --transcript <structured_transcript_path> --extraction <chosen draft> \
  --output-root <root>/batch --revision <rev> --edition <edition>

.venv/bin/python -m cadgpt_regulations.cli candidate-to-rule-ir \
  --batch-root <root>/batch --mapping <root>/mapping.json --output-root <root>/ir

.venv/bin/python -m cadgpt_regulations.cli compile-native-rule \
  --rule <root>/ir/rules/<one>.json --output-root <root>/compiled   # for each mapped rule

.venv/bin/python -m cadgpt_regulations.cli rule-release \
  --rules-root <root>/compiled --output-root <root>/release
```

The evidence must paste: the `candidate-to-rule-ir` summary line showing mapped versus unmapped
counts; the `rule-release` line showing the rule count; `find <root>/release -name '*.ids'`
listing real files; the full XML of one compiled `.ids` showing its Persian citation in the
`description` and `instructions`; and an `ifctester.ids.open()` parse of it. It must also show
one unmapped candidate and the reason code it carried — proof that the honest path is taken and
not an exception swallowed.

## Evidence

<!-- the builder writes this -->

## Review
