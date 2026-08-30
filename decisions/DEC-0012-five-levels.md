# DEC-0012 — Five decomposition levels, expanded breadth-first

**Status:** DECIDED
**Date:** 2026-08-30
**Decided by:** Stakeholder, formalized by Lead
**Affects:** `docs/roadmap/`, `docs/process/decomposition.md`

## Problem
Getting from a one-sentence goal to tasks a bounded session can finish, without anyone holding
the whole system in their head, and without the plan acquiring false precision on one branch
while its siblings are still a phrase.

## Constraints
- Stakeholder direction: *"start from a big goal and break it down level by level until get to
  subagent doable tasks; don't act greedy, go layer by layer."*
- The stakeholder decides on outcomes, not details.
- A task is only executable if its contracts, context list and acceptance command are already
  written — which requires the level above it to be settled.

## Options
1. A flat backlog. Loses the level distinction, so stakeholder-judgeable outcomes and
   agent-doable tasks sit in one list and neither is legible.
2. Depth-first on the most interesting branch. The natural failure: the plan is precise where
   it does not matter and empty where the real dependency is, and that dependency is discovered
   after code exists.
3. Five levels, expanded breadth-first, one level at a time, on the branch the stakeholder chose.

## Decision
Option 3. L0 Goal, L1 Outcome, L2 Capability, L3 Slice, L4 Task. Each level is **fully
enumerated** before any node of it is expanded. The stakeholder is asked exactly once per
level, and only at L1.

Currently: L0 settled, L1 fully enumerated, L2 expanded for O1 only, L3 not written.

## Expected result
At every moment there is exactly one level being decomposed and one branch being expanded, and
the reason for both is written down. A plan reader can see what is settled, what is enumerated
but unexpanded, and what has not been thought about — as three distinct states rather than one
blur.

## Reopens if
A level proves to have the wrong granularity — L2 capabilities that are each one task, or L3
slices that are each five. Then the level definitions are adjusted here, not worked around
in the roadmap.

## Consequences accepted
It feels slow. Enumerating ten L1 outcomes when only one will be built looks like waste, right
up until the moment a dependency in outcome six changes the shape of outcome one — which is
exactly what breadth-first exists to catch, and it catches it on paper rather than in code.
