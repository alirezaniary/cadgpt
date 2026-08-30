# DEC-0009 — Two inference planes behind one OpenAI-compatible port

**Status:** DECIDED
**Date:** 2026-08-30
**Decided by:** Lead
**Affects:** `codification`, `assistance`

## Problem
`prd.md` §5.9 requires self-hosted open-weight inference *"for latency, cost, and keeping client
drawings inside the deployment's own network."* `prd.md` §8 requires an LLM API call over
regulatory text. Read as one requirement, self-hosting is imposed on codification too, and the
binding constraint on corpus quality — extraction accuracy over legal prose in a non-Latin
script — is traded away for a privacy property that workload does not need.

## Constraints
- The §5.9 privacy constraint attaches to **client drawings**. That is what must not leave.
- Regulatory text is **public**. `prd.md` §8 notes this is a materially better position than
  markets where an equivalent product needs a data licensing agreement.
- Codification is offline, batch, rare, and every draft passes a named human ratifier
  (`prd.md` §8, step 2).
- The assistance plane is online, per-request, and its output reaches the user unreviewed.
- Neither may be importable from `engine` (I1, DEC-0004).

## Options
1. Self-hosted for both. Uniform, and it caps extraction quality on the corpus — the asset —
   to buy privacy for text that is already public.
2. Hosted for both. Sends client drawings to a third party. Violates the §5.9 intent.
3. **Two planes:** hosted frontier API for codification, self-hosted open-weight for assistance.

## Decision
Option 3, both behind **one OpenAI-compatible interface**, so the backend is a configuration
value and neither plane's choice is embedded anywhere.

## Expected result
- Codification draft quality is bounded by the best available extraction, not by what fits on
  our GPUs — and the quote linter plus ratification measure it (`prd.md` §11 Gate 1).
- No client drawing crosses the network boundary. Provable: `assistance` is configured against
  a local endpoint, and the deployment can run with no outbound route at all.

## Reopens if
Open-weight extraction over Persian regulatory text measures within a few points of frontier
quality on a CODE-ACCORD-style held-out set. Then codification moves in-house too, and the
interface makes that a configuration change.

## Consequences accepted
Two inference configurations and a per-draft cost during codification. The cost is bounded by
corpus size, is incurred once per clause, and buys the quality of the asset the entire product
rests on.
