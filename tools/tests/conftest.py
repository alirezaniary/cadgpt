"""The one place this suite's nesting guard is spelled.

Gate 14 runs ``pytest``, and these tests prove the gates work by running the real
``make verify``. So a test that spawns one of those spawns something that runs this suite
again, without bound unless something stops the descent. What stops it is a marker in the
environment: a test spawns its child with ``CADGPT_NESTED_VERIFY=1`` set, and a run that
sees the marker skips the tests that would spawn in turn.

The name, the skip decorator and the spawn helper live here so that both test modules use
one mechanism rather than two spellings of it. The guard is a property of the **tests**:
``tools/verify.py`` and ``tools/gates/`` never read this marker and gain no flag, no env
read and no config key for it. T-0001a removed an injection path from the runner
deliberately, and it does not come back through a conftest.

DEC-0024 accepts that no environment marker is unspoofable and requires the guard's effect
to be visible instead: gate 14 reports ``pytest``'s summary line, so a run that skipped
proofs says so. Two consequences are enforced by tests rather than remembered:

* ``outermost_run_only`` goes on **only** the tests that spawn a process which re-enters
  the harness — one running ``ruff`` or ``mypy`` cannot recurse and must not be skipped,
  because a test skipped for a reason that is not true about it is a proof silently lost;
* with the marker absent nothing at all is skipped, which
  ``test_verify.test_nothing_is_skipped_without_the_nesting_marker`` proves. DEC-0016: a
  guard ships with a proof that it does what it claims.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

NESTED = "CADGPT_NESTED_VERIFY"
"""Marks a process this suite spawned. Spelled here and nowhere else in the repository."""

outermost_run_only = pytest.mark.skipif(
    os.environ.get(NESTED) == "1",
    reason=(
        "already inside a process this suite spawned: this test runs `make verify` or "
        "`pytest`, either of which runs this test again, without bound"
    ),
)
"""Skip a test that spawns a process re-entering the harness, one level down.

Only such a test. The descent stops one level down and the proof still runs in full at the
depth a person or CI invokes it from.
"""


def make_verify(cwd: Path) -> subprocess.CompletedProcess[str]:
    """Run the real ``make verify`` in ``cwd``, marking the child as one level down.

    ``PYTHON`` is passed so the child runs under the interpreter this suite is running
    under, not whatever ``python3`` resolves to.
    """
    return subprocess.run(
        ["make", "verify", f"PYTHON={sys.executable}"],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
        env={**os.environ, NESTED: "1"},
    )
