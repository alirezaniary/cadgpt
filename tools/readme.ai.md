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
coverage is visible rather than assumed.

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
  prints `PASS`/`FAIL` plus the indented detail of each failure, then
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
  exit code and the tool's own stdout and stderr, unedited.
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
`tools/tests/test_verify.py` and `tools/tests/test_gates_static.py`. Thirteen tests,
7 unit / 6 integration (54%, inside the 40–60% band gate 15 will enforce at T-0007).

Unit, over the runner's own logic (`test_verify.py`):
- gates run cheapest-first, ties by number;
- `--list` exits 0 and names every registered gate;
- a `GateResult(ok=False)` with a blank detail is rejected at construction;
- a gate whose `run` raises is reported `FAIL` with the exception type, its message and its
  traceback in the detail, and the gates after it still run.

Unit, over each gate's own `run()` (`test_gates_static.py`) — the bad input is planted, the
real tool runs, and the gate must return `ok=False` carrying that tool's words:
- gate 1 rejects an unused import and its detail contains `F401`;
- gate 2 rejects a contradicted annotation and its detail contains
  `Incompatible types in assignment`;
- gate 14 rejects a failing test and its detail names the failing test.

Integration, through the real `Makefile` and a real subprocess:
- `make verify` over this repository exits 0 and prints the registered count;
- a copy of `Makefile`, `pyproject.toml` and `tools/` whose `REGISTRY` is reset to one
  literal failing `Gate(...)` exits non-zero;
- that run names the failing gate and prints `"1 gates registered, 1 failed"`;
- each of the three bad inputs, planted where the tool scans it, makes the real
  `make verify` exit non-zero and print `FAIL  gate <n>` for exactly the gate it targets.

The failure proof deliberately goes through the **real registration path** — `REGISTRY` in
a copied tree — because that is the only registration path the product has. Proving the
runner fails via a mechanism nothing else uses proves the mechanism, not the runner.

**The bad inputs live in `tools/tests/badfixtures/`** and are excluded from `ruff` and
`mypy` in `pyproject.toml`; none of their names matches a pytest collection pattern. A
deliberately bad file can therefore sit in the tree, reviewable in a diff, without the
repository failing its own verify — and no gate is disabled to achieve it. Each test copies
one into a scanned path for the duration of the test and removes it again.

**Nesting is bounded by a marker, not by a production flag.** Gate 14 runs `pytest`, so a
test that spawns `make verify` (or `pytest`) spawns something that runs that test again.
Every such test marks the processes it spawns with `CADGPT_NESTED_VERIFY=1`, and a marked
run skips them. Recursion stops one level down; the proof still runs in full at the depth a
person or CI invokes it from. The marker is spelled in the two test modules and nowhere in
`tools/verify.py`: the runner has exactly one registration path and gains no test-only
surface.

**Mocking: none.** No fake gate module is imported, no filesystem is faked, `make` is
invoked as `make`, and `ruff`, `mypy` and `pytest` are the real tools over real files.

## How to run it
```
$ make verify
python3 -m tools.verify
PASS  gate 1  format-and-lint
PASS  gate 2  types
PASS  gate 14  tests
3 gates registered, 0 failed
$ echo $?
0
```

Listing without running anything:

```
$ python3 -m tools.verify --list
gate 1  cost 1  format-and-lint
gate 2  cost 2  types
gate 14  cost 3  tests
3 gates registered
```

A failure prints the tool's own message, indented under the gate that produced it:

```
FAIL  gate 2  types
        $ uv run --group dev mypy --strict tools/
        exited 1
        tools/mismatched_annotation_probe.py:14: error: Incompatible types in assignment (expression has type "int", variable has type "str")  [assignment]
        Found 1 error in 1 file (checked 9 source files)
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
