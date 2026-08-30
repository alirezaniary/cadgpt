# DEC-0014 — The first judgeable outcome is a coverage report on a real model

**Status:** DECIDED
**Date:** 2026-08-30
**Decided by:** Stakeholder
**Affects:** `docs/roadmap/L1-outcomes.md` (O1), `docs/roadmap/L2-O1-capabilities.md`

## Problem
Which outcome does the stakeholder judge first — and therefore which branch gets expanded and
built while every other stays enumerated but untouched.

## Constraints
- Stakeholder chose: a coverage report on a real model.
- `prd.md` §11 Gate 5 calls this *"the single largest product-design question in v0"*, and says
  it cannot be answered without real numbers in front of a real architect.
- `prd.md` §11 Gates 3 and 5 are not answerable by fieldwork alone — they require the ingest
  and derivation code to exist.
- O1 is also the only outcome with no unbuilt prerequisite (DEC-0013).

## Options
1. **A coverage report on a real model.** Answers Gates 3 and 5 with real numbers, and O1 is
   startable immediately.
2. **One cited finding end to end** on a fixture. Proves the architecture; proves nothing about
   real-world models, and depends on O2 and O3, both of which have external blockers.
3. **The rule-authoring harness on one chapter.** Answers Gate 1 and is the cheapest item on
   `prd.md` §11 — but its output is blocked on a named ratifier (DEC-0015).

## Decision
Option 1. O1 is the first outcome. Its six capabilities are enumerated in
`docs/roadmap/L2-O1-capabilities.md` and are built in strict order.

The honest first number is **observation-level**: "produced 31 of the 40 observation types this
requirement set needs; here are the 9 it could not, and why." Clause-level coverage —
"evaluated 12 of 80 provisions" — needs O2's ratified packs and is not claimed before then.

## Expected result
An architect reads the report and treats it as information rather than as a broken tool. If a
first run dominated by things the system could not determine reads as failure rather than as a
coverage statement, that is the most valuable thing v0 can learn, and learning it costs one
conversation instead of a release.

## Reopens if
Gate 2 returns that the market is overwhelmingly 2D. Then v0's import path has too few
reachable users, and `prd.md` §11's own recommendation applies: lead with authoring in a host
we control. The corpus and the engine are unchanged either way.

## Consequences accepted
The first shipped thing produces no findings at all. It measures what could be checked, not
what passed. That is a harder thing to demonstrate and the right thing to build first, because
`prd.md` §2's whole argument is that the oracle comes before everything downstream of it.
