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


def run_tools(commands: Sequence[Sequence[str]]) -> GateResult:
    """Run each command through ``uv run --group dev``; fail if any exits non-zero.

    Every command runs even after one of them has failed, for the same reason
    ``run_gates`` runs every gate: a report that stops at the first failure hides how much
    else is broken.

    ``GateResult`` is imported inside the function on purpose. ``tools.verify`` imports
    this package to build its registry, so importing it at module level would be a cycle.
    """
    from tools.verify import GateResult

    failures: list[str] = []
    for command in commands:
        invocation = ["uv", "run", "--group", "dev", *command]
        completed = subprocess.run(
            invocation,
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        if completed.returncode != 0:
            output = (completed.stdout + completed.stderr).strip()
            failures.append(
                f"$ {' '.join(invocation)}\nexited {completed.returncode}\n{output}"
            )
    return GateResult(ok=not failures, detail="\n".join(failures))
