# T-0007a — Classify the existing tests

Slice: S0.5 · Capability: P0 · Outcome: O1

## Prerequisites
| Requires | Evidence |
| --- | --- |
| T-0007 | Gates 15 and 16 registered; `python -m tools.verify --list` prints nine in cost order |
| DEC-0029 | `Status: DECIDED` |

## Objective
Gate 15 classifies unit versus integration by an explicit `@pytest.mark.integration` marker.
The marker did not exist until T-0007 created it, so every one of the 65 pre-existing tests
currently counts as unit and gate 15 reports `tools: 65 unit / 0 integration` and fails.

Mark each pre-existing test for what it actually is. That is the whole task.

## Context — read these and nothing else
- `CLAUDE.md` — §7 in particular, which is the classification rule
- `decisions/DEC-0029-gate-15-classification.md` — **binding**, including what it forbids
- `docs/process/testing-strategy.md`
- `tools/gates/test_balance.py` — how the gate counts, so you can predict its output
- The five modules you are marking, plus the two already-correct ones for comparison:
  `tools/tests/test_gates_static.py`, `test_gate_isolation.py`, `test_gate_jurisdiction.py`,
  `test_gate_module_contract.py`, `test_gate_placeholder.py`, `test_verify.py`,
  `test_gate_test_discipline.py`

## The rule you are applying
`CLAUDE.md` §7: **behaviour crosses layers.** A test is `integration` when it enters at a real
outermost entry point and exits at a real output — it copies a tree, spawns `make verify` or
`pytest`, runs a real `ruff`/`mypy`, builds a real environment, or drives a gate's `run()` over
a real filesystem. A test is unit when it exercises one function's logic over constructed input
with no process and no tree.

Read each test and decide. Do not classify by file name, by helper name, or by the table in
DEC-0029 — that table is the Lead's heuristic over call sites and is explicitly **not** the
classification. Where you disagree with it, say so in your report and say why; that is expected.

## Invariants this task must uphold
- **A marker only.** No test body is rewritten, renamed, split, merged or deleted. No assertion
  changes. If a test seems wrong, that is a finding for your report, not an edit.
- **The band does not move.** 40–60% stands. If your honest classification lands `tools` outside
  it, stop and report that — do not adjust a single marker to get back in. DEC-0029 is explicit
  that the fix would be tests, not markers.
- **`test_make_verify_over_the_real_tree_exits_zero` keeps asserting `returncode == 0`.**
- Do not touch `SPAWNS_A_RE_ENTERING_PROCESS` or the `spawns_harness` hook. `spawns_harness` and
  `integration` are different questions and a test may carry both.

## Files
Modify: `tools/tests/test_gates_static.py`, `tools/tests/test_gate_isolation.py`,
`tools/tests/test_gate_jurisdiction.py`, `tools/tests/test_gate_module_contract.py`,
`tools/tests/test_gate_placeholder.py`, `tools/tests/test_verify.py`,
`tools/tests/test_gate_test_discipline.py`, `tools/gates/readme.ai.md` (the Tests section states
the resulting split)
Forbidden: everything else. In particular `tools/gates/test_balance.py` — if the gate looks
wrong, that is a finding, not a fix.

## Tests
No new test. This task is classification of existing ones, and gate 15 is its own check: it
passes or it does not, over the real tree, in `make verify`.

## Acceptance
```
make verify                                        # exits 0, "9 gates registered, 0 failed"
uv run --group dev pytest tools/tests/ -q          # 65 passed
uv run --group dev python -c "from tools.gates import test_balance; print(test_balance.run().detail)"
```
Quote gate 15's per-module line verbatim in your report.

## Deliverables
The markers · `tools/gates/readme.ai.md` Tests section updated with the resulting split · a
completion report giving the final unit/integration counts, and naming every test where your
reading differed from DEC-0029's table, with the reason.

## If you hit an unresolved decision
OPEN decision record, stop, report. Take the **next free number** — check `decisions/INDEX.md`
first; DEC-0029 is taken.
