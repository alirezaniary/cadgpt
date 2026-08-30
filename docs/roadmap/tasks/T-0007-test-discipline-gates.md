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
- `tools/gates/__init__.py` — `REPO_ROOT`, `run_tools`, and the `GateResult` import convention
  (`TYPE_CHECKING` only at module level, imported inside the function body; `tools.verify` imports
  this package to build `REGISTRY`, so a module-level import back is a cycle). Binding on both new
  gate modules.
- `tools/tests/conftest.py` — **the file that decides whether gate 16 is safe to write.** Gate 16
  spawns `pytest`, which re-collects this suite, which contains tests that spawn `make verify`.
  `copied_tree`, `only_gate`, `outermost_run_only`, `depth_zero_only`, `MAX_DEPTH` and
  `SPAWNS_A_RE_ENTERING_PROCESS` are the existing, and only permitted, recursion-safety
  mechanism. Do not invent a second one; `tools/gates/readme.ai.md` §Must not depend on forbids it.
- `pyproject.toml` — you are adding a `markers` entry to `[tool.pytest.ini_options]`, which has
  none today. Read its current shape rather than assuming it.
- `decisions/DEC-0027-gate-16-scope.md` — what gate 16 runs, what it deliberately does not, and
  why. **Binding.** It settles a question you would otherwise have to decide, and you may not.

This list was corrected after a first dispatch stopped and reported it as incomplete. That was the
correct behaviour and the spec was wrong, not the session.

## Contract
```python
# tools/gates/test_balance.py
def run() -> GateResult:
    """Per module with tests, count unit vs integration and fail outside 40-60%.
    A module with fewer than 4 tests is reported but not failed — a ratio over 3 tests
    is noise. detail is a per-module table, printed whether or not it fails."""

# tools/gates/determinism.py
def run() -> GateResult:
    """Run the suite twice — different PYTHONHASHSEED, different -p randomly seed, and
    `-m "not spawns_harness"` — and fail if the pass/fail set differs.
    detail names the tests that disagreed on failure, and on success reports how many
    tests ran, the two seeds, and how many were deselected (DEC-0027 §4)."""
```

Classification of unit vs integration must be **explicit**, not inferred from filenames. Use a
pytest marker (`@pytest.mark.integration`); an unmarked test counts as unit. Inferring from path
or name means the gate silently miscounts the moment someone names a file differently.

## Invariants this task must uphold
- 40–60%, per `docs/process/testing-strategy.md`. Do not widen the band to make the current tree
  pass — if `tools/` is outside it, that is a finding to report, and the fix is tests, not a
  wider band.
- **DEC-0027 governs gate 16's scope and is not yours to revisit.** Read it first. It settles
  what the suite-twice run covers, why the eight harness-spawning tests are deselected, that
  `pytest-randomly` is added to the `dev` group by decision, that `addopts` must carry
  `-p no:randomly` so every other run is unchanged, and that the gate reports its deselected
  count on pass as well as fail. The measured numbers behind it are in the record; do not
  re-measure to decide, only to confirm.
- Gate 16 is cost tier 2 under DEC-0027 (two ~24s runs, not two ~258s ones). Give it a cost
  that puts it after gate 15 and before gate 14 in cost order, and say in your report what
  `make verify` actually took.

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
Modify:
- `tools/verify.py` — registration, two entries
- `pyproject.toml` — the `integration` and `spawns_harness` markers, `pytest-randomly` in the
  `dev` group, and `addopts = ["-p", "no:randomly"]` (DEC-0027 §3)
- `tools/tests/conftest.py` — `@pytest.mark.spawns_harness` on exactly the eight tests
  `SPAWNS_A_RE_ENTERING_PROCESS` names; that frozenset stays the one hand-written literal
- `tools/tests/test_verify.py` — `test_only_the_spawning_tests_skip_one_level_down` gains the
  assertion that the `spawns_harness`-marked node ids equal `SPAWNS_A_RE_ENTERING_PROCESS`
  (DEC-0027 §2). Do not change what that test already asserts.
- `tools/gates/readme.ai.md` — both gates' public surface, their tests, their invariants
- `tools/readme.ai.md` — the `REGISTRY` table gains two rows; that file stops at the runner

Forbidden: everything else. In particular, do not touch any other test's body to make a balance
number come out right.

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

Run `make verify` **once**, at the end. It is 5m31s before your change and DEC-0027 expects
roughly 6m20s after it. Iterate with `uv run --group dev pytest tools/tests/ -q` and by calling
each gate's `run()` directly.
Report the full `make verify` output. **This is P0's completion evidence** — nine gates, each
with a committed proof it can fail.

## Deliverables
Code · tests (4/4) · `tools/readme.ai.md` updated · completion report stating P0 complete and
the balance table for `tools/`.

## If you hit an unresolved decision
OPEN decision record, stop, report.
