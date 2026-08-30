# DEC-0029 — Gate 15 fails on the real tree, and T-0007 cannot fix it inside its own Files list

**Status:** DECIDED
**Date:** 2026-08-30
**Raised by:** Subagent, T-0007 (test discipline gates), second dispatch
**Decided by:** Lead
**Affects:** `tools/gates/test_balance.py`, `tools/tests/test_verify.py`,
`tools/tests/test_gates_static.py`, `tools/tests/test_gate_isolation.py`,
`tools/tests/test_gate_jurisdiction.py`, `tools/tests/test_gate_module_contract.py`,
`tools/tests/test_gate_placeholder.py`, T-0007's own completion

## Problem
T-0007's contract for gate 15 is explicit: classification of unit versus integration is
**by marker only** (`@pytest.mark.integration`; an unmarked test counts as unit), and the
Files section forbids touching any test file's body beyond the two named exceptions
(`tools/tests/conftest.py` for the `spawns_harness` marker, `tools/tests/test_verify.py` for
one named assertion) — "do not touch any other test's body to make a balance number come out
right."

No test written before this task carries `@pytest.mark.integration`, because the marker did
not exist before it. Every one of the 58 pre-existing tests in `tools/tests/` therefore counts
as unit by the gate's own rule, regardless of what it actually does — including the tests the
task's own Invariants section names as textbook integration behaviour (`test_gates_static.py`'s
tree-copying, subprocess-spawning proofs; `test_gate_isolation.py`'s real `resolve()` against
this repository's `engine` group; the real end-to-end proofs in every other `test_gate_*.py`).
None of those five files is in T-0007's Files list, so none of them can be marked in this task.

Measured, with gate 15 and gate 16 both implemented exactly to spec and the 8 spawning tests
correctly marked `spawns_harness` (evidence below): `tools` is **65 unit / 0 integration — 0%,
outside the 40-60% band.** `verdict()` therefore returns `ok=False` for the only module gate 15
has anything to report on today.

This is not silent: the task's own Invariants section anticipated a version of this ("if
`tools/` fails on arrival then report that as the gate working — do not tune the rule until it
passes") and forbids exactly the moves that would paper over it (widening the band, touching
another test's body). What it did not anticipate is the specific mechanism by which the
failure becomes load-bearing rather than merely reported: `tools/tests/test_verify.py`'s
existing, protected `test_make_verify_over_the_real_tree_exits_zero` —

```python
@outermost_run_only
def test_make_verify_over_the_real_tree_exits_zero() -> None:
    result = make_verify(REPO_ROOT)
    assert result.returncode == 0, result.stdout + result.stderr
    assert f"{len(REGISTRY)} gates registered" in result.stdout
```

— runs a real `make verify` over this checkout and asserts `returncode == 0`. The moment gate
15 and gate 16 are registered in `REGISTRY`, this test starts exercising them too, and it fails
for real: `make verify` now exits 2, with `FAIL  gate 15  test-balance` and everything else
passing (full output below). T-0007's Files section does not list this test among what may be
changed, and its instructions for `test_verify.py` say only to add one named assertion
elsewhere and "do not change what that test already asserts." I cannot make it pass without
one of:
- marking a pre-existing test `@pytest.mark.integration` in a file the Files list forbids me
  to touch,
- widening the 40-60% band, which the Invariants section explicitly forbids, or
- changing what `test_make_verify_over_the_real_tree_exits_zero` asserts, which the Files
  section explicitly forbids.

Each is a decision the spec reserves to the Lead (`CLAUDE.md` §0). I am stopping here rather
than picking one.

## Constraints
- `docs/roadmap/tasks/T-0007-test-discipline-gates.md` Files section: touch only the files
  listed; do not touch another test's body to make a balance number come out right; do not
  change what `test_only_the_spawning_tests_skip_one_level_down` already asserts (the only
  sanctioned edit to `test_verify.py`).
- Same spec, Invariants: "Do not widen the band to make the current tree pass"; classification
  is explicit-marker-only, decided "by what the marker says, not by what keeps the existing
  tree green."
- `CLAUDE.md` §0: a subagent that meets an unresolved decision does not decide.
- `CLAUDE.md` §9 / `docs/process/definition-of-done.md`: `make verify` passes clean is
  condition 1 of done — in tension with the above once gate 15 is registered honestly.

## Options
1. **Mark the genuinely-integration tests in the five existing `test_gate_*.py` /
   `test_gates_static.py` files.** Matches the Invariants section's own worked example (the
   three tree-copying, subprocess-spawning tests in `test_gates_static.py` "are integration"
   under `CLAUDE.md` §7's reading) and would very likely bring `tools` into band — these files
   are integration-heavy by the task's own account. Cost: requires touching five files T-0007's
   Files section does not list, which is either a spec correction or a scope T-0007 does not
   have.
2. **Accept gate 15 failing on the real tree as this task's honest, final state**, and adjust
   `test_make_verify_over_the_real_tree_exits_zero` so it no longer asserts unconditional
   success (e.g. asserts the registered count and that only gate 15 is in the failing set, or
   is narrowed the way other real-tree proofs already are). Cost: the Files section forbids
   changing what that test asserts; matches the spirit of "report honestly" but requires
   reinterpreting an explicit constraint.
3. **Widen the 40-60% band.** Explicitly forbidden by the spec's own Invariants section; not a
   real option, listed for completeness.
