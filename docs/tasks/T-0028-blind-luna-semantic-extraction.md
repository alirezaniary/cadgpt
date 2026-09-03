# T-0028 - Extract source-anchored semantics with blind Luna workers

**Phase:** Regulation corpus 5   **Status:** open
**Touches invariants:** I1, import contracts

## Why

The page and structure layers make every source character, region, table, and formula addressable,
but they do not state what a provision requires, permits, prohibits, defines, qualifies, or refers
to. Convert each bounded structural bundle into candidate semantic records using two independent
Luna passes. Models may classify and relate deterministic source IDs; they may never manufacture
verbatim evidence or directly publish a rule. Disagreement and uncertainty become durable review
data instead of being averaged away.

## Scope

- Add `extract-jobs`, `extract-ingest`, and `extraction-check` commands in the regulations package.
  The commands prepare deterministic jobs, validate externally produced Luna responses, reconcile
  blind passes, and account for every input bundle. They do not put an inference client in
  `cadgpt_engine`.
- Generate one immutable job manifest per T-0027 bundle and blind pass (`A` and `B`). Each job binds
  the catalog/source/configuration identities, structural bundle hash, prompt version/hash, strict
  response schema hash, model identifier, pass label, maximum bytes, and exact allowed source IDs.
  Pass B receives no output, summary, confidence, or failure information from pass A.
- Use the T-0026/T-0027 bundles of at most ten contiguous pages. If a model transport rejects a
  bundle or exceeds its context/byte limit, deterministically split at structural boundaries and
  finally fall back to single-page jobs. A failed retry must not repeat a known HTTP 413 payload.
- Define a strict semantic-candidate schema. Candidate kinds include `scope`, `definition`,
  `requirement`, `prohibition`, `permission`, `recommendation`, `exception`, `condition`,
  `procedure`, `reference`, `table_rule`, and `formula_rule`. Every candidate identifies its exact
  supporting and qualifying source span/structure IDs; quoted Persian is always re-derived during
  ingestion and is never accepted from the model response.
- Represent a candidate as structured relations rather than prose alone: subject/concept,
  predicate or regulated property, modality, comparator, scalar/range/set value, printed and UCUM
  unit references, conditions, exceptions, temporal or occupancy scope, cross-references, formula
  IDs, table-cell IDs, and dependency edges. Unknown fields stay explicit `null`/`unknown`; the
  worker may not fill a missing value from general knowledge.
- Preserve source Persian and add an English semantic gloss as a separate model-derived field with
  pass/model provenance. Translation never replaces source text, changes identity, or becomes
  exact evidence. Conflicting translations remain alternatives for later reconciliation.
- Formula-bearing candidates reference T-0027 formula IDs and symbol records. Luna may classify
  formula purpose and connect variables to provisions, but it may not rewrite formula tokens or
  create Content MathML. Any mismatch between a claimed variable/value and verified formula
  evidence is a blocking review flag.
- Ingest raw responses only from private, caller-owned output roots. Retain the exact response
  bytes, transport/model metadata, termination reason, and schema diagnostics in content-addressed
  history outside Git. Reject symlinks, traversal, duplicate job responses, unknown source IDs,
  prompt/schema drift, and responses claiming a different model or job identity.
- Reconcile passes deterministically. Exact structural agreement becomes a paired candidate;
  compatible partial records remain distinct alternatives with a machine-readable difference;
  contradictions, missing high-impact provisions, unsupported anchors, translation conflicts,
  and formula/table disagreements enter a validator queue. Neither majority vote nor numeric model
  confidence may cross the publication boundary.
- Produce a separate validator-job manifest for an independent Luna worker that sees the source
  bundle and the anonymized alternatives but not which pass produced them. A validator may select,
  merge by field with explicit provenance, reject, or defer; it cannot add a new source anchor or
  author verbatim evidence. Deterministic ingestion rechecks every validator decision.
- Keep every bundle and response in a terminal state: `accepted_candidate`, `needs_validation`,
  `needs_review`, or `failed`. Processing continues without human input. Human-required items are
  append-only deferred-review records and cannot enter publishable data.
