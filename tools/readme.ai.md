# readme.ai.md — tools/

## Purpose
`tools/` is the verification harness: the runner behind `make verify`, which is the whole
quality interface of this repository (`CLAUDE.md` §3 and §9). It owns the *mechanism* by
which build gates are registered, ordered, run and reported — and nothing else.

It is **not** a gate. It contains no check of its own: it does not lint, type-check, scan
`src/`, or know what any particular gate does. A gate is added by the task that introduces
the artefact type it guards, in that same task (DEC-0022), as one module plus one `REGISTRY`
entry. `REGISTRY` is empty today, and `make verify` says so out loud rather than implying
coverage it does not have.

It is also **not** part of the product. Nothing under `src/` may import it, and it ships in
no distribution.

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
- `REGISTRY: list[Gate]` — the single place a gate is registered. Empty at P0. A gate module
  appends to it at import time; there is no other registration path, no plugin loader and no
  injection flag.
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

## Invariants enforced here
None from `docs/ddd/04-aggregates-and-invariants.md`: `tools/` is outside the domain model
and owns no domain aggregate.

Two local invariants of the harness itself are enforced here and are not re-checked by
callers:

- **A failing gate always carries a detail.** `GateResult.__post_init__`
  (`tools/verify.py`) — a gate cannot construct a silent failure.
- **Every registered gate runs, whatever any other gate does.** `run_gates`
  (`tools/verify.py`) — the `try`/`except Exception` around `gate.run()` means one broken
  gate cannot hide how much else is broken.

## Depends on
The Python standard library only: `argparse` (the CLI), `dataclasses` (the two value
objects), `traceback` (the detail of a raising gate), `sys`, `collections.abc`, `typing`.

Nothing else, on purpose. The runner has to be able to run before and without the rest of
the toolchain, and every gate brings its own tooling when it is registered (DEC-0022).

Tests additionally use `pytest` (dev group) and invoke `make` and the real runner through
`subprocess`.

## Must not depend on
- **Anything under `src/`.** The harness checks the product; a harness importing the thing
  it checks can be broken by the same defect it is meant to catch.
- **Any third-party package.** `make verify` must run on a clean checkout with nothing
  installed, so that a broken environment fails as a gate's own failure and not as an import
  error before any gate runs.
- **Any inference client or model SDK** (I1, I2) — as for every module in this repository.

## Tests
`tools/tests/test_verify.py`. Seven tests, 4 unit / 3 integration (57%, inside the 40–60%
band gate 15 will enforce at T-0007).

Unit, over the runner's own logic:
- gates run cheapest-first, ties by number;
- `--list` exits 0 and names every registered gate;
- a `GateResult(ok=False)` with a blank detail is rejected at construction;
- a gate whose `run` raises is reported `FAIL` with the exception type, its message and its
  traceback in the detail, and the gates after it still run.

Integration, through the real `Makefile` and a real subprocess:
- `make verify` over this repository exits 0 and prints the registered count;
- a copy of `Makefile`, `pyproject.toml` and `tools/` with one literal
  `REGISTRY.append(Gate(...))` block appended to the copied runner exits non-zero;
- that run names the failing gate and prints `"1 gates registered, 1 failed"`.

The failure proof deliberately goes through the **real registration path** — appending to
`REGISTRY` in a copied tree — because that is the only registration path the product has.
Proving the runner fails via a mechanism nothing else uses proves the mechanism, not the
runner.

**Mocking: none.** No fake gate module is imported, no filesystem is faked, and `make` is
invoked as `make`.

## How to run it
```
$ make verify
python3 -m tools.verify
0 gates registered, 0 failed
$ echo $?
0
```

Listing without running anything:

```
$ python3 -m tools.verify --list
0 gates registered
```

## Open questions
- `REGISTRY` is empty. `make verify` passing today means only that the runner works — it
  proves nothing about the tree. The nine P0 gates are T-0002 onward
  (`docs/architecture/harness.md` names all sixteen and when each becomes real). Do not read
  a green `make verify` as evidence about `src/` until gates are registered.
- **DEC-0023 is closed**, not open: gate 4 does not close the raw-HTTP path. `ifctester` is a
  forced inherited component and pulls `requests` into the engine closure, so gate 4 asserts
  instead that no inference SDK resolves and that every HTTP-capable package in the closure
  is on an allowlist. The raw-HTTP path is closed by **gate 3** (import contracts), which
  forbids `src/engine` from importing any HTTP client or socket module, and gate 3 ships at
  **C1.1** — it cannot exist before there is an `src/` package to constrain. Until C1.1 that
  path is unguarded, and that is known and scheduled, not overlooked.
- `uvx mypy --strict tools/` reports `import-not-found` for `pytest`, because `uvx` builds an
  isolated environment that has no dev dependencies in it. The type check is clean under
  `uvx --with pytest mypy --strict tools/`. Whichever form gate 2 adopts at T-0002 has to
  make the test dependencies visible to mypy; the bare `uvx mypy` form cannot pass while
  `tools/tests/` imports `pytest`.
