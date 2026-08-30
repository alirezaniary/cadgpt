"""Gate 1 — format and lint, wrapping ``ruff`` (``docs/architecture/harness.md``)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from tools.gates import run_tools

if TYPE_CHECKING:
    from tools.verify import GateResult


def run() -> GateResult:
    """Fail on style drift, unused imports and the defects in the configured selection.

    Both halves run. ``ruff check`` reads the rule selection and ``ruff format --check``
    reads the layout; a tree can satisfy either one while failing the other. The selection
    and the line length live in ``pyproject.toml`` and nowhere else.
    """
    return run_tools([["ruff", "check", "."], ["ruff", "format", "--check", "."]])