- Provide queue manifests that the session coordinator can execute with the available parallel
  `gpt-5.6-luna` worker slots. Work is leased idempotently and can resume after interruption without
  rewriting completed responses. Concurrency is configurable; correctness must not depend on job
  completion order.
- Do not crawl the web, decide legal precedence, compile IDS, or call the checking engine in this
  task. Official-web corroboration and final publication are separate gated stages.

## Tests

- Fixtures cover each semantic kind, nested conditions/exceptions, cross-page clauses, definitions,
  table-derived limits, formulas, cross-references, repeated terms, conflicting translations, and
  provisions that are intentionally not machine-actionable.
- Response ingestion rejects unknown/duplicate/out-of-bundle IDs, model-written quote substitution,
  schema/prompt/job drift, malformed values/units, impossible formula references, traversal,
  symlinks, partial writes, and unaccounted response files.
- Blind-pass reconciliation is order-independent and deterministic. Agreement, compatible partial
  overlap, contradiction, omission, unsupported assertion, and validator deferral each reach the
  correct terminal state without using model confidence as truth.
- Bundle splitting proves a rejected ten-page payload is never retried unchanged and eventually
  reaches bounded page jobs while retaining full source coverage.
- Two ingest/reconcile runs over identical raw responses produce byte-identical candidates, queues,
  manifests, and review flags; the second run reuses outputs without changing mtimes.
- Import contracts prove all inference orchestration stays outside `cadgpt_engine`; the engine has
  no network, model SDK, jurisdiction, prompt, or corpus imports.
- Real-path tests use Luna, not mocked extraction, for Volume 1 pages 11-20, the photographed
  clarification, a formula-bearing bundle, a continued table, and a watermarked page.

## How to prove it ran

```sh
make verify

extraction_root=$(mktemp -d /tmp/cadgpt-inbr-extraction.XXXXXX)

uv run cadgpt-regulations extract-jobs \
  --structure /tmp/cadgpt-inbr-structure.FINAL/structure.json \
  --root /tmp/cadgpt-inbr-structure.FINAL \
  --output-root "$extraction_root" \
  --model gpt-5.6-luna \
  --blind-passes 2

# The coordinator drains pending job manifests with parallel Luna workers and stores each raw
# response under the private extraction root. This command ingests completed responses and emits
# validation jobs without trusting worker-written evidence strings.
uv run cadgpt-regulations extract-ingest \
  --jobs "$extraction_root/jobs.json" \
  --root "$extraction_root"

uv run cadgpt-regulations extraction-check \
  "$extraction_root/extraction.json" \
  --root "$extraction_root" \
  --structure-root /tmp/cadgpt-inbr-structure.FINAL
```

The evidence must show:

- every structural bundle covering all 43 documents and 5,892 pages has two independent terminal
  extraction passes, with deterministic fallback jobs where transport limits required them;
- all accepted Persian evidence text is regenerated from valid T-0027 IDs and byte-compares with
  stored source evidence; no Luna-authored string is marked verbatim;
- Volume 1 pages 11-20 preserve the source heading/clause order while both blind outputs and their
  disagreements remain inspectable;
- all photographed, formula-bearing, table-bearing, continued, and watermarked pilot bundles have
  two blind passes plus independent validation where the passes disagree;
- all formula/table semantics reference verified T-0027 records and every token/value disagreement
  becomes a blocking deferred-review flag;
- response, prompt, schema, model, transport, split, reconciliation, and validator provenance can
  reconstruct every candidate decision;
- interrupted execution resumes from the job lease/receipt state and reuses completed responses;
- the final extraction check reports complete accounting by document, page, bundle, pass, candidate
  kind, validator outcome, failure, and review reason, while unresolved content remains excluded
  from publication.

## Evidence

Not run yet.

## Review

Required because model output is entering the regulation authoring pipeline and this task defines
the semantic assertion boundary consumed by validation and publication.
