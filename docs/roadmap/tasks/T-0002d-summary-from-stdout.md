# T-0002d — Stop tool chatter displacing a gate's summary, and make the copied-tree proofs affordable

Slice: S0.1 · Capability: P0 · Outcome: O1

## Prerequisites
T-0002c, complete. Evidence: `make verify` exits 0, 19 passed, 0 skipped; `git status --porcelain`
byte-identical across a full suite run; three concurrent runs all exit 0.

## Why this task exists
Review of T-0002c confirmed the end-to-end proof is non-vacuous and the depth cap bounds every
vector. It found two things left.

**E1 — any `uv` chatter silently becomes a gate's summary line.** `run_tools` builds
`output = completed.stdout + completed.stderr` and `_summary_line` takes the **last** non-empty
line, so anything uv writes to stderr displaces the tool's own summary:

```
RUN 1 (cold venv) gate 1 detail: 'Installed 12 packages in 23ms\n9 files already formatted'
RUN 2 (warm venv) gate 1 detail: 'All checks passed!\n9 files already formatted'
```

That summary line is the whole mechanism DEC-0024 exists for, so this is a live
`Reopens if` condition on that decision — "gate 14 ever stops being able to report a summary".
Dropping `VIRTUAL_ENV` from child environments removed one trigger; the class remains, and the
next uv warning re-opens the hole. It also makes one assertion in
`test_a_full_run_is_visibly_different_from_a_nested_one` — `assert full.stdout != nested.stdout` —
true by construction on a cold copy, so it can never fail and carries no signal.

**E2 — `make verify` costs 2m28s, up from ~17s.** Eleven tests copy the tree and run a real
`make verify` inside it, and each of those copies runs its **whole** registry — ruff and mypy and
pytest — when the proof only concerns one gate.

## Context — read these and nothing else
- `CLAUDE.md`
- `decisions/DEC-0024-harness-tests-itself.md`
- `docs/process/readme-ai-convention.md`
- `tools/verify.py`, `tools/gates/__init__.py`
- `tools/tests/conftest.py`, `tools/tests/test_verify.py`, `tools/tests/test_gates_static.py`
- `tools/tests/badfixtures/` (all files)
- `tools/readme.ai.md`

## Contract

**1. A success summary comes from the tool's own stdout.** In `run_tools`, take the summary line
from `completed.stdout` alone. `ruff`, `mypy` and `pytest` all write their summary to stdout;
`uv`'s own chatter goes to stderr and is not the tool's report. **Failure detail is unchanged** —
it keeps `stdout + stderr`, unedited, because on a failure you want everything.

Prove it: make a gate's command emit a line on stderr after its real summary, show that the
summary printed by `make verify` is still the tool's own line and not the stderr line. Quote it.

**2. Each copied-tree proof registers only the gate it proves.** The copy helper already accepts an
edit to the copied `tools/verify.py`; the failing-gate proof already uses `REGISTRY.clear()`.
Extend that: `test_make_verify_fails_and_names_gate_1` registers gate 1 in its copy and nothing
else, gate 2's proof registers gate 2, gate 14's registers gate 14, and
`test_a_full_run_is_visibly_different_from_a_nested_one` registers gate 14 only — it is a claim
about gate 14's line, and the other two gates contribute nothing to it.

`test_make_verify_over_the_real_tree_exits_zero` keeps the full registry: it is the one test whose
subject *is* the whole registry.

Report gate 14's wall time before and after. This is a cost change, not a behaviour change: every
proof must still assert exactly what it asserted before, and the suite must still catch the
sabotages — re-run the two demonstrations T-0002c reported (§4's `tools/gates/tests.py` returning
an empty success detail, §5's marker removal) and show they still fail.

**3. Correct three overstated claims.** `tools/tests/conftest.py`'s module docstring and
`tools/readme.ai.md` both say a mistake in a skip set surfaces as a named error in seconds. That is
true for four of the eight vectors. The three `test_make_verify_fails_and_names_gate_*` proofs and
`test_tests_gate_fails_on_a_failing_test` **pass** with their marker removed, because they assert
on the depth-1 run's own output, which is there regardless of what happens deeper. They are
bounded, not caught. Say that.

Also: `tools/tests/badfixtures/assertion_that_fails.py` and `.../unused_import.py` still say the
suite "copies it … runs the gate, and removes it again". Nothing is removed now — the copy goes
with `tmp_path`.

**4. Guard the depth variable.** `int(os.environ.get(DEPTH, "0"))` raises a bare `ValueError`
traceback if the variable is ever non-numeric. Treat an unparseable value as the error it is, with
the same explanatory message the cap raises.

## Invariants this task must uphold
- **No production surface for tests.** `tools/verify.py` and `tools/gates/` read no environment
  variable and gain no flag or config key.
- **No test writes into the repository working tree.** Still the central invariant; check it the
  same way, `git status --porcelain` byte-identical across a full run.
- Every existing proof keeps proving what it proved. This task must not weaken a single assertion.
- `ruff`, `mypy --strict` clean. Test balance inside 40–60%.

## Files
Modify: `tools/gates/__init__.py`, `tools/tests/conftest.py`, `tools/tests/test_verify.py`,
`tools/tests/test_gates_static.py`, `tools/tests/badfixtures/assertion_that_fails.py`,
`tools/tests/badfixtures/unused_import.py`, `tools/readme.ai.md`
Forbidden: everything else. No `src/`, no new dependency, no `pyproject.toml` change.

## Acceptance
```
make verify                                     # exits 0; report its wall time
uv run --group dev pytest tools/tests/ -q       # all pass, 0 skipped
uvx --with pytest mypy --strict tools/          # clean
git status --porcelain                          # identical before and after a full pytest run
```
Plus: the §1 stderr demonstration, gate 14's before/after wall time, and the two re-run sabotage
demonstrations from §2.

## Deliverables
Code · tests · `tools/readme.ai.md` updated · completion report per
`docs/process/definition-of-done.md`.

## If you hit an unresolved decision
Write `decisions/DEC-XXXX.md` with `Status: OPEN`, stop, and report.
