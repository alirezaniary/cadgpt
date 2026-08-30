# readme.ai.md — tools/

## Purpose
`tools/` is the verification harness: the runner behind `make verify`, which is the whole
quality interface of this repository (`CLAUDE.md` §3 and §9). It owns the *mechanism* by
which build gates are registered, ordered, run and reported, and the gates themselves.

`tools/verify.py` is the mechanism and contains no check of its own. Every check lives in
one module under `tools/gates/`, exposing `run() -> GateResult`, plus one entry in
`REGISTRY`. A gate is added by the task that introduces the artefact type it guards, in
that same task (DEC-0022), with a test proving it can reject (DEC-0016).

Three of the sixteen gates in `docs/architecture/harness.md` are registered today —
1 (lint), 2 (types) and 14 (tests). `make verify` prints how many, so the harness's own
coverage is visible rather than assumed — and each gate prints its tool's own summary
line, so coverage *inside* a gate is visible on the same terms (DEC-0024). For `mypy` and
`pytest` that line is a count of what was checked. For `ruff check` it is `All checks
passed!`, which is the same string over this repository and over an empty directory and
says nothing about how much was looked at; gate 1's coverage is not visible this way and
is not claimed to be.

No gate re-implements a check. Each wraps an inherited tool (`CLAUDE.md` §6) and returns
the tool's own output unedited: the agent reading a failing `make verify` needs the real
message, not a summary of it.

It is **not** part of the product. Nothing under `src/` may import it, and it ships in no
distribution.

## Context
Outside every bounded context in `docs/ddd/03-bounded-contexts.md`. `tools/` is build
infrastructure, not domain code, and models nothing in the problem space.

Subdomain: **generic**. A gate registry has no competitive value; it exists so the other
subdomains can be checked mechanically.

## Contract
The public surface of `tools.verify`. Anything not listed here is internal.

- `GateResult(ok: bool, detail: str)` — frozen dataclass. The outcome of one gate.
  Raises `ValueError` at construction when `ok is False` and `detail` is blank: a failure
  that does not say what failed is not a usable failure.
- `Gate(number: int, name: str, cost: int, run: Callable[[], GateResult])` — frozen
  dataclass. One build guard. `number` is stable and matches the table in
  `docs/architecture/harness.md`. `cost` is 1 (seconds), 2 (tens of seconds) or 3 (minutes).
  `run` takes no arguments and returns a `GateResult`.
- `REGISTRY: list[Gate]` — the single place a gate is registered. There is no other
  registration path, no plugin loader and no injection flag. It currently holds:

  | # | name | cost | module |
  | --- | --- | --- | --- |
  | 1 | `format-and-lint` | 1 | `tools/gates/lint.py` |
  | 2 | `types` | 2 | `tools/gates/types.py` |
  | 14 | `tests` | 3 | `tools/gates/tests.py` |

- `in_cost_order(gates: Sequence[Gate]) -> list[Gate]` — cheapest first, ties broken by gate
  number so a run is deterministic.
- `write_listing(gates: Sequence[Gate], out: TextIO) -> None` — prints one line per gate and
  then `"<n> gates registered"`, running nothing.
- `run_gates(gates: Sequence[Gate], out: TextIO) -> bool` — runs every gate in cost order,
  prints `PASS`/`FAIL` and then, indented by eight spaces, the gate's `detail` whenever that
  detail is non-empty — **on `PASS` as well as `FAIL`** (DEC-0024) — then
  `"<n> gates registered, <m> failed"`. Returns `True` only if every gate passed. Raises
  nothing: a gate that raises is reported `FAIL` with its traceback as the detail, and the
  remaining gates still run. `KeyboardInterrupt` and `SystemExit` propagate — those are the
  operator stopping the run, not a gate reporting a defect.
- `main(argv: list[str]) -> int` — the CLI. Accepts `--list` and nothing else. `--list`
  writes the listing and returns 0; otherwise runs the registry and returns 0 or 1.
  Returns 2 via `argparse` on an unrecognised argument.

