# T-0001 — Build the gate registry and `make verify`

Slice: S0.1 · Capability: P0 · Outcome: O1

## Prerequisites
None. This is the first code in the repository.

## Objective
`make verify` exists, runs a registry of gates cheapest-first, prints how many are registered,
and exits non-zero if any fail. No real gates yet — this task builds the mechanism and proves
the mechanism can fail.

## Context — read these and nothing else
- `CLAUDE.md`
- `docs/architecture/harness.md`
- `docs/architecture/stack.md`
- `docs/architecture/module-map.md`
- `docs/process/readme-ai-convention.md`
- `decisions/DEC-0022-gates-ship-with-their-artifact.md`

## Contract
```python
# tools/verify.py
from dataclasses import dataclass
from collections.abc import Callable

@dataclass(frozen=True)
class GateResult:
    ok: bool
    detail: str           # on failure: what failed and where. Never empty when ok is False.

@dataclass(frozen=True)
class Gate:
    number: int           # stable, matches docs/architecture/harness.md
    name: str
    cost: int             # 1 = seconds, 2 = tens of seconds, 3 = minutes. Runner sorts by this.
    run: Callable[[], GateResult]

REGISTRY: list[Gate]      # the single place a gate is registered

def main(argv: list[str]) -> int:
    """--list prints registered gates and exits 0.
    Otherwise runs every gate in cost order, prints one line each,
    prints the registered count, and returns 0 only if all passed."""
```

Run **all** gates even after one fails, then report. A runner that stops at the first failure
hides how much else is broken and makes an agent iterate one gate at a time.

## Invariants this task must uphold
- **No scaffolding.** No gate module is created here except the one deliberately-failing gate
  used by the meta-test. Do not create empty `src/` packages.
- Registering a gate must cost one entry in `REGISTRY` plus one module. If it costs more, later
  tasks will defer it (DEC-0022).
- Typed throughout; `mypy --strict` must pass on this code once T-0002 wires it.

## Files
Create: `pyproject.toml`, `Makefile`, `tools/__init__.py`, `tools/verify.py`,
`tools/tests/__init__.py`, `tools/tests/test_verify.py`, `tools/readme.ai.md`
Modify: none
Forbidden: everything else. No `src/`. No dependencies beyond `uv`-managed dev tooling.

## pyproject requirements
Declare the distributions and dependency groups from `docs/architecture/module-map.md`.
`cadgpt-engine`'s group must contain **no inference SDK and no HTTP client** — T-0003 asserts
this, so declare it correctly now even though no engine code exists.

## Tests
Unit (3): cost ordering is respected; `--list` exits 0 and names every registered gate; a
`GateResult(ok=False)` with an empty detail is rejected at construction.
Integration (3): `make verify` over the real tree exits 0; with a deliberately failing gate
registered it exits non-zero; its output names the failing gate and prints the registered count.
Mocking: none permitted. Invoke the real `make verify` via subprocess.

## Acceptance
```
make verify            # exits 0, prints "0 gates registered"
python -m tools.verify --list
uv run --group dev pytest tools/tests/ -q
```
Quote the actual output of `make verify` in the completion report.

## Deliverables
Code · tests (3 unit / 3 integration) · `tools/readme.ai.md` · completion report per
`docs/process/definition-of-done.md`.

## If you hit an unresolved decision
Write `decisions/DEC-XXXX.md` with `Status: OPEN`, stop, report. Do not decide.
