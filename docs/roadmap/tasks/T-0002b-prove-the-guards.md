# T-0002b — Prove the harness's own guards, and stop concurrent runs corrupting each other

Slice: S0.1 · Capability: P0 · Outcome: O1

## Prerequisites
T-0002a, complete. Evidence: `make verify` prints each gate's summary line; a nested run's output
differs from a full run's; 16 tests, 0 skipped at the outermost run.

## Why this task exists
T-0002a added the mechanism DEC-0024 asked for. Review then established that **nothing proves it
works**, and reproduced each hole. This repository's whole thesis is that a guard which has never
been observed failing is not a guard (DEC-0016), and three of them are in that state.

**H1 — DEC-0024's mechanism is unproven.** Replace `_summary_line`'s body with `return ""` and the
full suite still reports `16 passed`, while `make verify` output goes back to byte-identical
between a full and a nested run. Confirmed independently by the Lead. One line restores the exact
silent green DEC-0024 was written to make impossible, and every test stays green.

**H2 — the guard proof detects only *unconditional* skips.** `test_nothing_is_skipped_without_the
_nesting_marker` runs its child with the marker removed, so `skipif` is False for every test by
construction. Put `@outermost_run_only` back on the ruff and mypy tests — the precise regression
T-0002a removed — and the guard still passes while a nested run skips 8 of 16. The skip set can
widen back to anything and nothing notices. `tools/tests/conftest.py` currently *claims* this is
"enforced by tests rather than remembered". It is not, and a docstring asserting a proof that does
not exist is worse than no docstring.

**H3 — a drifting deselect nodeid recurses without bound.** The guard deselects itself from its own
child by nodeid. `--deselect` with a non-matching id is silently ignored by pytest — exit 0, no
warning — so if the id ever drifts (parametrising the test, or losing the `[tool.pytest.ini_options]`
rootdir anchor), the child runs the guard, which spawns its own child, forever. Observed: nested
pytest processes climbing 8 → 18 over sixty seconds, terminated only by `kill -KILL`.

**H4 — concurrent runs corrupt each other.** `_planted` writes probe files to fixed paths in the
real tree (`tools/unused_import_probe.py` and friends). Two `make verify` runs at once — two agents,
a CI matrix, or one `diff <(make verify) <(make verify)` — delete each other's fixtures mid-test.
Observed: `FileNotFoundError` in `_planted`'s cleanup, two spurious failures.

## Context — read these and nothing else
- `CLAUDE.md`
- `decisions/DEC-0024-harness-tests-itself.md`
- `decisions/DEC-0016-harness-before-code.md`
- `docs/process/readme-ai-convention.md`
- `tools/gates/__init__.py`, `tools/verify.py`
- `tools/tests/conftest.py`, `tools/tests/test_verify.py`, `tools/tests/test_gates_static.py`
- `tools/readme.ai.md`

## Contract

**1. Prove H1.** A test that fails if `run_tools` stops reporting a successful command's summary.
Assert on `run_tools`'s real `GateResult` over a real succeeding command that its `detail` is
non-empty and carries that command's actual last output line. Your proof is only accepted if you
demonstrate it: stub `_summary_line` to `return ""`, show the suite now fails, revert, show it
passes. Both outputs go in the report.

**2. Prove H2.** A test that pins the skip set **by name**. Run a child with the marker set, collect
the node ids that skipped, and assert set equality against an explicit literal list of the six
tests that legitimately spawn a re-entering process. Widening or narrowing the set then fails,
naming the difference. Demonstrate it: add `@outermost_run_only` to the ruff test, show the failure
and its message, revert, show it passes.

**3. Close H3.** The guard's child invocation must assert its deselect actually took effect — the
child's summary must report exactly one deselected test. A drifting nodeid then fails the run in
seconds instead of forking without bound. Demonstrate with a deliberately stale nodeid that the
failure is now immediate; do **not** leave a test that spawns an unbounded chain if it regresses.

**4. Close H4.** Probe destinations must be unique per process, so concurrent runs cannot collide —
derive the filename from `os.getpid()` (this is test code; `tools/verify.py` and `tools/gates/`
still read no environment and gain no surface). The files must still land where the gates actually
scan, and `_planted`'s cleanup stays. Demonstrate: two `make verify` runs concurrently, both exit 0.

**5. Correct two false claims in prose.** `tools/tests/conftest.py`'s docstring says the decorator
placement is enforced by tests — true only once §2 lands, so make sure it is. `_summary_line`'s
docstring and `tools/readme.ai.md` say the retained line "carries the count of what was checked";
`ruff check` prints `All checks passed!` with no count, identically over the repo and over an empty
directory. Say what is actually true.

## Invariants this task must uphold
- **No production surface for tests.** `tools/verify.py` and `tools/gates/` read no environment
  variable, gain no flag, no config key. Only `tools/gates/__init__.py`'s docstring may change
  there, and only per §5.
- Every proof in this task is **demonstrated failing**, not asserted to work. That is the whole
  subject of the task.
- `ruff`, `mypy --strict` clean. Test balance inside 40–60%.

## Files
Modify: `tools/tests/conftest.py`, `tools/tests/test_verify.py`, `tools/tests/test_gates_static.py`,
`tools/gates/__init__.py` (docstring only), `tools/readme.ai.md`
Forbidden: everything else. No `src/`, no new dependency, no `pyproject.toml` change.

## Tests
New integration (3): the H1 proof, the H2 skip-set proof, the H4 concurrency proof.
Modify the existing guard test for §3.
Mocking: none.

## Acceptance
```
make verify                                     # exits 0
uv run --group dev pytest tools/tests/ -q       # all pass, 0 skipped
uvx --with pytest mypy --strict tools/          # clean
```
Plus the four demonstrations required by Contract §1–4: each showing the new proof **failing** when
its defect is reintroduced, and passing after revert. A completion report without those four
failure demonstrations is not a completion report — it is the claim this task exists to stop
accepting.

## Deliverables
Code · tests · `tools/readme.ai.md` updated · completion report per
`docs/process/definition-of-done.md`.

## If you hit an unresolved decision
Write `decisions/DEC-XXXX.md` with `Status: OPEN`, stop, and report.
