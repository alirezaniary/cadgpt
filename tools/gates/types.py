"""Gate 2 — types, wrapping ``mypy --strict`` (``docs/architecture/harness.md``)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from tools.gates import run_tools

if TYPE_CHECKING:
    from tools.verify import GateResult


def run() -> GateResult:
    """Fail on any untyped boundary, under ``--strict`` and with no blanket ignores.

    ``tools/`` and ``src/`` are both checked, one command, since ``src/engine`` (T-0010)
    became the first ``src/`` package.
    """
    return run_tools([["mypy", "--strict", "tools/", "src/"]])
