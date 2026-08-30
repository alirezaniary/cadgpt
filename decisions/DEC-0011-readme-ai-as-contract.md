# DEC-0011 — `readme.ai.md` is the module contract, and it is mandatory

**Status:** DECIDED
**Date:** 2026-08-30
**Decided by:** Stakeholder, formalized by Lead
**Affects:** every module, `make verify` gate 7

## Problem
Work is done by many short sessions that share no conversation. A session working on module A
while depending on module B has to learn B somehow. Reading B's source costs context the task
needs for its own work, and it teaches the session what B *does* rather than what B *guarantees*.

## Constraints
- Stakeholder direction: every module carries a `readme.ai.md`.
- Context length is a defect (`docs/process/agent-operating-manual.md`). Every file a session
  reads is budget it cannot spend on the work.
- Boundaries are invisible in the flat layout (DEC-0002), so each module must state its own.
- The information a session actually needs — which invariants this module owns, which edges it
  must not cross, what it refuses to be responsible for — has no function to attach a docstring to.

## Options
1. Docstrings only. Describe functions; cannot express a boundary or an ownership claim.
2. A central architecture document. Single point of drift, and it grows past what a session can
   afford to read.
3. A per-module contract file with fixed sections, mandatory, machine-checked.

## Decision
Option 3. Nine fixed sections, in a fixed order, checked for presence and conformance by
harness gate 7: Purpose, Context, Contract, Invariants enforced here, Depends on, Must not
depend on, Tests, How to run it, Open questions.

Written in the **same task as the code, by the same agent**. A documentation pass afterwards
documents what the code appears to do, which is information the reader already has.

The Contract section is **normative**: code disagreeing with it is a bug in the code.

## Expected result
A session can work against a neighbouring module having read only its `readme.ai.md`. When that
is not enough, the neighbour's contract is inadequate — a defect in the neighbour, filed as one.

"How to run it" carries a real command over real input, which is what
`docs/process/definition-of-done.md` condition 2 executes.

## Reopens if
Never in principle. The section list may grow if a recurring gap appears; sections are not
removed, because each exists to answer a question a bounded session actually asks.

## Consequences accepted
Documentation cost on every task, and a file that can drift from its code. Mitigated by gate 7
checking conformance and by Review reading contract against diff — not by hoping.