The public surface of `tools.gates`:

- `run_tools(commands: Sequence[Sequence[str]]) -> GateResult` — runs each command through
  `uv run --group dev` from the repository root and fails if any exited non-zero. Every
  command runs even after one has failed. The detail of a failure is the invocation, the
  exit code and the tool's own stdout and stderr, unedited. The detail of a success is one
  line per command: that command's **last non-empty output line**. For `mypy`
  (`Success: no issues found in N source files`) and `pytest` (`N passed`) that line
  carries a count of what was checked; for `ruff check` it is `All checks passed!`, a
  constant that carries no count. What the line is reliably good for is making one run
  *differ* from another — a gate 14 that skipped its proofs reports a different line from
  one that ran them (DEC-0024) — not for reading gate 1's coverage off. A command that
  printed nothing contributes no line, so a gate with nothing to report stays silent. Gate
  1 runs two commands and so reports two lines.
- `lint.run() -> GateResult` — gate 1. `ruff check .` and `ruff format --check .`. A tree
  can satisfy either half while failing the other, so both run.
- `types.run() -> GateResult` — gate 2. `mypy --strict tools/`. The task that creates the
  first `src/` package extends the paths, in that same task.
- `tests.run() -> GateResult` — gate 14. `pytest` with no path, so it collects whatever the
  repository holds rather than a list that has to be remembered.

Rule selection, line length and the exclusions for `ruff` and `mypy` are configured in
`pyproject.toml` and nowhere else — one place, no per-tool config files. The selection
includes `RUF100` (unused `noqa`) **alongside** the real rule set, because `CLAUDE.md`
forbids suppressing a warning, so every surviving `noqa` must be load-bearing. `RUF100`
selected on its own reports every other rule as non-enabled and so calls live suppressions
dead; it is only meaningful next to the rules it is checking against.

## Invariants enforced here
None from `docs/ddd/04-aggregates-and-invariants.md`: `tools/` is outside the domain model
and owns no domain aggregate.

Three local invariants of the harness itself are enforced here and are not re-checked by
callers:

- **A failing gate always carries a detail.** `GateResult.__post_init__`
  (`tools/verify.py`) — a gate cannot construct a silent failure.
- **Every registered gate runs, whatever any other gate does.** `run_gates`
  (`tools/verify.py`) — the `try`/`except Exception` around `gate.run()` means one broken
  gate cannot hide how much else is broken.
- **A gate reports its tool verbatim.** `run_tools` (`tools/gates/__init__.py`) — the
  failure detail is the tool's own stdout and stderr, never a summary of them.
- **A gate that checked less than it was asked to says so.** `run_gates`
  (`tools/verify.py`) prints a non-empty detail on `PASS`, and `run_tools`
  (`tools/gates/__init__.py`) makes a succeeding tool's own summary line that detail
  (DEC-0024). A `make verify` whose gate 14 skipped tests is therefore not byte-identical
  to one that ran them. Both halves are proven, not asserted:
  `test_a_succeeding_command_reports_its_own_last_output_line` runs a real command through
  the real `run_tools` and fails if the surviving line is ever dropped, which is the hole
  T-0002b closed — one line of `_summary_line` restored the byte-identical silent green
  while every other test stayed green.

## Depends on
`tools/verify.py` imports the Python standard library only: `argparse` (the CLI),
`dataclasses` (the two value objects), `traceback` (the detail of a raising gate), `sys`,
`collections.abc`, `typing` — plus `tools.gates`, which is stdlib-only too (`subprocess`,
`pathlib`).

Nothing third-party is **imported**, on purpose. The gates reach their tools by
`subprocess`, through `uv run --group dev`, at the moment the gate runs. So a missing or
broken toolchain surfaces as *that gate* failing with the real error, not as an import
error before any gate runs. `ruff`, `mypy` and `pytest` are declared in the `dev`
dependency group in `pyproject.toml` (DEC-0005 settled that these three are the static
enforcement layer).

