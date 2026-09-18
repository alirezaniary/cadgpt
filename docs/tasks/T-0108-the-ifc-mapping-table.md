# T-0108 — Author the Persian-to-IFC mapping as reviewable, source-cited data

**Phase:** Regulation corpus 8 — source-cited rule codification   **Status:** open
**Touches invariants:** I1, measure never invent, three-valued

## Why

This is the actual remaining work, and it is authoring, not plumbing. Across all 900 draft files
and 5,378 candidate records, **not one** carries an IFC target. Measured 2026-09-19, the
candidates break down by their own `implementation_type`:

| `implementation_type` | candidates |
|---|---|
| `unsupported` | 3,343 |
| `decision_table` | 833 |
| `formula_evaluator` | 599 |
| `native_ids` | 484 |
| `derived_ids` | 115 |
| `table_lookup` | 4 |

(Counts are over all draft files including duplicates; the authoritative per-chunk figures come
from T-0106's index. `table_lookup` is outside T-0031's documented five-value enum and is a
drift this task must classify explicitly rather than ignore.)

**The 484 `native_ids` candidates are the target.** They are the ones their own extraction step
judged expressible as a plain IDS facet. T-0107 built the command that consumes a mapping; this
task fills it. Without this, every compiled-rule count stays at whatever was hand-written for
T-0107's proof.

An LLM may help author these mappings — `CLAUDE.md` permits exactly that ("An LLM may help
author rules or explain results; it never decides pass or fail"). What it may not do is decide
at check time. The mapping is committed data, read deterministically by a compiler with no
model dependency, and that is what keeps I1 structural rather than remembered.

## Scope

- **A mapping file for the `native_ids` candidates**, in the format T-0107 defined, stored where
  T-0107 put it and validated by its schema. Authored per candidate by reading that candidate's
  `statement_fa` and its exact transcript quote — never by pattern-matching `rule_key` slugs.
- **Every entry carries the candidate identity it was authored from**, so a mapping can be
  audited back to the Persian sentence that justified it. A reviewer must be able to ask "why
  does this rule say `IFCSPACE.Height >= 2.4`" and get the sentence.
- **Measure, never invent, at mapping time.** If the Persian text states a bound but not what it
  applies to, or names a quantity the model would have to synthesise (a space that was not
  authored, a boundary, a classification), the candidate gets **no mapping entry** and is left
  to T-0109's uncompiled count. Do not pick a plausible IFC entity to make a rule compile. A
  guessed mapping is a confident wrong PASS, which is the single failure mode this product
  exists to avoid.
- **Classify, do not silently skip, the rest.** `decision_table`, `formula_evaluator`,
  `derived_ids`, `table_lookup` and `unsupported` candidates are not mapped here — but each must
  carry a reason code so T-0109 can report *why* it did not compile, not merely that it did not.
  `rule_capability.classify_rule` already produces exactly this shape (`status: "deferred"` with
  a `reason_code`, preserving the citation) and should be reused rather than reimplemented.
- **Batch this.** Do not attempt all 484 in one pass. Work document by document off T-0106's
  index, and stop at a natural boundary if the dispatch is running long — the task is finished
  around, with the remaining documents named, rather than narrowed and reported as complete.

**Does not change:** the compiler, the citation contract, the draft files, or any candidate. This
task adds mapping data and reason codes only.

## How to prove it ran

`make verify`, then the real path — the mapping actually driving compilation across more than
the one document T-0107 proved:

```sh
.venv/bin/python -m cadgpt_regulations.cli candidate-to-rule-ir \
  --batch-root <batches for the documents covered> \
  --mapping <the authored mapping> --output-root <root>/ir
```

The evidence must paste:

- how many `native_ids` candidates were reviewed, how many received a mapping, and how many were
  deliberately left unmapped **with the reason** — the last number is expected to be non-zero and
  a zero is itself suspicious;
- three mapping entries in full, each beside the Persian sentence it was authored from, one of
  which must be a case the author **declined** to map and why;
- the count of non-`native_ids` candidates given a reason code, broken down by reason;
- at least ten real `.ids` files compiled end to end from this mapping, one of them pasted in
  full, and an `ifctester.ids.open()` parse over all of them;
- which documents are covered and which remain, named explicitly.

## Evidence

<!-- the builder writes this -->

## Review
