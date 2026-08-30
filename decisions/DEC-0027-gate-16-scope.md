# DEC-0027 — Gate 16 varies seed and order over the suite minus the tests that spawn the harness

**Status:** DECIDED
**Date:** 2026-08-30
**Raised by:** Lead, on measured suite timings, before T-0007's second dispatch
**Decided by:** Lead
**Affects:** `tools/gates/determinism.py`, `pyproject.toml`, `tools/tests/conftest.py`,
T-0007's spec

## Problem
Gate 16 runs the suite twice and fails if the two runs disagree. Gate 14 already runs it once.
Three full runs per `make verify` is the naive reading of that, and the measurement says what it
costs:

```
$ uv run --group dev pytest tools/tests -q --durations=15
94.03s  test_verify.py::test_a_full_run_is_visibly_different_from_a_nested_one
79.84s  test_verify.py::test_nothing_is_skipped_without_the_nesting_marker
15.39s  test_gates_static.py::test_tests_gate_fails_on_a_failing_test
15.32s  test_gates_static.py::test_make_verify_fails_and_names_gate_14
15.26s  test_verify.py::test_make_verify_over_the_real_tree_exits_zero
14.08s  test_verify.py::test_only_the_spawning_tests_skip_one_level_down
...
58 passed in 257.83s
```

Six tests are 234 of the 258 seconds — **91%** — and all six are members of
`conftest.SPAWNS_A_RE_ENTERING_PROCESS`: they spawn `make verify` or `pytest`, which runs this
suite again. The other 52 tests together take about 24 seconds.

So gate 16 as written would add roughly 8.6 minutes to a `make verify` that is already 5m31s,
taking it past fourteen minutes — and it would spend 91% of that re-running the harness's proof
of its own scaffolding, which is the exact allocation DEC-0025 was written to stop.

## Constraints
- The gate must still be a real determinism check. Deselecting until it is cheap and calling it
  green is the silent-green failure this repository exists to prevent.
- `CLAUDE.md` §7 requires determinism with no ordering luck. A gate that varies only the hash
  seed and calls that "order varied" would be claiming something it did not check.
- `tools/tests/conftest.py` owns the recursion-safety mechanism and must not grow a second one.
- The excluded set must not become a second, unchecked spelling of
  `SPAWNS_A_RE_ENTERING_PROCESS`. `conftest.py`'s own docstring is explicit that a set derived
  from the thing it checks agrees by construction and proves nothing.

## Decision

**1. Gate 16 runs the suite twice with the harness-spawning tests deselected.** They carry a
`spawns_harness` marker; gate 16 runs `-m "not spawns_harness"`. Two runs of ~24s each, cost
tier 2. `make verify` goes to roughly 6m20s, not fourteen minutes.

**2. The marker is checked against the existing literal, not trusted.** `SPAWNS_A_RE_ENTERING_PROCESS`
stays the one hand-written set of node ids. `test_verify.test_only_the_spawning_tests_skip_one_level_down`
gains a second assertion: the set of node ids carrying `spawns_harness` equals that frozenset. A
test that grows a spawn and forgets the marker fails there.

**3. Order is varied for real, by inheriting `pytest-randomly`.** It is added to the `dev`
group — I3, inherit before writing; hand-rolling a shuffling collector here would be authoring
what the ecosystem ships. `[tool.pytest.ini_options].addopts` carries `-p no:randomly` so every
ordinary run — gate 14, a developer's `pytest`, every existing copied-tree proof — is
byte-for-byte unchanged and still order-stable. Gate 16 is the only caller that enables it, with
two different `-p randomly` seeds and two different `PYTHONHASHSEED`s.

This is a dependency added by decision, not by a session's improvisation. T-0007's standing
"do not add a dependency" still binds it for everything else.

**4. Gate 16 reports what it did not run, on pass as well as fail (DEC-0024).** Its detail names
the count it checked and the count it deselected, so a run that quietly stopped covering the
suite is visibly different from one that covered it. A gate that deselects and says nothing is
worse than no gate.

## Expected result
`make verify` reports ten gates in roughly six and a half minutes. Gate 16 prints something of
the shape `50 tests, 2 runs, seeds 1/2, agreed; 8 deselected (spawns_harness)`. A test whose
outcome depends on `PYTHONHASHSEED` or on collection order fails it and is named.

## Reopens if
A determinism defect is found in one of the eight deselected tests — that would mean the
exclusion is hiding the class of bug the gate exists to find, and the answer is then to make
those tests cheap (the copied-tree lever `session-state.md` already names) rather than to widen
the gate onto an eight-minute run.

## Consequences accepted
The eight tests that spawn the harness are not checked for seed or order sensitivity. They are
the tests least likely to have it — each asserts on the stdout of a subprocess it started — and
they are checked for *passing* by gate 14 on every run. The trade is stated in the gate's own
output rather than only here, which is the point of §4.
