# T-0029 - Cross-validate semantics against source evidence and the official web

**Phase:** Regulation corpus 6   **Status:** open
**Touches invariants:** I1, import contracts

## Why

Blind model agreement is useful evidence, not proof. Before any candidate can be published, every
anchor, reference, table value, unit, comparison, and formula link must be checked deterministically,
and the cohort must be compared with versioned official INBR web metadata. The live site already
shows that all 43 cohort artifacts remain official while the cohort is no longer complete/current.
Build the validation layer that preserves both facts without rewriting primary evidence.

## Scope

- Add `web-evidence`, `validate-semantics`, and `validation-check` commands. They separately acquire
  official corroboration snapshots, validate T-0028 candidates against T-0026/T-0027 evidence, and
  emit a complete terminal validation manifest. Network acquisition stays outside
  `cadgpt_engine`; deterministic validation can rerun offline from pinned snapshots.
- Crawl only bounded official sources reachable from the attested national-regulations page and
  curated official INBR origins. Snapshot raw REST/HTML response bytes, request/final URLs, status,
  media type, ETag/Last-Modified when present, retrieval time, SHA-256, parsed links, and a canonical
  semantic projection in content-addressed history. Search engines and unofficial mirrors may
  locate a source but never count as corroboration.
- Start from WordPress page `5825` and the stable volume/guide landing records discovered in the
  2026-09-03 audit. Follow only same-origin, explicitly bounded post/media links; disable ambient
  proxies, cap redirects/body sizes/deadlines, rate-limit requests, and retain every redirect and
  failure as evidence. Reuse unchanged snapshots without rewriting them.
- Map each of the 43 catalog artifacts to its official landing records and PDF links. Compare title,
  document kind, edition/year, amendment/appendix relationships, URL, media type, byte length, and
  pinned source hash where bytes are acquired. A web page may corroborate or contradict catalog
  metadata but can never silently mutate it.
- Discover official linked publications not present in the cohort and record them as immutable
  `unmapped_official_document` findings. At minimum, preserve evidence that Volume 12 fifth edition
  (1403), post `4101` / `v_3_m3.pdf`, and the two-page masonry-guide correction are outside the
  cohort. The cohort remains 43 documents until explicitly revised.
- Deterministically validate every semantic candidate: all source/qualifier IDs resolve; derived
  Persian quotes byte-match their spans; references resolve or are explicitly external; hierarchy
  scope is coherent; comparisons and numeric ranges agree with source tokens; units reconcile with
  printed forms and UCUM mappings; table-derived values point to the correct cells; formula rules
  point to verified formula/symbol records; and no model-created evidence enters the record.
- Validate Content MathML by schema/parser round-trip, compare its token/operator tree with the
  anchored formula evidence, check symbol scope and dimensional consistency where enough unit data
  exists, and preserve `unknown` when it does not. A syntactically valid formula is not automatically
  a legally or physically valid rule.
- Resolve internal cross-references against the source graph and document relationships. References
  to amendments, appendices, explanatory guides, superseded editions, or external standards retain
  typed edges and their legal-status uncertainty; absence of a target is never repaired by fuzzy
  matching alone.
- Compare both blind Luna candidates and independent validator outcomes. Deterministic agreement
  can pass; a model-only choice, omitted provision, conflicting modality/value/scope, formula
  mismatch, or official-web contradiction remains `needs_review` or `rejected`. Validation does not
  use majority vote or confidence thresholds to publish disputed content.
- Emit append-only findings with stable reason codes, severity, affected candidate/source IDs,
  primary evidence, corroborating/contradicting snapshot IDs, machine checks, validator provenance,
  and deferred-human-review status. Processing never waits for a human, but blocking findings keep
  affected records out of the publishable set.
- Store web snapshots, raw responses, Luna validation responses, reports, and all derived artifacts
  outside Git under private no-symlink, no-clobber, content-addressed roots. Re-attest every upstream
  receipt and fail closed on drift, missing coverage, unknown files, or mixed cohort identities.
- Keep IDS compilation and engine evaluation out of this task. It validates the semantic corpus;
  publication is the following task.

## Tests

- Recorded official fixtures cover WordPress REST/HTML, direct PDFs, redirects, changed titles,
  changed edition order, amendments, appendices, missing metadata, rate limits, timeouts, oversized
  bodies, malformed content, and newly linked unmapped official documents.
- Acquisition tests reject off-origin redirects, ambient proxy use, traversal names, symlinks,
  duplicate/conflicting snapshots, content drift under reused validators, partial writes, and
  unaccounted files. A second unchanged run reuses all evidence without changing mtimes.
- Semantic fixtures cover valid and invalid anchors, quotes, cross-references, modalities,
  comparisons, ranges, units, tables, equations, symbol scopes, dimensional checks, external
  references, amendment precedence, and unresolved legal relationships.
- Formula tests prove valid Content MathML round-trips and source-token equivalence; changed signs,
  exponents, subscripts, denominators, comparison operators, digits, decimal separators, or units
  are blocking mismatches.
- Reconciliation tests prove model agreement alone cannot override deterministic failure or
  official contradiction, and that missing evidence produces `unknown`/review rather than a pass.
- Full accounting rejects missing/duplicate/nonterminal documents, pages, bundles, passes,
  candidates, validation jobs, snapshots, and findings while preserving a complete report.
- Import contracts prove no HTTP, inference, corpus, jurisdiction, or validation dependency enters
  `cadgpt_engine`.

## How to prove it ran

```sh
make verify

validation_root=$(mktemp -d /tmp/cadgpt-inbr-validation.XXXXXX)

uv run cadgpt-regulations web-evidence \
  --catalog packages/regulations/src/cadgpt_regulations/data/inbr_catalog.json \
  --output-root "$validation_root/web"

uv run cadgpt-regulations validate-semantics \
  --extraction /tmp/cadgpt-inbr-extraction.FINAL/extraction.json \
  --extraction-root /tmp/cadgpt-inbr-extraction.FINAL \
  --structure-root /tmp/cadgpt-inbr-structure.FINAL \
  --transcription-root /tmp/cadgpt-inbr-transcription.FINAL \
  --web "$validation_root/web/web-evidence.json" \
  --web-root "$validation_root/web" \
  --output-root "$validation_root/semantic"

uv run cadgpt-regulations validation-check \
  "$validation_root/semantic/validation.json" \
  --root "$validation_root/semantic"
```

The evidence must show:

- 43/43 cohort artifacts map to official INBR evidence, with exact landing/media link chains and
  reproducible snapshot hashes;
- the report explicitly states that 43/43 processing does not prove current completeness and lists
  every discovered official document outside the cohort, including the newer Volume 12 edition and
  known correction records;
- every accepted semantic candidate passes anchor, quote, hierarchy, reference, numeric, unit,
  table, and formula checks applicable to it; skipped checks have explicit reasons;
- every formula/operator/token difference and unresolved unit/symbol mapping is quarantined rather
  than repaired or voted through;
- all blind-pass disagreements and independent Luna validation outcomes remain traceable, and no
  model-only assertion becomes publishable against deterministic or official contradictory evidence;
- every document, page, bundle, candidate, official snapshot, and finding reaches exactly one
  terminal state without stopping for human input;
- a fully offline rerun from pinned web/model/source evidence produces byte-identical validation
  outputs, while a live-source change creates new history and drift findings without overwriting the
  earlier snapshot.

## Evidence

Not run yet.

## Review

Required because this task establishes the publication gate and introduces bounded network evidence
alongside model-derived semantics.