`uvx` is not usable and must not be substituted: it builds an isolated environment with no
dev dependencies, so gate 2 reports `pytest` as a missing library stub for every test
module that imports it, and gate 14 would have no `pytest` at all.

`tools/gates/lint.py`, `types.py` and `tests.py` import `GateResult` under
`TYPE_CHECKING` only, and `run_tools` imports it inside the function body: `tools.verify`
imports `tools.gates` to build `REGISTRY`, so a module-level import back would be a cycle.

Tests additionally use `pytest` (dev group) and invoke `make` and the real runner through
`subprocess`.

## Must not depend on
- **Anything under `src/`.** The harness checks the product; a harness importing the thing
  it checks can be broken by the same defect it is meant to catch.
- **Any third-party package at import time.** `python -m tools.verify` must import on a
  clean checkout with nothing installed.
- **Any inference client or model SDK** (I1, I2) — as for every module in this repository.

## Tests
`tools/tests/test_verify.py`, `tools/tests/test_gates_static.py` and
`tools/tests/conftest.py`. Nineteen tests, 9 unit / 10 integration (47% unit, inside the
40–60% band gate 15 will enforce at T-0007).

Unit, over the runner's own logic (`test_verify.py`):
- gates run cheapest-first, ties by number;
- `--list` exits 0 and names every registered gate;
- a `GateResult(ok=False)` with a blank detail is rejected at construction;
- a passing gate whose detail is non-empty has that detail printed under its `PASS` line;
- a passing gate whose detail is empty prints its own line and nothing else;
- a gate whose `run` raises is reported `FAIL` with the exception type, its message and its
  traceback in the detail, and the gates after it still run.

Unit, over each gate's own `run()` (`test_gates_static.py`) — the bad input is planted, the
real tool runs, and the gate must return `ok=False` carrying that tool's words:
- gate 1 rejects an unused import and its detail contains `F401`;
- gate 2 rejects a contradicted annotation and its detail contains
  `Incompatible types in assignment`;
- gate 14 rejects a failing test and its detail names the failing test.

Integration, through a real subprocess — the real `Makefile`, the real tools, the real
runner:
- a real succeeding command run through the real `run_tools` comes back `ok=True` with a
  non-empty `detail` that is **that command's own last output line**. This is the only
  test that touches the code building the detail; without it, `_summary_line` returning
  `""` left the whole suite green and made a `make verify` that skipped every proof
  byte-identical to one that ran them (DEC-0024);
- `make verify` over this repository exits 0 and prints the registered count;
- a copy of `Makefile`, `pyproject.toml` and `tools/` whose `REGISTRY` is reset to one
  literal failing `Gate(...)` exits non-zero;
- that run names the failing gate and prints `"1 gates registered, 1 failed"`;
- with the nesting marker removed from the environment, the whole of `tools/tests/` runs in
  a child process and reports **no skips at all** — the proof that the nesting guard below
  does only what it claims (DEC-0016). That child deselects the test itself, and the
  deselect is **verified at collection time before the child that executes anything is
  started**: `--deselect` with an id matching nothing is silently ignored by `pytest` (exit
  0, no warning), so a drifting id would let the child run that test, which would spawn its
  own child, without bound — nested processes were observed climbing 8 to 18 over a minute.
  A collection-only run executes nothing and so can spawn nothing, and its summary must
  report exactly one deselected test, which fails a drifted id in hundredths of a second;
- with the marker **set**, a child reports skips for exactly
  `conftest.SPAWNS_A_RE_ENTERING_PROCESS` and nothing else, compared by node id through
  the child's JUnit XML. This is the pin that makes the previous item mean something: that
  child runs with the marker absent, so every `skipif` in the suite is False by
  construction there and only an *unconditional* skip could ever be caught. Until T-0002b
  the skip set could widen back to anything — `outermost_run_only` back on the `ruff` and
  `mypy` tests left the suite green while a marked run skipped half of it;
