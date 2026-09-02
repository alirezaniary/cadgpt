# T-0028 — A requirement that evaluated nothing must not report PASS

**Phase:** 3 — What the first real user needs   **Status:** open
**Touches invariants:** three-valued results, I7. **The reviewer will be dispatched on this
task.**

## Why

Found by the T-0026 reviewer while reproducing a prohibited specification on the real CLI, and
pre-existing rather than introduced there:

```
spec status FAIL, applicability APPLIES, cardinality prohibited,
reason PROHIBITED_SUBJECTS_PRESENT, matched 3
req  description: '...'   status PASS, 0/0/0, entities []
```

`_aggregate(failed=0, indeterminate=0)` in `packages/engine/src/cadgpt_engine/check.py`
returns `Status.PASS`. For an ordinary requirement where every matched entity passed, that is
correct and must stay correct. For a requirement that evaluated nothing at all, it is the
precise failure this engine exists to prevent, stated in `check.py`'s own module docstring and
in `status.py`'s: a rule that checked nothing has established no compliance, however green
`ifctester` reports it.

The engine already understands this distinction one level up. `judge()` was written for exactly
these zero-subject cases at the specification level — `NO_SUBJECTS_NOTHING_CHECKED`,
`NO_SUBJECTS_BUT_REQUIRED`, `PROHIBITED_SUBJECTS_PRESENT` — and the commit *"Applicability is
a separate question from status; a rule that checked nothing cannot pass"* is that reasoning.
The reasoning was applied to specifications and never pushed down to requirements. So a
specification can be correctly judged while a requirement inside it still reports a green PASS
over nothing, and the requirement is the row the architect actually reads.

This matters beyond the prohibited case. Any requirement whose `passed`, `failed` and
`indeterminate` are all zero has established nothing, and every count in the report that sums
requirement statuses inherits the error.

## Scope

**Changes**

- `packages/engine/src/cadgpt_engine/check.py` — `_aggregate` must distinguish "everything
  passed" from "nothing was evaluated". It currently takes only `failed` and `indeterminate`;
  it needs `passed` too, or the caller must decide before calling it. A requirement with no
  outcomes at all is `INDETERMINATE`, never `PASS`.
- `packages/engine/src/cadgpt_engine/status.py` — a `ReasonCode` for it, if none of the
  existing ones fits. Read the list first: `NO_SUBJECTS_NOTHING_CHECKED` exists and may be
  exactly right, in which case reuse it rather than adding a synonym. `RequirementOutcome` has
  no `reason_code` field today; if the reason is worth carrying it needs one, and that is a
  wire-format change requiring a `REPORT_SCHEMA_VERSION` bump.
- `packages/engine/tests/` — a test per case, asserting on real fixture output: a requirement
  where all matched entities passed is `PASS`; a requirement that evaluated nothing is
  `INDETERMINATE`. The prohibited-specification fixture added in T-0026 is the natural input
  for the second — reuse it rather than writing a second one.

**What explicitly does not change**

- `judge()` and the specification-level logic. It is right; this task pushes its reasoning down
  one level, it does not revisit it.
- The `PASS` verdict for a requirement that genuinely evaluated entities and all of them
  passed. This task must not turn real passes into unknowns — that would be the same invariant
  broken in the other direction, and it would make the tool unusable rather than merely wrong.
- Presentation. T-0025 owns the report view; if a new status appears on requirements it renders
  through the existing `StatusPill` path with no new component.

## How to prove it ran

```sh
uv run cadgpt-engine check packages/engine/tests/fixtures/three_doors.ifc \
                           packages/engine/tests/fixtures/door_width.ids --json
make verify
```

The evidence must show:

1. The `--json` output for the **prohibited-specification fixture**, with the requirement that
   evaluated nothing showing `INDETERMINATE` where it previously showed `PASS`. Paste the
   before and the after — this task is a change of verdict and the diff in the output is the
   proof.
2. The `--json` output for `door_width.ids`, showing the ordinary requirement **still** reports
   its real `PASS` for the door that genuinely passed. A fix that turns every requirement
   indeterminate passes finding 1 and destroys the product.
3. Both new tests by name in the `make verify` output.
4. Mutation check, since this is a verdict change and T-0026's first test did not constrain the
   code it was written for: revert the `_aggregate` change, show the new test failing, restore
   it, show it passing. Paste both.
5. **Wiring:** quote the changed `_aggregate` signature and every call site, showing none was
   left passing the old argument list.

Then `make up` and `make e2e` if any rendered text changed; if nothing user-visible changed,
say so and skip it rather than pasting an unchanged screenshot.

## Evidence

<!-- the builder writes this -->

## Review