4. **Scope gate 15 away from `tools/` for now** (e.g., `src/`-only, mirroring gates 5/6/7's P0
   story where `src/` does not exist yet and the gate is proven by fixtures alone). Cost:
   contradicts the spec's own Invariants section, which walks through `tools/tests/`'s counts
   as the gate's first live subject and expects a real verdict from it, not a vacuous pass.

## Decision — Lead

**Renumbered from DEC-0028 on integration.** The Lead took that number for an unrelated record
while this session was running. The collision is the Lead's, not the session's.

**Option 1. The pre-existing tests are marked, honestly, by what they do.** T-0007's Files list
is extended to permit `@pytest.mark.integration` in the five test modules, and *only* that: a
marker added, no test body rewritten, no assertion changed, no band moved.

This was a defect in the spec, not in the design. The spec's own Invariants section walks
through `test_gates_static.py`'s three tree-copying, subprocess-spawning proofs and concludes
they "are integration" under `CLAUDE.md` §7 — then forbade the files that would let anyone say
so. A classification rule with no way to classify anything is not a strict rule, it is an
inoperative one, and it read as strict only because nothing had ever run it.

**Adding a marker is not tuning the number.** The constraint the Files section was protecting —
"do not touch another test's body to make a balance number come out right" — stands unchanged,
and still forbids the move it was written against: rewriting, splitting or deleting tests to
shift the ratio. Stating what a test already is, is the opposite of that.

**The band is not touched, and it did not need to be.** Measured over the tree as it stands,
classifying by whether a test crosses a layer boundary — `copied_tree`, `make_verify`,
`gate_result_in`, a real `subprocess`, a real `resolve()`:

```
test_gate_isolation.py            unit  2   integration  2
test_gate_jurisdiction.py         unit  6   integration  4
test_gate_module_contract.py      unit  9   integration  5
test_gate_placeholder.py          unit  5   integration  4
test_gate_test_discipline.py      unit  6   integration  1
test_gates_static.py              unit  0   integration  6
test_verify.py                    unit  9   integration  6
                                  ────────────────────────
                                  unit 37   integration 28   →  43% integration
```

43% sits inside the band with room on both sides, so the honest classification and the green
build are the same outcome here and the tension this record was raised about does not actually
arise. **That is a fact about today's tree, not a licence.** The marker goes on what a test
genuinely is. If a future tree's honest split falls outside the band, the fix is tests, and the
band still does not move.

The counts above are a Lead heuristic over call sites and are **not** the classification. The
task session marks each test by reading it. Disagreeing with this table is expected and is the
session's call; a disagreement it cannot justify is a finding.

**`test_make_verify_over_the_real_tree_exits_zero` is left exactly as it is.** Option 2 would
have weakened the one test asserting this repository's own build is green, to accommodate a gate
that was mis-specified. The pinned test is right; the spec was wrong.

## Expected result
`make verify` exits 0, nine gates registered, 0 failed, and gate 15 prints a real per-module
table for `tools` whose integration share is inside the band and comes from markers a human put
there deliberately.

## Reopens if
An honest classification of some future module lands outside 40–60% and the fix by tests is
genuinely unavailable. That is a conversation about the band held with the number in front of
it, and it is not this record.

## Consequences accepted
Marking 28 tests is a large mechanical diff across five files nothing else in T-0007 touches,
and a reviewer has to read it as classification rather than as behaviour change. That is why it
ships as its own task (T-0007a) with its own review, rather than as a late amendment to a
session that has already reported.

## Evidence
A clean, top-level `make verify` (4m41s total, under DEC-0027's ~6m20s estimate):
```
$ make verify
python3 -m tools.verify
PASS  gate 1  format-and-lint
        All checks passed!
        20 files already formatted
PASS  gate 5  jurisdiction-guard
PASS  gate 6  placeholder-scan
PASS  gate 7  module-contract
FAIL  gate 15  test-balance
        tools: 65 unit / 0 integration (0% integration, OUTSIDE 40-60% band)
PASS  gate 2  types
        Success: no issues found in 20 source files
PASS  gate 16  determinism
        57 tests, 2 runs, seeds 1/2, agreed; 8 deselected (spawns_harness)
PASS  gate 4  isolation-proof
        51 packages resolved from the engine group; anthropic, openai raise ImportError there; HTTP-capable present: requests via ifctester, urllib3 via ifctester, flask via ifctester, bcf-client via ifctester
FAIL  gate 14  tests
        [...] 2 failed, 63 passed in 226.11s: test_make_verify_over_the_real_tree_exits_zero,
        test_nothing_is_skipped_without_the_nesting_marker — both fail purely because gate 15
        fails inside the nested `make verify` / `pytest` runs they spawn; every other test
        (including all seven new to this task, and the pre-existing 58 unaffected by gate 15)
        passes.
9 gates registered, 2 failed
make: *** [Makefile:12: verify] Error 1
```
Gate 15 is the only *direct* failure. Gate 14 fails *only* because it re-runs this same suite,
which contains the two tests above that transitively depend on gate 15 passing over the real
tree. Gate 16 — the other gate this task adds — passes cleanly on the real tree (both runs
combined: 9-29s across several measurements, well inside DEC-0027's ~24s-per-run estimate) and
is not implicated in either failure.
