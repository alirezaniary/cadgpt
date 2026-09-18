# T-0109 — Compile the corpus, and publish what did not compile

**Phase:** Regulation corpus 8 — source-cited rule codification   **Status:** open
**Touches invariants:** three-valued, never assert compliance we did not establish

## Why

By this point one document is proven (T-0107) and the mapping exists (T-0108). What remains is
the batch run over all 668 chunks and 43 documents, and — the half that carries the invariant —
a release that states what it does **not** contain.

A release of 300 compiled rules drawn from a corpus of 5,378 candidates is honest only if it
says so. Left unstated, a downstream reader takes "the INBR pack" to mean the INBR code, and
every requirement that never became a rule silently becomes something the product implies it
checked. That is the `INDETERMINATE`-never-becomes-`PASS` discipline at the corpus boundary,
and it is the half of the retired T-0104 that was explicitly **not** deferred
(`docs/decisions.md`, 2026-09-19).

The mechanism already exists and does not need designing: `rule_release.build_rule_release_manifest`
takes `deferred_records` and emits a `coverage` block with `rules`, `verified_citations`,
`documents`, `source_spans`, `assertions` and `deferred` counts, and `write_rule_release`
installs every compiled `.ids` plus its sidecar under a content-addressed release directory.
Both were run successfully against real data on 2026-09-19. This task feeds them the whole
corpus and makes the deferred side complete rather than empty.

## Scope

- **A runner that batches the T-0107 spine over every chunk in T-0106's index** — provisional
  batch, rule IR, compile, release — restartable, so a failure at chunk 400 does not mean
  re-running 399. Follow `docs/inbr-operations.md`'s durable-workspace conventions; runs live
  under `.cadgpt/inbr/`, never `/tmp`.
- **Every candidate reaches a terminal state and is counted.** Compiled, or deferred with a
  reason code. The sum of compiled plus deferred must equal the total candidate count from the
  index, and the runner must fail loudly if it does not. No candidate may be absent from both
  sides of that ledger.
- **The deferred block of the release manifest is populated**, one record per uncompiled
  candidate, each keeping its source citation so a reader can find the Persian text that was not
  turned into a rule.
- **A human-readable coverage summary** alongside the manifest: per document, how many pages,
  how many candidates, how many compiled, and the deferred breakdown by reason code. This is the
  artifact that answers Gate 1 in `docs/plan.md` — "what does a first coverage manifest actually
  say in front of a real architect" — so write it to be read by one, in the wording the service
  layer would use rather than reason codes alone.
- **Chunk 42 and any other unresolved chunk from T-0106 appear in the summary as unprocessed
  source**, distinct from a candidate that was processed and deferred. A chunk we never read is
  not the same claim as a requirement we read and could not express.

**Does not change:** the compiler, the mapping, or the citation contract. If the batch run
surfaces a compiler defect, fix it here only if it blocks the run, and record it; otherwise
report it as an observation for the judge rather than widening this task.

## How to prove it ran

`make verify`, then the real full-corpus run:

```sh
.venv/bin/python tools/inbr_compile_corpus.py \
  --index .cadgpt/inbr/draft-index.json \
  --mapping <the T-0108 mapping> \
  --output-root .cadgpt/inbr/rule-release/<revision>
```

The evidence must paste:

- the runner's final summary — documents, chunks, candidates, compiled, deferred — and the
  arithmetic showing compiled + deferred equals the candidate total;
- `find .cadgpt/inbr/rule-release/<revision> -name '*.ids' | wc -l` and the release directory's
  `release_id`;
- the `coverage` block of `manifest.json` verbatim;
- the deferred breakdown by reason code, with the top three reasons named in plain language;
- one compiled `.ids` pasted in full, and an `ifctester.ids.open()` parse across **every** file
  in the release, with the failure count (which must be zero);
- a re-run of the compile step on identical input producing byte-identical `.ids` files —
  T-0031's completion check "a second compile from identical candidate input is byte-identical";
- the first ten lines of the human-readable coverage summary, so the wording can be judged.

## Evidence

<!-- the builder writes this -->

## Review
