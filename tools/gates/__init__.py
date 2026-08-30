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


def _summary_line(stdout: str) -> str:
    """The last non-empty line of a tool's **stdout** — the line these tools summarise on.

    ``stdout`` only, never ``stderr``. ``ruff``, ``mypy`` and ``pytest`` all write their
    summary to stdout; what arrives on stderr is whoever ran them talking — ``uv``
    announcing ``Installed 12 packages in 23ms`` on a cold environment, or warning that a
    virtualenv does not match the project. Taking the last line of the two streams merged
    let any such line displace the tool's own report and become the gate's summary, which
    is the one thing DEC-0024 requires that summary to be. Failure detail is unaffected and
    still carries both streams: on a failure you want everything.

    It is **not** reliably a count. ``mypy`` ends on ``Success: no issues found in N
    source files`` and ``pytest`` on ``N passed``, both of which say how much was checked;
    ``ruff check`` ends on ``All checks passed!``, which is identical over this repository
    and over an empty directory and says nothing about how much it looked at. What this
    line is good for is showing that a run differs from another run — a gate 14 that
    skipped its proofs reports a different line from one that ran them (DEC-0024) — and
    for ``ruff`` that difference has to come from the gate failing instead.

    That difference is proven where it is read, not only here:
    ``test_verify.test_a_full_run_is_visibly_different_from_a_nested_one`` runs the real
    ``make verify`` over one tree twice, plain and marked, and fails if the two printed
    outputs are the same.

    Empty when the tool printed nothing on stdout, so a silent tool contributes no line.
    """
    for line in reversed(stdout.splitlines()):
        if line.strip():
            return line.strip()
    return ""


def run_tools(commands: Sequence[Sequence[str]]) -> GateResult:
    """Run each command through ``uv run --group dev``; fail if any exits non-zero.

    Every command runs even after one of them has failed, for the same reason
    ``run_gates`` runs every gate: a report that stops at the first failure hides how much
    else is broken.

    The detail of a failure is the invocation, the exit code and the tool's own output —
    stdout **and** stderr, unedited, because on a failure you want everything. The detail of
    a success is one line per command: the last non-empty line of that command's **stdout**
    (DEC-0024). Discarding it made a run that checked nothing print exactly what a run that
    checked everything prints, which is the silent green this repository is built to
    prevent; ``test_verify.test_a_full_run_is_visibly_different_from_a_nested_one`` fails on
    that edit from outside, through the real ``make verify``. Reading stderr into the
    success summary was the same hole by another route: anything ``uv`` wrote after the tool
    finished became the gate's summary in place of the tool's own line. A command that
    printed nothing on stdout contributes no line.

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
        if completed.returncode != 0:
            everything = (completed.stdout + completed.stderr).strip()
            failures.append(
                f"$ {' '.join(invocation)}\nexited {completed.returncode}\n{everything}"
            )
        elif summary := _summary_line(completed.stdout):
            summaries.append(summary)
    if failures:
        return GateResult(ok=False, detail="\n".join(failures))
    return GateResult(ok=True, detail="\n".join(summaries))
