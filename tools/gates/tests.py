"""Gate 14 — tests, wrapping ``pytest`` (``docs/architecture/harness.md``)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from tools.gates import run_tools

if TYPE_CHECKING:
    from tools.verify import GateResult


def run() -> GateResult:
    """Fail when any test fails.

    ``pytest`` is invoked with no path so it collects whatever the repository holds,
    rather than a list that would have to be remembered and extended.
    """
    return run_tools([["pytest"]])
