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
proofs says so. Two consequences are enforced by tests rather than remembered, and each
names the test that enforces it:

* ``outermost_run_only`` goes on **only** the tests that spawn a process which re-enters
  the harness — one running ``ruff`` or ``mypy`` cannot recurse and must not be skipped,
  because a test skipped for a reason that is not true about it is a proof silently lost.
  ``SPAWNS_A_RE_ENTERING_PROCESS`` below names that set, and
  ``test_verify.test_only_the_spawning_tests_skip_one_level_down`` asserts set equality
  against what a marked run actually skipped, so widening or narrowing it fails;
* with the marker absent nothing at all is skipped, which
  ``test_verify.test_nothing_is_skipped_without_the_nesting_marker`` proves. DEC-0016: a
  guard ships with a proof that it does what it claims.

Before T-0002b the first of those two was a claim in this docstring and nothing else: a
run one level down could skip any set at all and the suite stayed green.
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


_STATIC = "tools/tests/test_gates_static.py"
_VERIFY = "tools/tests/test_verify.py"

SPAWNS_A_RE_ENTERING_PROCESS = frozenset(
    {
        f"{_STATIC}::test_tests_gate_fails_on_a_failing_test",
        f"{_STATIC}::test_make_verify_fails_and_names_gate_1",
        f"{_STATIC}::test_make_verify_fails_and_names_gate_2",
        f"{_STATIC}::test_make_verify_fails_and_names_gate_14",
        f"{_STATIC}::test_concurrent_verify_runs_do_not_collide",
        f"{_VERIFY}::test_make_verify_over_the_real_tree_exits_zero",
        f"{_VERIFY}::test_nothing_is_skipped_without_the_nesting_marker",
        f"{_VERIFY}::test_only_the_spawning_tests_skip_one_level_down",
    }
)
"""Exactly the tests that carry ``outermost_run_only``, pinned by node id.

Each one spawns ``make verify`` or ``pytest``, either of which runs this suite again, so
each one must be skipped one level down and no other test may be. Written out rather than
derived from the decorator: a set derived from the thing it is checking agrees with it by
construction and proves nothing. ``test_only_the_spawning_tests_skip_one_level_down``
compares this literal against the node ids a marked run really skipped.

Add a test that spawns a re-entering process and it goes here too; a test that spawns
``ruff`` or ``mypy`` does not, because those tools are not this suite and cannot recurse.
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
