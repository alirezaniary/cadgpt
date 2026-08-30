# DEC-0013 — Prerequisite order is absolute; no part starts against an unbuilt dependency

**Status:** DECIDED
**Date:** 2026-08-30
**Decided by:** Stakeholder
**Affects:** every task, `docs/roadmap/dependency-order.md`

## Problem
The default way to go faster is to start several things at once and integrate later, stubbing
across the gaps. In a codebase written by sessions that share no context and cannot notice a
drifted assumption, that produces code written against a guess about a neighbour that does not
exist yet.

## Constraints
- Stakeholder direction: *"do not start a part that rely on other parts, keep the prerequisite
  order."*
- A Task session cannot detect that its assumption about an unbuilt module is wrong. It has no
  context in which the contradiction would appear.
- Stubbing a prerequisite is indistinguishable, in a diff, from implementing it. Six months
  later nobody can tell which modules were written against a stub.
- `prd.md` §11's own reasoning is the same shape: the phase plan is ordered by dependency, not
  by ambition.

## Options
1. **Parallel with stubs.** Maximum apparent throughput. Every stub is a wrong assumption with
   an unknown number of dependents, and the wrongness surfaces late and expensively.
2. **Parallel with mocks at real boundaries.** Better, and it still bakes in an interface nobody
   has validated against a real implementation.
3. **Strictly serial along the dependency graph.** No part starts while anything it depends on
   is unbuilt.

## Decision
Option 3, absolutely. Every task spec names its prerequisites and the **evidence** each is
complete. A subagent whose prerequisite evidence is missing stops without starting — it does
not stub, and it does not proceed on an assumption.

`docs/roadmap/dependency-order.md` is the graph, and the graph is the schedule. There is no
separate schedule.

## Expected result
No task is ever invalidated by a neighbour turning out different, because no task is written
before its neighbour exists. Rework caused by an assumption about unbuilt code should be zero,
and if it is not, this rule was broken somewhere and the record will show where.

## Reopens if
Never as a rule. The graph itself changes by decision record when a missing edge is discovered —
which stops the task and gets recorded, rather than being routed around.

## Consequences accepted
Real serialization, and it is the largest cost in this framework. O1's six capabilities run
strictly one after another even where two look parallelizable. Accepted because the alternative
converges more slowly in the end: this way, when the coverage report produces a number, every
part of the chain behind it was built against something real.
