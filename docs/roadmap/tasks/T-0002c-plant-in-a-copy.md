# T-0002c — Remove the shared mutable tree, and prove DEC-0024 end to end

Slice: S0.1 · Capability: P0 · Outcome: O1

## Prerequisites
T-0002b, complete. Evidence: four guards demonstrated failing when their defects are
reintroduced; `make verify` exits 0 printing `19 passed`; two concurrent runs both exit 0.

## Why this task exists
This is the **last** task on the harness's own scaffolding. It closes the class of defect that
T-0002a and T-0002b each closed one instance of, rather than closing another instance.

**D1 — DEC-0024 is still defeatable with a fully green suite.** The behaviour is a chain: gate 14
→ `run_tools` → `_summary_line` → `run_gates` prints on PASS. T-0002b proved the middle. Nothing
enters at `make verify` and asserts the output, so discarding the detail in `tools/gates/tests.py`
makes a full run byte-identical to a nested one again while all 19 tests pass, ruff is clean and
mypy is clean. `CLAUDE.md` §7 requires every behaviour to have at least one test entering at the
outermost real entry point and exiting at the real output. The one behaviour DEC-0024 exists for
does not have one.

**D2 — planting probes in the real tree is the wrong shape, and pid-uniqueness only narrows it.**
Three concurrent `make verify` runs fail 6 of 12, cross-gate: one run's *lint* probe vanishing
mid-walk makes another run's *types* gate report
`mypy: error: Cannot read file 'tools/unused_import_probe_1377906.py'`. Reproduced by the Lead.
The same class also forced `ignore=TRANSIENT` onto `shutil.copytree`, left `test_concurrent_verify
_runs_do_not_collide` non-deterministic (one failure in ~30 solo runs), drops probe files in
`tools/` if a run is SIGKILLed, and accumulates one `__pycache__` entry per run without bound.

Every one of those is a symptom of tests mutating the tree they are being run from. **Stop doing
that.** The gate-rejection proofs must plant into a copied tree and run `make verify` there.

**D3 — narrowing the skip set still forks without bound.** T-0002b fast-failed the deselect-drift
vector only. Removing `@outermost_run_only` from a spawning test still climbs 7 → 35 processes in
30 s, killable only by process group. Fix the class, not the vector.

**D4 — three prose claims are false.** `tools/tests/test_verify.py`'s module docstring says "Six
unit tests … and four integration tests"; it holds 6 and 6. `tools/readme.ai.md` lists the H1 test
under "through a real subprocess — the real `Makefile`, the real tools, the real runner"; it goes
through none of them. And the readme's Open-questions paragraph bounding the concurrency residual
by fixture content is wrong, per D2.

## Context — read these and nothing else
- `CLAUDE.md`
- `decisions/DEC-0024-harness-tests-itself.md`
- `decisions/DEC-0016-harness-before-code.md`
- `docs/process/readme-ai-convention.md`
- `tools/verify.py`, `tools/gates/__init__.py`, `tools/gates/tests.py`
- `tools/tests/conftest.py`, `tools/tests/test_verify.py`, `tools/tests/test_gates_static.py`
- `tools/readme.ai.md`

## Contract

**1. One shared "tree copy" helper in `conftest.py`.** `tools/tests/test_verify.py` already copies
the tree for its failing-gate proof; `test_gates_static.py` plants into the real one. Unify: one
helper that copies `Makefile`, `pyproject.toml`, `uv.lock` and `tools/` into `tmp_path` and returns
its root. Both modules use it. It takes an optional edit to apply to the copy's `tools/verify.py`
(the existing `REGISTRY.clear()` + append case is one such edit).

**2. Every gate-rejection proof plants into a copy.** `test_lint_gate_fails_on_an_unused_import`,
`test_types_gate_fails_on_a_mismatched_annotation`, `test_tests_gate_fails_on_a_failing_test` and
the three `make verify` failure proofs write their bad fixture into the copied tree and run there.
Nothing under `tools/tests/` may create, modify or delete a file inside the repository's own
working tree, at any point, for any reason.

This is still a real end-to-end proof: a real `Makefile`, a real runner, real `ruff`/`mypy`/
`pytest`, a real bad fixture — it simply is not *this* checkout. Losing "the probe is scanned by
the repo's own gate" costs nothing, because the gate scans its own root either way.

Once this holds: delete `ignore=TRANSIENT` from the `copytree` call, and delete the pid suffixes —
both exist only to survive the shared tree. If either turns out to still be needed, that means §2
is incomplete; fix §2 rather than keeping them.

**3. `test_concurrent_verify_runs_do_not_collide` must be deterministic or gone.** With §2 there is
no shared mutable state left for it to detect, so prefer deleting it and saying why in the readme.
If you keep it, it must pass 20/20 and you must show the 20 runs. `CLAUDE.md` §7 forbids a test
that passes on ordering luck.

**4. Prove DEC-0024 end to end (D1).** One integration test that runs the **real `make verify`** in
a copied tree twice — once plainly, once with `CADGPT_NESTED_VERIFY=1` in the child environment —
and asserts the two outputs differ, and that the full run's gate 14 line carries a pytest summary.
Demonstrate it: edit the copy's `tools/gates/tests.py` to discard its success detail, show this
test failing, revert, show it passing. Both outputs in the report.

**5. Cap the depth for every vector (D3).** In `conftest.py`, read a depth counter from the
environment at import; the spawn helpers increment it in the child. Beyond depth 2, fail the
session immediately with a message naming the depth and the marker. This supersedes per-vector
fast-fails: any future skip-set mistake becomes a loud error in seconds instead of a fork bomb.
Demonstrate by removing `@outermost_run_only` from a spawning test: show the run failing fast, and
show `pgrep -fa pytest` finding nothing afterwards.

**6. Correct the three false prose claims (D4)**, and tighten `assert "1 deselected" in summary` —
it also matches `11 deselected`.

## Invariants this task must uphold
- **No production surface for tests.** `tools/verify.py` and `tools/gates/` read no environment
  variable and gain no flag or config key. Only docstrings may change there.
- **No test writes into the repository working tree.** This is the point of the task; it is also
  the acceptance check below.
- `ruff`, `mypy --strict` clean. Test balance inside 40–60%.

## Files
Modify: `tools/tests/conftest.py`, `tools/tests/test_verify.py`, `tools/tests/test_gates_static.py`,
`tools/gates/__init__.py` (docstring only), `tools/readme.ai.md`
Forbidden: everything else. No `src/`, no new dependency, no `pyproject.toml` change.

## Acceptance
```
make verify                                     # exits 0
uv run --group dev pytest tools/tests/ -q       # all pass, 0 skipped
uvx --with pytest mypy --strict tools/          # clean

# three concurrent runs, all exit 0 — the case that fails 6/12 today
for i in 1 2 3; do ( make verify >/tmp/t3-$i.log 2>&1; echo "run$i exit=$?" ) & done; wait

# the tree is untouched by its own suite
git status --porcelain    # empty, before and after a full pytest run
```
Quote all of it, plus the two demonstrations from §4 and §5.

## Deliverables
Code · tests · `tools/readme.ai.md` updated · completion report per
`docs/process/definition-of-done.md`.

## If you hit an unresolved decision
Write `decisions/DEC-XXXX.md` with `Status: OPEN`, stop, and report.
