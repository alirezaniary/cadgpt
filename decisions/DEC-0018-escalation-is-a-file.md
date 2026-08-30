# DEC-0018 — A subagent never decides; escalation is a file and a stop

**Status:** DECIDED
**Date:** 2026-08-30
**Decided by:** Lead
**Affects:** every Task session

## Problem
A bounded session working from a spec will meet something the spec did not anticipate — an
ambiguous contract, an invariant that seems to conflict with the requirement, a missing
prerequisite. It has three moves: guess, ask, or stop. Ask does not exist; there is nobody in
the session.

## Constraints
- The stakeholder wants minimum involvement in details.
- `CLAUDE.md` §8: a decision reached and not written did not happen and will be re-litigated.
- A Task session has no context in which its guess could be contradicted. It cannot see the
  other modules, the other decisions, or the reasoning that produced its spec.
- DEC-0013: no work proceeds on an assumption about something unbuilt.

## Options
1. **Guess and note it in the report.** The guess is already in the code by the time anyone
   reads the note, and it has propagated to whatever was built next.
2. **Guess conservatively.** Same failure. "Conservative" is itself a judgement made without
   the context needed to make it.
3. **Write a decision stub with `Status: OPEN` and stop.**

## Decision
Option 3. On meeting anything unresolved, a Task session writes
`decisions/DEC-XXXX.md` with `Status: OPEN` — Problem, Constraints, Options with their
consequences, **no Decision line** — then stops and reports.

The Lead resolves it. Only if two answers produce two materially different *products* does it
reach the stakeholder, as a direction question.

## Expected result
Every decision in the codebase was made by something that could see the whole picture, and is
written down. A stopped task is one file to read. A guess is a wrong assumption with an unknown
number of dependents, discovered later and more expensively.

## Reopens if
Never. This is the mechanism that makes "minimum stakeholder involvement" compatible with
"every decision documented" — the alternative is undocumented decisions, which is neither.

## Consequences accepted
Stopped tasks and round trips through the Lead. That is the intended cost, and it is the same
argument `prd.md` §8 makes about ratification: the bottleneck is the point of it.