- two `make verify` runs started concurrently both exit 0. Probe destinations are
  per-process, so neither run unlinks the other's files;
- each of the three bad inputs, planted where the tool scans it, makes the real
  `make verify` exit non-zero and print `FAIL  gate <n>` for exactly the gate it targets.

The failure proof deliberately goes through the **real registration path** — `REGISTRY` in
a copied tree — because that is the only registration path the product has. Proving the
runner fails via a mechanism nothing else uses proves the mechanism, not the runner.

**The bad inputs live in `tools/tests/badfixtures/`** and are excluded from `ruff` and
`mypy` in `pyproject.toml`; none of their names matches a pytest collection pattern. A
deliberately bad file can therefore sit in the tree, reviewable in a diff, without the
repository failing its own verify — and no gate is disabled to achieve it. Each test copies
one into a scanned path for the duration of the test and removes it again, at **its own**
destination: a nested `pytest` runs the un-skipped tests of `test_gates_static.py` again, so
a destination shared between two tests would be unlinked by the nested run while the outer
test still held it.

**Every destination is suffixed with the planting process's id.** The same collision happens
between two independent runs — two agents, a CI matrix, one
`diff <(make verify) <(make verify)`. With fixed destinations those runs deleted each other's
probes mid-test: `FileNotFoundError` out of `_planted`'s cleanup, and plant-and-scan proofs
failing for a reason that was nothing to do with the gate they prove. `os.getpid()` is read
in `test_gates_static.py` only; `tools/verify.py` and `tools/gates/` still read no
environment and gain no surface. For the same reason `_tree_with_one_failing_gate_registered`
copies `tools/` with `ignore=TRANSIENT`: `shutil.copytree` enumerates before it copies, and a
concurrent run's probe that vanishes in between makes it raise `shutil.Error`.

**Nesting is bounded by a marker, not by a production flag.** Gate 14 runs `pytest`, so a
test that spawns `make verify` (or `pytest`) spawns something that runs that test again.
Every such test marks the processes it spawns with `CADGPT_NESTED_VERIFY=1`, and a marked
run skips them. Recursion stops one level down; the proof still runs in full at the depth a
person or CI invokes it from.

The marker name, the `outermost_run_only` decorator and the `make_verify(cwd)` spawn helper
are defined **once**, in `tools/tests/conftest.py`, and nowhere in `tools/verify.py` or
`tools/gates/`: the runner has exactly one registration path and gains no test-only surface,
no flag and no env read. The decorator goes on only the eight tests that spawn a process
re-entering the harness, and `SPAWNS_A_RE_ENTERING_PROCESS` in the same file names them by
node id so that set is checked rather than remembered. The two tests that spawn `ruff` and
`mypy` carry no marker — those tools are not this suite and cannot recurse, and a test
skipped for a reason untrue about it is a proof silently lost.

The guard is spoofable, and DEC-0024 accepts that and makes its effect visible instead:
gate 14 reports `pytest`'s summary line, so
`env CADGPT_NESTED_VERIFY=1 make verify` prints `11 passed, 8 skipped` where a full run
prints `19 passed`. **`make verify` alone is therefore not evidence that this suite ran in
full** — that is why every task also runs `uv run --group dev pytest tools/tests/ -q`
directly, and why one test asserts the suite reports zero skips when the marker is absent.

Both test modules import the shared pieces as `from tools.tests.conftest import ...`, not
`from conftest import ...`. `tools/` is a package, so `mypy --strict tools/` names that file
`tools.tests.conftest`; the bare spelling works under `pytest` and fails gate 2 with
`Cannot find implementation or library stub for module named "conftest"`.

**Mocking: none.** No fake gate module is imported, no filesystem is faked, `make` is
invoked as `make`, and `ruff`, `mypy` and `pytest` are the real tools over real files.

