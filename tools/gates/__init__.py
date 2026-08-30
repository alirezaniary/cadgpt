"""The build gates registered in ``tools.verify.REGISTRY``.

Each module here exposes ``run() -> GateResult`` and wraps one inherited tool
(``CLAUDE.md`` §6: inherit before writing). No gate here re-implements a check. A gate's
whole job is to invoke its tool the way this repository has settled on and to hand the
tool's own output back **unedited** — the agent reading a failing ``make verify`` needs
the real message, not a summary of it.

Tools are invoked through ``uv run --group dev`` so they resolve from the ``dev``
dependency group in ``pyproject.toml``. ``uvx`` cannot be used: it builds an isolated
environment with no dev dependencies in it, so gate 2 would report ``pytest`` as a missing
library stub for every test module that imports it, and gate 14 would have no ``pytest``
at all.
"""

from __future__ import annotations

import subprocess
from collections.abc import Sequence
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from tools.verify import GateResult

REPO_ROOT = Path(__file__).resolve().parents[2]
"""Every tool is invoked from the repository root, wherever the runner was started."""


def _summary_line(output: str) -> str:
    """The last non-empty line of a tool's output — the line these tools summarise on.

    ``ruff``, ``mypy`` and ``pytest`` each end on a count. That count is what tells a
    reader how much was actually checked, so it is the one line worth keeping from a
    command that succeeded. Empty when the tool printed nothing.
    """
    for line in reversed(output.splitlines()):
        if line.strip():
            return line.strip()
    return ""


def run_tools(commands: Sequence[Sequence[str]]) -> GateResult:
    """Run each command through ``uv run --group dev``; fail if any exits non-zero.

    Every command runs even after one of them has failed, for the same reason
    ``run_gates`` runs every gate: a report that stops at the first failure hides how much
    else is broken.

    The detail of a failure is the invocation, the exit code and the tool's own output,
    unedited. The detail of a success is one line per command — that command's own summary
    line (DEC-0024). Discarding it made a run that checked nothing print exactly what a run
    that checked everything prints, which is the silent green this repository is built to
    prevent. A command that printed nothing contributes no line.

    ``GateResult`` is imported inside the function on purpose. ``tools.verify`` imports
    this package to build its registry, so importing it at module level would be a cycle.
    """
    from tools.verify import GateResult

    failures: list[str] = []
    summaries: list[str] = []
    for command in commands:
        invocation = ["uv", "run", "--group", "dev", *command]
        completed = subprocess.run(
            invocation,
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        output = (completed.stdout + completed.stderr).strip()
        if completed.returncode != 0:
            failures.append(
                f"$ {' '.join(invocation)}\nexited {completed.returncode}\n{output}"
            )
        elif summary := _summary_line(output):
            summaries.append(summary)
    if failures:
        return GateResult(ok=False, detail="\n".join(failures))
    return GateResult(ok=True, detail="\n".join(summaries))
