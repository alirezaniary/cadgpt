# DEC-XXXX — <short imperative title>

**Status:** OPEN | DECIDED | SUPERSEDED by DEC-YYYY
**Date:** YYYY-MM-DD
**Decided by:** Lead | Stakeholder | `prd.md` §N
**Affects:** <modules, contexts or documents>

## Problem
What was actually in the way. Concrete. If this section could be written before the problem
was met, it is not the problem — it is a preference.

## Constraints
What was not negotiable, and where each comes from — an invariant, a `prd.md` decision, a
physical limit, an external dependency. This is the section that makes the decision
reproducible: someone rereading it should be able to see that the answer was forced, or see
exactly which constraint was traded.

## Options
Each with its consequence. Options nobody would choose are not options; do not pad this.

## Decision
One paragraph. What we are doing.

## Expected result
What we expect to observe if this was right. **Falsifiable.** "Better maintainability" is not
an expected result. "The engine environment resolves no inference SDK, provable by an import
probe in CI" is.

## Reopens if
The specific evidence that would make us revisit. "Never" is a legitimate answer and should be
written when true.

## Consequences accepted
What this costs. Every real decision costs something; a decision record with no cost is
describing a preference.
