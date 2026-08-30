# T-0008 — A scanning gate says what it scanned, and fails when it scanned nothing

Slice: S0.5 · Capability: P0 · Outcome: O1

## Prerequisites
| Requires | Evidence |
| --- | --- |
| T-0007a | `make verify` exits 0, "9 gates registered, 0 failed" |
| The P0 review | `REVIEW-harness-p0.md` findings C1, H1, M1 |

## Objective
`REVIEW-harness-p0.md` C1, reproduced by a real run: gate 15's walk was made to find nothing,
it returned `GateResult(ok=True, detail='')`, and the entire suite stayed green. Gates 5, 6 and
7 have the same shape. A gate that scanned nothing is byte-identical to a gate that scanned
everything.

This is under DEC-0025 §1's carve-out — a harness finding is recorded rather than worked
*unless* it lets a product gate pass while the invariant it guards is violated. Gate 5 guards
I4. It qualifies.

Close C1, H1 and M1. Nothing else.

## Context — read these and nothing else
- `CLAUDE.md`
- `REVIEW-harness-p0.md` — findings C1, H1, M1 are the specification; read their evidence
- `decisions/DEC-0024-harness-tests-itself.md` — the principle being extended
- `decisions/DEC-0027-gate-16-scope.md` — §4 is what M1 undermines
- `tools/verify.py`
- `tools/gates/jurisdiction.py`, `placeholder.py`, `module_contract.py`, `test_balance.py`,
  `determinism.py`
- `tools/gates/readme.ai.md`, `tools/readme.ai.md`
- `tools/tests/conftest.py` — `copied_tree`, `only_gate`, and the recursion rules
- `tools/tests/test_gate_module_contract.py` — the rejection-proof pattern to copy

## Contract

**C1 — every scanning gate reports its coverage and fails closed on an empty scan.**

Gates 5, 6, 7 and 15 gain a success detail naming what they scanned:

```
gate 5   "<n> files scanned under tools/"          (src/ named too, once it exists)
gate 6   "<n> files scanned under tools/"
gate 7   "<n> module directories checked"
gate 15  the per-module table it already prints (already compliant)
```

A gate whose scan roots exist but which found **zero** subjects returns `ok=False`, saying so.
A scan root that does not exist is not zero subjects — `src/` is legitimately absent at P0 and
must stay a clean pass. That distinction is the whole of this change; get it wrong in the
permissive direction and the gate is exactly as blind as before.

Gate 4 already fails closed on a proof it could not run. This is the same rule for a scan that
did not happen.

**M1 — `determinism._deselected_count` stops conflating zero with unknown.**
Return `int | None`; `None` when the summary line did not match. `verdict` renders it as
`unknown` and returns `ok=False` — a gate that cannot say what it skipped has not established
determinism over a known set.

**H1 — gates 15 and 16 get the rejection proof every other gate has.**
Two tests in the existing pattern: `copied_tree` with `only_gate(15)` and a planted skewed
module; `copied_tree` with `only_gate(16)` and a planted hash-seed-dependent test. Each asserts
`FAIL  gate N` in a real `make verify`'s stdout and a non-zero exit.

## Invariants this task must uphold
- **A gate reads no environment variable and takes no flag.** The nesting markers are a
  property of the tests (`tools/tests/conftest.py`); `tools/verify.py` and `tools/gates/` do
  not read them and must not start.
- **`src/` absent stays a clean pass.** There is no `src/` at P0. A gate that fails because
  `src/` is missing breaks every other proof in the suite.
- **No gate imports the test suite.** `determinism.py`'s docstring already explains why it does
  not import `SPAWNS_A_RE_ENTERING_PROCESS`; that holds.
- Do not touch the 40–60% band, `SPAWNS_A_RE_ENTERING_PROCESS`, or any existing test's body.

## Files
Create: nothing.
Modify: `tools/gates/jurisdiction.py`, `tools/gates/placeholder.py`,
`tools/gates/module_contract.py`, `tools/gates/determinism.py`,
`tools/tests/test_gate_jurisdiction.py`, `tools/tests/test_gate_placeholder.py`,
`tools/tests/test_gate_module_contract.py`, `tools/tests/test_gate_test_discipline.py`,
`tools/gates/readme.ai.md`, `tools/readme.ai.md`
Forbidden: everything else. In particular `tools/verify.py` — the runner already prints a
non-empty detail on PASS; if it did not, that would be a finding, not an edit.

**`tools/readme.ai.md` carries the paragraph this task disproves** — the one arguing an empty
detail is "the honest report" because there is "no partial-coverage question for a full-tree
`ast`/filesystem scan." Delete it and say what replaced it. Leaving it is shipping a document
that contradicts the code.

## Tests
Unit: an empty scan is `ok=False` for each of gates 5, 6, 7; a missing `src/` is still a clean
pass; `_deselected_count` returns `None` on an unmatched summary and `verdict` fails on it.
Integration: the two H1 rejection proofs.
Mocking: none.

## Acceptance
```
env -u CADGPT_NESTED_VERIFY -u CADGPT_VERIFY_DEPTH make verify   # exits 0, 9 gates, 0 failed
uv run --group dev pytest tools/tests/ -q
```
Quote every gate's success detail line from the `make verify` output. Confirm gate 14's line
shows all tests with **none skipped** — if it says "skipped", the run was nested and the
evidence is not from a real depth-0 run.

## Deliverables
Code · tests · both `readme.ai.md` files updated, including the deleted paragraph · a
completion report quoting the new coverage lines.

## If you hit an unresolved decision
OPEN decision record, next free number from `decisions/INDEX.md`, stop, report.
