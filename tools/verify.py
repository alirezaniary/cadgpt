"""The verification harness runner behind `make verify`.

`make verify` is the whole quality interface of this repository (CLAUDE.md sections 3
and 9). The harness is a *registry*, not a fixed list: a gate is added by the task that
introduces the artefact type it guards, in that same task (DEC-0022). Registering a gate
costs exactly one module plus one entry in ``REGISTRY`` below, and that cost is kept
small on purpose so no task is tempted to defer its gate.

Two properties of the runner are deliberate:

* It runs **every** gate even after one has failed. A runner that stops at the first
  failure hides how much else is broken and makes an agent iterate one gate at a time.
* It prints **how many gates are registered**. The harness's own coverage is therefore
  visible rather than assumed, which is the mitigation DEC-0022 accepted when it made
  the gate count grow over time.

Gate numbers are stable and match the table in ``docs/architecture/harness.md``.
"""

from __future__ import annotations

import argparse
import sys
import traceback
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import TextIO

from tools.gates import (
    determinism,
    isolation,
    jurisdiction,
    lint,
    module_contract,
    placeholder,
    test_balance,
    tests,
    types,
)


@dataclass(frozen=True)
class GateResult:
    """The outcome of one gate.

    A failing result must say what failed and where, because the report a failing
    ``make verify`` prints is the only thing the next agent sees.
    """

    ok: bool
    detail: str

    def __post_init__(self) -> None:
        if not self.ok and not self.detail.strip():
            raise ValueError(
                "a failing GateResult must carry a detail saying what failed and where"
            )


@dataclass(frozen=True)
class Gate:
    """One build guard.

    ``number`` is stable and matches ``docs/architecture/harness.md``.
    ``cost`` is 1 (seconds), 2 (tens of seconds) or 3 (minutes); the runner sorts by it
    so a broken change fails in seconds rather than minutes.
    """

    number: int
    name: str
    cost: int
    run: Callable[[], GateResult]


REGISTRY: list[Gate] = [
    Gate(number=1, name="format-and-lint", cost=1, run=lint.run),
    Gate(number=2, name="types", cost=2, run=types.run),
    Gate(number=4, name="isolation-proof", cost=3, run=isolation.run),
    Gate(number=5, name="jurisdiction-guard", cost=1, run=jurisdiction.run),
    Gate(number=6, name="placeholder-scan", cost=1, run=placeholder.run),
    Gate(number=7, name="module-contract", cost=1, run=module_contract.run),
    Gate(number=15, name="test-balance", cost=1, run=test_balance.run),
    Gate(number=16, name="determinism", cost=2, run=determinism.run),
    Gate(number=14, name="tests", cost=3, run=tests.run),
]
"""The single place a gate is registered.

A gate is one module under ``tools/gates/`` exposing ``run() -> GateResult`` plus one
entry here. There is no other registration path, no plugin loader and no injection flag:
the failure proof in ``tools/tests/test_verify.py`` goes through this list, because a
mechanism nothing else uses proves nothing about the one that ships.

Every gate is added by the task that introduces the artefact type it guards (DEC-0022);
gate numbers are stable and match ``docs/architecture/harness.md``.
"""


def in_cost_order(gates: Sequence[Gate]) -> list[Gate]:
    """Cheapest gates first; ties broken by gate number so a run is deterministic."""
    return sorted(gates, key=lambda gate: (gate.cost, gate.number))


def write_listing(gates: Sequence[Gate], out: TextIO) -> None:
    """Print the registered gates without running any of them."""
    out.writelines(
        f"gate {gate.number}  cost {gate.cost}  {gate.name}\n"
        for gate in in_cost_order(gates)
    )
    out.write(f"{len(gates)} gates registered\n")


def run_gates(gates: Sequence[Gate], out: TextIO) -> bool:
    """Run every gate in cost order, printing one line each. True only if all passed.

    A gate that raises is a failing gate, not a crashed run: its traceback becomes the
    detail. A runner that dies on the first broken gate hides how much else is broken.

    A non-empty detail is printed on **PASS as well as FAIL** (DEC-0024). A gate that
    skipped part of what it was asked to check has something to say about its own
    coverage, and a run that says nothing about it is indistinguishable from a run that
    checked everything — the silent green this repository exists to make impossible. A
    gate with nothing to report returns an empty detail and prints nothing, so clean runs
    stay readable; a gate that is noisy on success is a defect in that gate, not a reason
    for the runner to hide it.
    """
    ordered = in_cost_order(gates)
    failed: list[Gate] = []
    for gate in ordered:
        try:
            result = gate.run()
        except Exception:  # noqa: BLE001
            # Whatever a gate raises is that gate's failure, not the runner's, so the
            # remaining gates still run. format_exc() carries the exception type, its
            # message and the traceback, so the printed detail is enough to fix the gate
            # without re-running. KeyboardInterrupt and SystemExit still propagate: those
            # are the operator stopping the run, not a gate reporting a defect.
            result = GateResult(ok=False, detail=traceback.format_exc())
        out.write(f"{'PASS' if result.ok else 'FAIL'}  gate {gate.number}  {gate.name}\n")
        if not result.ok:
            failed.append(gate)
        if result.detail:
            out.writelines(f"        {line}\n" for line in result.detail.splitlines())
    out.write(f"{len(ordered)} gates registered, {len(failed)} failed\n")
    return not failed


def main(argv: list[str]) -> int:
    """--list prints registered gates and exits 0.

    Otherwise runs every gate in cost order, prints one line each, prints the
    registered count, and returns 0 only if all passed.
    """
    parser = argparse.ArgumentParser(
        prog="tools.verify", description="Run this repository's build gates."
    )
    parser.add_argument(
        "--list",
        dest="list_only",
        action="store_true",
        help="print the registered gates and exit 0 without running them",
    )
    args = parser.parse_args(argv)
    list_only: bool = bool(args.list_only)

    if list_only:
        write_listing(REGISTRY, sys.stdout)
        return 0
    return 0 if run_gates(REGISTRY, sys.stdout) else 1


if __name__ == "__main__":
    # `python -m tools.verify` would otherwise load this file twice under two names —
    # once as `__main__` and once as `tools.verify` — so a gate module's
    # `from tools.verify import GateResult` would not name the class the runner is
    # holding, and its REGISTRY entries would land in the other copy's list. Delegate to
    # the properly imported module so there is exactly one runner.
    from tools.verify import main as _main

    raise SystemExit(_main(sys.argv[1:]))