## How to run it
```
$ make verify
python3 -m tools.verify
PASS  gate 1  format-and-lint
        All checks passed!
        9 files already formatted
PASS  gate 2  types
        Success: no issues found in 9 source files
PASS  gate 14  tests
        ============================= 19 passed in 16.51s ==============================
3 gates registered, 0 failed
$ echo $?
0
```

Each `PASS` carries its tool's own summary line, so a run that checked less than it should
is visible as one (DEC-0024) — gate 14's line is a count, gate 1's `All checks passed!` is
not. One level down, inside a process this suite spawned, the same command reports the
difference:

```
$ env CADGPT_NESTED_VERIFY=1 make verify
python3 -m tools.verify
PASS  gate 1  format-and-lint
        All checks passed!
        9 files already formatted
PASS  gate 2  types
        Success: no issues found in 9 source files
PASS  gate 14  tests
        ======================== 11 passed, 8 skipped in 0.58s =========================
3 gates registered, 0 failed
```

Listing without running anything:

```
$ python3 -m tools.verify --list
gate 1  cost 1  format-and-lint
gate 2  cost 2  types
gate 14  cost 3  tests
3 gates registered
```

A failure prints the tool's own message, in full and unedited, indented under the gate that
produced it — the success lines above are summaries, a failure never is:

```
FAIL  gate 2  types
        $ uv run --group dev mypy --strict tools/
        exited 1
        tools/mismatched_annotation_probe_318041.py:14: error: Incompatible types in assignment (expression has type "int", variable has type "str")  [assignment]
        Found 1 error in 1 file (checked 10 source files)
```

## Open questions
- Three gates of sixteen are registered. A green `make verify` today means the tree is
  lint-clean, type-clean under `--strict` and its tests pass — and nothing more. In
  particular **nothing about `src/` is checked yet**, because there is no `src/`. Gates
  4–7 are T-0003 to T-0006; `docs/architecture/harness.md` names all sixteen and when each
  becomes real.
- **DEC-0023 is closed**, not open: gate 4 does not close the raw-HTTP path. `ifctester` is a
  forced inherited component and pulls `requests` into the engine closure, so gate 4 asserts
  instead that no inference SDK resolves and that every HTTP-capable package in the closure
  is on an allowlist. The raw-HTTP path is closed by **gate 3** (import contracts), which
  forbids `src/engine` from importing any HTTP client or socket module, and gate 3 ships at
  **C1.1** — it cannot exist before there is an `src/` package to constrain. Until C1.1 that
  path is unguarded, and that is known and scheduled, not overlooked.
- Gate 2 checks `tools/` and gate 14 collects the whole repository. The first `src/` task
  must extend gate 2's paths in that same task, or `src/` will be type-checked by nothing
  while `make verify` stays green.
- **Concurrent runs no longer corrupt each other, but they are not fully isolated.**
  Per-process probe destinations stop two runs unlinking each other's files, which is what
  T-0002b §4 fixed and what `test_concurrent_verify_runs_do_not_collide` proves. A planted
  probe still sits in the real tree, so while it exists another run's *same* gate can see
  it: run A's `unused_import_probe_<pid>.py` would fail run B's gate 1 if B happened to be
  inside `ruff check .` at that instant. It survives today because the two bad fixtures are
  clean to each other's gate — `unused_import.py` passes `mypy --strict` and
  `mismatched_annotation.py` passes `ruff check` and `ruff format --check` — so only a
  same-gate overlap can bite, and the windows are tenths of a second at opposite ends of a
  run. Measured: five consecutive `make verify` pairs started together, all ten exits 0.
  That is a probability, not a guarantee, and the only real fix is planting into a copied
  tree instead of this one — which would stop the proofs going through the real
  `make verify`, so it has not been taken. A new bad fixture that is *not* clean to the
  other gates would make this bite immediately.
