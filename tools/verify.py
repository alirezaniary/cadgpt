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
import importlib
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import TextIO

GATES_ATTR = "GATES"
"""Name of the list a module passed to ``--extra-gate`` must expose."""


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


REGISTRY: list[Gate] = []
"""The single place a gate is registered.

Empty at P0: this task built the mechanism, and every gate is added by the task that
introduces the artefact type it guards (DEC-0022).
"""


def in_cost_order(gates: Sequence[Gate]) -> list[Gate]:
    """Cheapest gates first; ties broken by gate number so a run is deterministic."""
    return sorted(gates, key=lambda gate: (gate.cost, gate.number))


def load_gates(module_name: str) -> list[Gate]:
    """Import ``module_name`` and return the ``GATES`` list it exposes."""
    module = importlib.import_module(module_name)
    gates = getattr(module, GATES_ATTR, None)
    if not isinstance(gates, list) or not all(isinstance(gate, Gate) for gate in gates):
        raise TypeError(f"{module_name} must define {GATES_ATTR}: list[Gate]")
    return list(gates)


def write_listing(gates: Sequence[Gate], out: TextIO) -> None:
    """Print the registered gates without running any of them."""
    for gate in in_cost_order(gates):
        out.write(f"gate {gate.number}  cost {gate.cost}  {gate.name}\n")
    out.write(f"{len(gates)} gates registered\n")


def run_gates(gates: Sequence[Gate], out: TextIO) -> bool:
    """Run every gate in cost order, printing one line each. True only if all passed."""
    ordered = in_cost_order(gates)
    failed: list[Gate] = []
    for gate in ordered:
        result = gate.run()
        out.write(
            f"{'PASS' if result.ok else 'FAIL'}  gate {gate.number}  {gate.name}\n"
        )
        if not result.ok:
            failed.append(gate)
            for line in result.detail.splitlines():
                out.write(f"        {line}\n")
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
    parser.add_argument(
        "--extra-gate",
        dest="extra_gates",
        action="append",
        default=[],
        metavar="MODULE",
        help=(
            "import MODULE and append its GATES to the registry for this run only. "
            "This is how the runner's own failure is proved: DEC-0016 requires a gate "
            "to ship with evidence that it fails, and the runner is no exception."
        ),
    )
    args = parser.parse_args(argv)
    list_only: bool = bool(args.list_only)
    extra_modules: list[str] = list(args.extra_gates)

    gates: list[Gate] = list(REGISTRY)
    for module_name in extra_modules:
        gates.extend(load_gates(module_name))

    if list_only:
        write_listing(gates, sys.stdout)
        return 0
    return 0 if run_gates(gates, sys.stdout) else 1


if __name__ == "__main__":
    # `python -m tools.verify` executes this file as `__main__`, so the classes defined
    # above are not the ones a gate module importing `tools.verify` will see. Delegate to
    # the properly imported module so a Gate is a Gate whoever constructed it.
    from tools.verify import main as _main

    raise SystemExit(_main(sys.argv[1:]))
