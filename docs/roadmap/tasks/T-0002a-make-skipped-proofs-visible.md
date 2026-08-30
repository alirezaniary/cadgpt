# T-0002a — Make a gate's skipped proofs visible in `make verify` output

Slice: S0.1 · Capability: P0 · Outcome: O1

## Prerequisites
T-0002, complete. Evidence: `make verify` exits 0 printing `3 gates registered, 0 failed`;
`uv run --group dev pytest tools/tests/ -q` → 13 passed; all three gates observed rejecting.

## Objective
Implement DEC-0024. Today a `make verify` that skipped every one of its failure proofs is
byte-identical to one that ran them:

```
$ env CADGPT_NESTED_VERIFY=1 make verify
PASS  gate 1  format-and-lint
PASS  gate 2  types
PASS  gate 14  tests
3 gates registered, 0 failed          exit 0, 0.98 s — seven proofs skipped, nothing said so
```

After this task that run must announce its skips. Read `decisions/DEC-0024-harness-tests-itself.md`
first; it is the whole rationale and it is settled.

## Context — read these and nothing else
- `CLAUDE.md`
- `decisions/DEC-0024-harness-tests-itself.md`
- `decisions/DEC-0016-harness-before-code.md`
- `docs/architecture/harness.md`
- `docs/process/readme-ai-convention.md`
- `tools/verify.py`, `tools/gates/__init__.py`, `tools/gates/tests.py`
- `tools/tests/test_verify.py`, `tools/tests/test_gates_static.py`
- `tools/readme.ai.md`

## Contract

**1. `run_gates` prints a non-empty detail on PASS as well as FAIL.** One condition changes: the
detail lines are written whenever `result.detail` is non-empty, not only when `not result.ok`.
Indentation and the failure path stay exactly as they are.

**2. `run_tools` reports on success.** It currently discards a succeeding command's output
entirely. It must return, as `detail`, the **last non-empty line** of each successful command's
combined output — the summary line every one of these tools ends with. Failure behaviour is
unchanged: the full verbatim output, as now. Gate 1 runs two commands, so its success detail is
two lines; that is correct and wanted.

**3. Narrow the skip set, and name it once.** `NESTED = "CADGPT_NESTED_VERIFY"` is currently a
duplicated string literal in two test modules, and the marker is applied by two different
mechanisms (an autouse `monkeypatch.setenv` fixture in one, an explicit per-call `env=` in the
other). Create `tools/tests/conftest.py` holding the marker name, one `outermost_run_only`
decorator, and one shared helper for spawning a child with the marker set. Both test modules use
those and define neither themselves.

The decorator goes on **only** the tests that spawn a process which re-enters the harness — those
that run `make verify` or `pytest`. It must come off
`test_lint_gate_fails_on_an_unused_import` and `test_types_gate_fails_on_a_mismatched_annotation`,
which spawn `ruff` and `mypy` and cannot recurse; they are over-skipped today and their skip
reason states something untrue about them.

**4. Prove the guard.** A test asserting that with the marker absent from the environment, no test
in `tools/tests/` is skipped — collect and run the suite in a subprocess with the variable removed
and assert a zero skip count. DEC-0016 makes a guard's own proof mandatory; this guard has none.

## Invariants this task must uphold
- **No production surface for tests.** `tools/verify.py` and `tools/gates/` must not read
  `CADGPT_NESTED_VERIFY` or any other test marker, must gain no flag, no env read, no config key.
  T-0001a removed an injection path deliberately; it does not come back through a conftest.
- A gate that has nothing to say on success returns an empty detail and prints nothing. Clean runs
  stay readable.
- `ruff` and `mypy --strict` clean; RUF100 stays enabled alongside the real selection.
- Test balance stays inside 40–60%.

## Files
Create: `tools/tests/conftest.py`
Modify: `tools/verify.py`, `tools/gates/__init__.py`, `tools/tests/test_verify.py`,
`tools/tests/test_gates_static.py`, `tools/readme.ai.md`
Forbidden: everything else. No `src/`. No new dependency. `pyproject.toml` is not touched.

## Tests
Adjust the existing assertions that pin `make verify` output — several will now see extra
lines, and that is the point of the task, not a regression.
New unit (2): `run_gates` prints a passing gate's non-empty detail, and prints nothing extra for
a passing gate whose detail is empty.
New integration (1): the guard proof from Contract §4.
Mocking: none.

## Acceptance
```
make verify                                     # exits 0; gate lines now carry summary lines
env CADGPT_NESTED_VERIFY=1 make verify          # exits 0 and its output DIFFERS, showing skips
uv run --group dev pytest tools/tests/ -q       # all pass, 0 skipped
uvx --with pytest mypy --strict tools/          # clean
```
Quote all four verbatim. For the second, also show the `diff` against the first — proving the two
are no longer identical is the deliverable, so show the proof, not a claim about it.

## Deliverables
Code · tests · `tools/readme.ai.md` updated · completion report per
`docs/process/definition-of-done.md`.

## If you hit an unresolved decision
Write `decisions/DEC-XXXX.md` with `Status: OPEN`, stop, and report.
