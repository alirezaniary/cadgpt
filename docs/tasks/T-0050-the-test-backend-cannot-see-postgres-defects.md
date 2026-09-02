# T-0050 — The suite cannot catch the class of defect that only Postgres enforces

**Phase:** 3   **Status:** open
**Touches invariants:** none, but this is about the evidence standard itself.

## Why

Found by the T-0031 review, and demonstrated by T-0031 itself. When `Review.rule_set` became
nullable, `CheckRunExecutor._claim`'s `select_for_update()` over `select_related("review__rule_set")`
became a lock across a LEFT OUTER JOIN. `make verify` was green throughout — sqlite does not
enforce the restriction — and the first real check against the compose stack's Postgres failed
with `NotSupportedError: FOR UPDATE cannot be applied to the nullable side of an outer join`.

It was found by running the stack, which is the fifth defect in this repository found that way
rather than by its suite. The fix (`select_for_update(of=("self",))`) is correct and is one line;
what is unguarded is the **class**. Nothing in the suite would catch its reintroduction, and the
only proof it works is a manual compose run pasted into a task file. The next nullable relation
added to a locked queryset reproduces it exactly, and reproduces it in production.

This is the repository's documented failure mode stated precisely: a green suite over a system
that does not work, because the test backend is not the production backend.

## Scope

**Changes**

- The tests that exercise database behaviour Postgres enforces and sqlite does not run against
  **Postgres**. The compose stack already has one; the decision is whether that is a separate
  marked suite, a CI-only backend switch, or `make verify` moving to Postgres wholesale.
  `make verify` is required to stay fast and hermetic, which argues against the last — but say
  which was chosen and why, because this decision outlives the task.
- A regression test that fails on the T-0031 defect specifically: `_claim` locking across a
  nullable outer join.
- The choice recorded in `docs/decisions.md`.

**What explicitly does not change**

- `make verify`'s speed and hermeticity, unless the evidence argues the trade is worth it.
- The `select_for_update(of=("self",))` fix, which is already correct.

## How to prove it ran

Revert the `of=("self",)` fix and show the new test **failing** — against Postgres — then restore
it and show it passing. That mutation is the whole task: a guard that does not fail on the
original defect is not a guard. Paste both runs, and state the wall-clock cost added to whichever
gate now runs against Postgres.

## Evidence

## Review
