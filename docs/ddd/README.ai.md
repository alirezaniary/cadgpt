# readme.ai.md — docs/ddd

## Purpose
The domain analysis. What the product is *about*, what the words mean, where the boundaries
are, and which rule is enforced by which object. Read before writing code in any context.

## Contents
| File | Answers |
| --- | --- |
| `01-domain-and-subdomains.md` | What is the domain, what is core vs supporting vs generic, what do we refuse to write |
| `02-ubiquitous-language.md` | What every term means; physical kind vs code role; the closed status sets; forbidden vocabulary |
| `03-bounded-contexts.md` | The ten contexts, the context map, and why each relationship has the pattern it has |
| `04-aggregates-and-invariants.md` | Every consistency boundary and every invariant, with its single owner |
| `05-import-contracts.md` | How I1 and I2 are machine-enforced, at two strengths |
| `06-property-vocabulary.md` | Which §5.3 property names IFC already defines, which are ours, and why |

## Contract
These files are **normative**. Code disagreeing with them is wrong, not the other way round.

## Invariants upheld here
- Vocabulary is single-sourced. A new term enters `02` in the same task that introduces it.
- An invariant appears in `04` exactly once, with exactly one owner.

## How to change
By decision record only. `02` and `04` are load-bearing for the build guards; editing them
without updating `docs/architecture/harness.md` desynchronizes doc from enforcement.

## Open questions
- Subject identity across a revised model (`04`, `Finding`). Genuinely hard, accepted as
  imperfect, deferred until dispositions arrive. `prd.md` §12.
