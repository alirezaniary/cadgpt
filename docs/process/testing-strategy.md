# Testing strategy

## The split

**50/50 unit and integration, by count, per module.** Enforced at 40–60% by `make verify`
gate 15, reported per module.

The ratio is not arbitrary. Unit tests prove that a piece is correct in isolation, which in
this system is the *less* interesting half: our correctness risks live at boundaries — a
convention lost between derivation and evaluation, an `INDETERMINATE` collapsed on the way to
a report, a rule that compiled but requires an observation nothing produces. A suite skewed
to unit tests proves every piece and misses every one of those.

A suite skewed to integration tests fails differently: a break points at the whole pipeline
and localizing it costs a session.

## Mocking: as little as possible

**Permitted:** exactly one thing — a genuine external boundary that cannot run locally.

- A hosted inference API (costs money, non-deterministic).
- A vendor authoring application (not installable in CI).

That is the complete list. Each use is named and justified in the module's `readme.ai.md`.

**Forbidden, without exception:**

| Never mock | Do this instead |
| --- | --- |
| Our own code | Call it. If that is hard, the boundary is wrong. |
| `ifcopenshell` and the IFC libraries | Run them over a small real model. They are fast. |
| The filesystem | `tmp_path`. |
| The database | A real PostGIS container. It is already in the compose file. |
| Time | Inject a `RegulatoryTimeline`. The four dates are domain data, not ambient clock. |
| An IFC file | Generate a real minimal one. |

**Mocking our own code is how a green suite ships over a broken system.** It has already
happened in this workspace, and it is the same defect the product exists to eliminate,
appearing inside the product. A test that mocks the thing under test proves the mock.

## Behaviour crosses layers

**Every behaviour has at least one test entering at the outermost real entry point and
exiting at the real output.** A behaviour proven only inside one layer is not proven.

For a rule, that means: a real fixture model in, the real derivation run, the real compiled
IDS, the real `ifctester` call, and the real finding out — with its status, basis, margin and
attribution asserted. Not "the compiler produced valid XML."

This is what makes the 50% integration half meaningful. An integration test that stops at a
module boundary is a slow unit test.

## Fixtures are code

Test models are produced by a committed deterministic generator script under `fixtures/`.
Never a committed binary.

A `.ifc` in a diff is unreviewable. Nobody can see that a fixture's stair width changed from
1.10 to 1.20, so nobody can see that a passing test now passes for a different reason. A
generator script makes that a one-line diff.

Generators are minimal — the smallest model exhibiting the behaviour. A fixture carrying
irrelevant geometry makes every test using it slower and its failures harder to read.

**Inherit before generating.** `docs/architecture/test-assets.md` inventories what already
exists — notably buildingSMART's 250+ paired `.ids`/`.ifc` test cases, which are exactly the
rule-plus-model pairs the evaluation wrapper needs. Study `IfcScript` before writing a
generator.

**A rule and its fixtures may not come from the same generator** (`prd.md` §8). This applies
to our code as directly as to the corpus: where a Task session writes an implementation, its
adversarial fixtures are specified by the Lead in the task spec, not invented by the
implementer to match what they built.

## Determinism

Gate 16 runs the suite twice with varied seeds and fails on disagreement.

No network. No wall-clock. No dependence on dict or filesystem ordering. Any randomness has a
pinned seed. Geometric tolerance is explicit and named — never a bare `pytest.approx` with a
default, because tolerance is a domain concept here (`docs/ddd/02-ubiquitous-language.md`) and
a defaulted one in a test is an undeclared tolerance policy.

## What every slice must prove

An L3 slice is not complete until its tests cover all five:

1. **The happy path**, end to end, real input to real output.
2. **The missing-input path** — the input is absent and the result is `INDETERMINATE` with a specific machine-readable reason. Never an exception, never a `PASS`, never absent.
3. **The boundary** — at the limit, and within tolerance on both sides of it, asserting near-miss where the policy says so. Designers draw to the limit, so this is where real findings cluster.
4. **The citation** — the basis resolves, the attribution names a pack version and a ratifier, the margin is present and correctly signed.
5. **The negative** — a model that should fail, does, for the stated reason and not by accident.

Missing (2) is the most common gap and the most dangerous, because its absence is invisible:
the suite is green, the feature demos, and the system silently passes unchecked buildings.

## Property tests where a rule is universal

A few invariants are quantified over all inputs and deserve `hypothesis` rather than examples:

- No input to any aggregation function maps `INDETERMINATE` to `PASS`.
- Every constructed `Observation` has a convention in its property name.
- Every constructed `Finding` has a resolvable basis.
- Finding identity is stable across two runs over the same input.

These are cheap, they encode the invariants from `docs/ddd/04` directly, and they are how a
universal claim gets tested as a universal claim.
