# T-0007 — Test balance and determinism (gates 15 and 16)

Slice: S0.5 · Capability: P0 · Outcome: O1

## Prerequisites
| Requires | Evidence |
| --- | --- |
| T-0006 | `make verify` exits 0 and prints "7 gates registered" |

## Objective
The two gates that guard the test policy itself. Everything else in the harness assumes the
suite means something; these two are why it does.

## Context — read these and nothing else
- `CLAUDE.md`
- `docs/process/testing-strategy.md`
- `decisions/DEC-0010-test-policy.md`
- `tools/verify.py`, `tools/gates/module_contract.py` (shape reference)
- `tools/gates/readme.ai.md` — the contract you are extending. `tools/gates/` is a module in its
  own right (DEC-0026, closed after this spec was written); its `readme.ai.md` is where a gate's
  public surface is documented, **not** `tools/readme.ai.md`.

## Contract
```python
# tools/gates/test_balance.py
def run() -> GateResult:
    """Per module with tests, count unit vs integration and fail outside 40-60%.
    A module with fewer than 4 tests is reported but not failed — a ratio over 3 tests
    is noise. detail is a per-module table, printed whether or not it fails."""

# tools/gates/determinism.py
def run() -> GateResult:
    """Run the suite twice with different PYTHONHASHSEED and different -p no:randomly
    ordering, and fail if the pass/fail set differs.
    detail names the tests that disagreed."""
```

Classification of unit vs integration must be **explicit**, not inferred from filenames. Use a
pytest marker (`@pytest.mark.integration`); an unmarked test counts as unit. Inferring from path
or name means the gate silently miscounts the moment someone names a file differently.

## Invariants this task must uphold
- 40–60%, per `docs/process/testing-strategy.md`. Do not widen the band to make the current tree
  pass — if `tools/` is outside it, that is a finding to report, and the fix is tests, not a
  wider band.
- Determinism runs the suite twice. cost tier 3, and it must be last in cost order.

**Classification is load-bearing, and `tools/` is already borderline.** The counts below are from
T-0002c and predate both T-0004/5/6 and the DEC-0026 fix, which together added tests; recount
rather than trusting them. The *shape* of the problem is what matters and has not changed. Review
of T-0002c found that `tools/tests/` reports 9 unit / 10 integration = 47% only because three
tests in
`test_gates_static.py` are counted as unit while each copies a tree to disk and spawns real
ruff/mypy/pytest. Under `CLAUDE.md` §7's "behaviour crosses layers" reading they are integration,
which gives 6/19 = 32% and puts the module **below** the band on the day this gate ships. Decide
the rule by what the marker says, not by what keeps the existing tree green, and if `tools/`
fails on arrival then report that as the gate working — do not tune the rule until it passes.

## Files
Create: `tools/gates/test_balance.py`, `tools/gates/determinism.py`,
`tools/tests/test_gate_test_discipline.py`
Modify: `tools/verify.py` (registration), `pyproject.toml` (register the `integration` marker),
`tools/gates/readme.ai.md` (both gates' public surface, their tests, their invariants),
`tools/readme.ai.md` (the `REGISTRY` table gains two rows — that file stops at the runner)
Forbidden: everything else.

Note on gate 7, which now runs over your work: `tools/gates/` is a module directory and both new
files land inside it, so its `readme.ai.md` must stay conforming — nine sections, in order, none
empty — or `make verify` fails on your own change. `tools/tests/` is not a module and needs
nothing.

## Tests
Unit (4): a 5-unit/0-integration module fails; a 3/3 module passes; a 2-test module is reported
not failed; the per-module table is produced even on success.
Integration (4): a test whose result depends on hash seed makes determinism fail and is named;
a stable suite passes; the real tree passes both gates; `make verify` prints nine registered
gates.
Mocking: none.

## Acceptance
```
make verify                      # exits 0, prints "9 gates registered"
python -m tools.verify --list    # all nine, in cost order
uv run --group dev pytest tools/tests/ -q
```
Report the full `make verify` output. **This is P0's completion evidence** — nine gates, each
with a committed proof it can fail.

## Deliverables
Code · tests (4/4) · `tools/readme.ai.md` updated · completion report stating P0 complete and
the balance table for `tools/`.

## If you hit an unresolved decision
OPEN decision record, stop, report.
