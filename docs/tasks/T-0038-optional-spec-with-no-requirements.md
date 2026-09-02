# T-0038 — A specification that asserted nothing must not report PASS either

**Phase:** 3 — What the first real user needs   **Status:** open
**Touches invariants:** three-valued results, I7. **Reviewer-gated.**

## Why

T-0028 fixed this at the requirement level. The T-0028 reviewer found it still live one level
up, in the function T-0028 was explicitly forbidden to touch.

`judge()` at `packages/engine/src/cadgpt_engine/check.py:155-160` now carries a comment
asserting that reaching its final return proves "something was evaluated and passed". That is
false for a specification with **no requirement facets at all**. Reproduced: `<ids:requirements/>`
with `minOccurs="0" maxOccurs="unbounded"` over `IFCDOOR`, run against
`packages/engine/tests/fixtures/three_doors.ifc`:

```
spec APPLIES PASS optional matched 3 reqs 0 reason null
report status PASS, passed/failed/indeterminate all zero
```

It validates against the buildingSMART XSD, so it is reachable from real user input — a rule
author who selects a subject and has not yet written the requirement gets a green PASS over a
rule that asserts nothing. An *optional* specification with zero requirements checked nothing
and established nothing, and the report calls it a pass. That is the same I7 failure T-0028
just closed, one level up.

**The `required`-cardinality version is not a defect and must stay PASS.** `minOccurs="1"` with
zero requirements is a legitimate existence check — "at least one of these must exist" — and
`matched > 0` genuinely establishes it. The hole is specifically `optional` plus zero
requirements. A fix that turns existence checks indeterminate breaks a real feature.

## Scope

**Changes**

- `packages/engine/src/cadgpt_engine/check.py` — `judge()`. A specification with no requirement
  facets whose cardinality is `optional` established nothing and is `INDETERMINATE`, with a
  reason. And **either fix the comment at lines 155-160 or delete it** — a comment asserting an
  invariant the code does not hold is worse than no comment.
- `packages/engine/src/cadgpt_engine/status.py` — a `ReasonCode` if none fits; read the list
  first and reuse `NO_SUBJECTS_NOTHING_CHECKED` or its neighbours rather than adding a synonym.
- `packages/engine/pyproject.toml` — **bump the engine package version.** This release changes
  a verdict the engine can emit. See `docs/decisions.md`, *"A verdict-changing engine release
  bumps the engine version"*, which this task is the first application of; it is retrospective
  for T-0028 as well, so state in the evidence that the bump covers both changes.
- `packages/engine/tests/` — a fixture per case and a test per case.

**Does not change:** `_aggregate` (settled by T-0028), the `required`-with-zero-requirements
PASS, the report schema — the wire format does not move here, only the verdict, which is
precisely why the *engine* version and not `REPORT_SCHEMA_VERSION` is what bumps.

## How to prove it ran

```sh
uv run cadgpt-check packages/engine/tests/fixtures/three_doors.ifc <optional-no-reqs.ids> --json
uv run cadgpt-check packages/engine/tests/fixtures/three_doors.ifc <required-no-reqs.ids> --json
make verify
```

Evidence must show both: the optional-with-no-requirements specification flipping PASS ->
INDETERMINATE with its reason, and the required-with-no-requirements specification **still**
PASS. Paste before and after for both. Mutation proof on each new test. Quote the bumped
version line and the `CheckRun.engine_version` a fresh run now records — the point of the bump
is that a stored run says which engine judged it, so show a real run recording the new value.

## Evidence

<!-- the builder writes this -->

## Review
