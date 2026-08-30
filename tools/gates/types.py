"""Gate 2 — types, wrapping ``mypy --strict`` (``docs/architecture/harness.md``)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from tools.gates import run_tools

if TYPE_CHECKING:
    from tools.verify import GateResult


def run() -> GateResult:
    """Fail on any untyped boundary, under ``--strict`` and with no blanket ignores.

    ``tools/`` is the whole of the Python in this repository today; the task that creates
    the first ``src/`` package adds it here, in that same task.
    """
    return run_tools([["mypy", "--strict", "tools/"]])
