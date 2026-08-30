# DEC-0025 — Harness findings are recorded, not recursed on; build agents are Sonnet

**Status:** DECIDED
**Date:** 2026-08-30
**Decided by:** Stakeholder, on measured token spend
**Affects:** `docs/process/agent-operating-manual.md`, every remaining task

## Problem
Through T-0003, roughly 55% of all agent tokens went into the harness proving its own test
scaffolding — T-0002a, T-0002b, T-0002c and T-0002d, ~800k tokens, four build sessions and three
reviews, producing no product capability. Each review finding spawned a remediation task, which
spawned a review, which found the next thing. The recursion was real work each time and still the
wrong allocation.

## Decision
1. **A finding about the harness's own tests is recorded in `tools/readme.ai.md` and the commit
   message. It does not spawn a task** unless it lets a *product* gate pass while the invariant it
   guards is violated.
2. **Build sessions run on Sonnet 5**, Opus only where a task turns on judgement rather than
   execution.
3. **A separate Review session is spent only on a gate that enforces a product invariant**
   (I1–I7). Mechanical gates are verified by the Lead running their acceptance and their rejection
   proof directly.
4. **Sibling gates of identical shape are one task, not one each.** T-0004, T-0005 and T-0006 are
   three `tools/gates/*.py` scanners over `src/`; they ship together.
5. Review may overlap the next build. `docs/process/agent-operating-manual.md`'s no-overlap rule
   was written to stop unreviewed work being integrated, and it still governs integration — but a
   review of an already-committed gate does not block the next task from starting.

## Expected result
Remaining P0 work — gates 5, 6, 7, 15, 16 — costs roughly what one of the T-0002x rounds cost.

## Reopens if
A mechanical gate ships broken and the Lead's own verification missed it, which would mean §3 is
too loose and Review comes back for that class.
