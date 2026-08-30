# T-0001a — Remove the invented registration path, make the runner survive a raising gate, write the module contract

Slice: S0.1 · Capability: P0 · Outcome: O1

## Prerequisites
T-0001, complete. Evidence: `make verify` exits 0 printing `0 gates registered, 0 failed`;
`uv run --group dev pytest tools/tests/ -q` → 6 passed.

## Why this task exists
T-0001's Review found three things. Two are defects in the code, one is a deliverable T-0001's
own Files list wrongly forbade. This task closes all three and nothing else.

1. **`--extra-gate` is a second registration path.** `tools/verify.py` ships a plugin loader —
   the `--extra-gate MODULE` flag, `load_gates()`, and the `GATES` module protocol — that no
   contract asked for. Its only consumer is the test file. It contradicts the `REGISTRY`
   docstring five lines above it ("the single place a gate is registered"), it contradicts
   T-0001's own invariant that registering a gate costs one `REGISTRY` entry plus one module,
   and it is a permanent public CLI surface that exists only for testability
   (`CLAUDE.md` §6: no configuration option nothing reads).
2. **A gate that raises kills the run.** `run_gates` calls `gate.run()` unguarded, so a gate
   whose tool is missing aborts the whole run and skips every remaining gate. That is exactly
   the "hides how much else is broken" failure T-0001's design note exists to prevent, arriving
   through the exception path instead of the `ok=False` path.
3. **`tools/readme.ai.md` does not exist.** It is required by `CLAUDE.md` §8, DoD §9.5 and
   harness gate 7, and T-0002 lists it in its *Context* — so T-0002 cannot start without it.

## Context — read these and nothing else
- `CLAUDE.md`
- `docs/process/readme-ai-convention.md`
- `docs/architecture/harness.md`
- `tools/verify.py`, `tools/tests/test_verify.py`, `Makefile`
- `decisions/DEC-0022-gates-ship-with-their-artifact.md`

## Contract

**Delete**, with no replacement surface: `GATES_ATTR`, `load_gates()`, the `--extra-gate`
argument, the `import importlib`, and `VERIFY_ARGS` from the `Makefile`. After this task
`main(argv)` accepts `--list` and nothing else, and `REGISTRY` is the only way a gate is
registered — as its docstring already claims.

**Keep** the `if __name__ == "__main__"` delegation to the imported module, and correct its
comment: the reason is no longer `isinstance`, it is that `python -m tools.verify` would
otherwise load this file twice under two names, so a gate module's `from tools.verify import
GateResult` would not name the class the runner is holding.

**Change `run_gates`** so a gate that raises is reported as a failing gate and the run
continues:

```python
def run_gates(gates: Sequence[Gate], out: TextIO) -> bool:
    """Run every gate in cost order, printing one line each. True only if all passed.

    A gate that raises is a failing gate, not a crashed run: its traceback becomes the
    detail. A runner that dies on the first broken gate hides how much else is broken.
    """
```

The raising gate's line must print `FAIL`, and its detail must carry the exception type, its
message, and the traceback — enough to fix it without re-running.

## Invariants this task must uphold
- **No new surface.** Nothing is added to `main()`, the `Makefile`, or `pyproject.toml` beyond
  what is named above. Removing the loader must not introduce a replacement for it.
- Registering a gate costs one `REGISTRY` entry plus one module. After this task that is true
  with no exception.
- Typed throughout. `uvx mypy --strict` over `tools/` clean, `uvx ruff check tools/` clean —
  including the two `FURB122` findings currently at `tools/verify.py:90` and `:106`.

## How the failure proof works now
T-0001 proved the runner can fail by injecting a gate through the loader. Prove it through the
**real registration path** instead: the integration test copies `Makefile`, `pyproject.toml` and
`tools/` into `tmp_path`, appends one literal `REGISTRY.append(Gate(...))` block to the copied
`tools/verify.py`, and runs `make verify` in that copy. That is the documented mechanism used
verbatim, it needs no production code, and it proves the real `Makefile` → real runner → real
registry → non-zero exit path end to end.

## Files
Create: `tools/readme.ai.md`
Modify: `tools/verify.py`, `tools/tests/test_verify.py`, `Makefile`
Forbidden: everything else. No `src/`. No `tools/gates/` — that is T-0002. No new dependency.

## Tests
Unit (4): cost ordering is respected; `--list` exits 0 and names every registered gate; a
`GateResult(ok=False)` with an empty detail is rejected at construction; **a gate whose `run`
raises is reported `FAIL` with the exception in its detail, and the gates after it still run.**
Integration (3): `make verify` over the real tree exits 0; the copied tree with one appended
`REGISTRY` entry exits non-zero; that output names the failing gate and prints the registered
count.
Mocking: none permitted. Invoke the real `make verify` via subprocess.
4/3 is 57% unit, inside the 40–60% band gate 15 will enforce at T-0007.

## `tools/readme.ai.md`
All nine sections of `docs/process/readme-ai-convention.md`, in order, describing `tools/` as it
actually is after this task. `Open questions` names `DEC-0023` as closed and gate 3 as the thing
that will close the raw-HTTP path at C1.1. Do not describe gates that do not exist yet.

## Acceptance
```
make verify                                    # exits 0, prints "0 gates registered, 0 failed"
python -m tools.verify --list                  # exits 0
python -m tools.verify --extra-gate x          # exits 2: the flag is gone
uv run --group dev pytest tools/tests/ -q      # 7 passed
uvx ruff check tools/                          # clean
uvx mypy --strict tools/                       # clean
```
Quote the actual output of every one of these in the completion report. Run them. The Review of
T-0001 found strong evidence its acceptance commands were never executed — filesystem timestamps
showed no `.pyc` and no environment in which `pytest` could have run — while the report quoted
output for all three. Quoting output you did not observe is the single worst thing a session here
can do: it defeats every other guard at once.

## Deliverables
Code · tests (4 unit / 3 integration) · `tools/readme.ai.md` · completion report per
`docs/process/definition-of-done.md`.

## If you hit an unresolved decision
Write `decisions/DEC-XXXX.md` with `Status: OPEN`, **stop, and report** — do not write the stub
and then finish the task anyway, which is what T-0001 did.
