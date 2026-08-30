"""Everything this suite needs to run the harness against a tree that is not this one.

Gate 14 runs ``pytest``, and these tests prove the gates work by running the real
``make verify``. So a test that spawns one of those spawns something that runs this suite
again, and a test that plants a bad input where a gate will find it is mutating the tree it
is itself being run from. This module holds the three mechanisms that make both safe, in
one place so that both test modules use one spelling of each.

**1. Nothing here writes into this checkout.** ``copied_tree`` copies the harness — the
``Makefile``, ``pyproject.toml``, ``uv.lock`` and ``tools/`` — into a ``tmp_path`` and hands
back the copy's root. Every gate-rejection proof plants its bad input there and runs the
gate, or the whole of ``make verify``, in the copy. It is still a real end-to-end proof: a
real ``Makefile``, a real runner, a real ``ruff``/``mypy``/``pytest``, a real bad input. It
simply is not *this* checkout, and the gate scans its own root either way.

Before T-0002c the probes were planted into the real ``tools/`` under a per-process name.
Three concurrent ``make verify`` runs then failed six of twelve, *across* gates: one run's
lint probe vanishing mid-walk made another run's gate 2 report ``Cannot read file``. The
per-process names, and the ``ignore`` argument that kept ``shutil.copytree`` from tripping
over a vanishing probe, were both symptoms of the same thing and are both gone.

**2. Descent is bounded by two markers, and capped by a counter.** A child that this suite
spawns carries ``CADGPT_NESTED_VERIFY=1``, and a run that sees it skips the tests that
spawn in turn (``outermost_run_only``). Two tests must spawn a child *without* that marker,
because what they are proving is what an unmarked run does; they cannot use it to stop
themselves and are skipped by depth instead (``depth_zero_only``).

**3. The cap.** Every spawn helper here increments ``CADGPT_VERIFY_DEPTH`` in the child, and
a session deeper than ``MAX_DEPTH`` fails at import, before it collects anything. Depth 2 is
reached legitimately — an unmarked child at depth 1 runs the tests that spawn marked
children at depth 2 — and nothing correct goes further. This supersedes per-vector
fast-fails: any future mistake in a skip set surfaces in seconds as a named error instead of
climbing 7 processes to 35 in thirty seconds, killable only by process group.

The guards are a property of the **tests**. ``tools/verify.py`` and ``tools/gates/`` read
neither marker nor the counter and gain no flag, no env read and no config key. T-0001a
removed an injection path from the runner deliberately, and it does not come back through a
conftest.

DEC-0024 accepts that no environment marker is unspoofable and requires the guard's effect
to be visible instead: gate 14 reports ``pytest``'s summary line, so a run that skipped
proofs says so. Three consequences are enforced by tests rather than remembered:

* ``SPAWNS_A_RE_ENTERING_PROCESS`` below names, by node id, exactly the tests that must be
  skipped one level down, and
  ``test_verify.test_only_the_spawning_tests_skip_one_level_down`` asserts set equality
  against what a marked run really skipped, so widening or narrowing it fails;
* with no marker present nothing at all is skipped, which
  ``test_verify.test_nothing_is_skipped_without_the_nesting_marker`` proves;
* a full ``make verify`` and a nested one really do print different output, which
  ``test_verify.test_a_full_run_is_visibly_different_from_a_nested_one`` proves by running
  both, at the outermost real entry point.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path

import pytest

from tools.verify import GateResult

REPO_ROOT = Path(__file__).resolve().parents[2]
"""This checkout. It is **copied from and never written to**: no test in this suite may
create, modify or delete a file under it, at any point, for any reason."""

NESTED = "CADGPT_NESTED_VERIFY"
"""Marks a process this suite spawned. Spelled here and nowhere else in the repository."""

DEPTH = "CADGPT_VERIFY_DEPTH"
"""How many spawns below the run a person started this process is. Spelled here only."""

MAX_DEPTH = 2
"""The deepest a correct arrangement of this suite reaches.

Depth 1 is a child this suite spawned. Depth 2 is a child of an *unmarked* depth-1 child:
``test_nothing_is_skipped_without_the_nesting_marker`` and
``test_a_full_run_is_visibly_different_from_a_nested_one`` each run this suite with the
marker absent, so the tests that spawn marked children run there too. Nothing correct goes
deeper, because a marked child skips every test that would spawn again.
"""

DEPTH_HERE = int(os.environ.get(DEPTH, "0"))
"""Read once, at import, so the cap below is applied before anything is collected."""

if DEPTH_HERE > MAX_DEPTH:
    raise RuntimeError(
        f"{DEPTH}={DEPTH_HERE} is deeper than {MAX_DEPTH}: this pytest session is "
        f"{DEPTH_HERE} spawns below the run a person started, which no correct "
        f"arrangement of this suite reaches. Some test that spawns a process re-entering "
        f"the harness has lost its marker — `outermost_run_only` ({NESTED}) for a test "
        f"that spawns a marked child, `depth_zero_only` ({DEPTH}) for one that spawns an "
        f"unmarked child. Failing the session now rather than spawning another."
    )


outermost_run_only = pytest.mark.skipif(
    os.environ.get(NESTED) == "1",
    reason=(
        "already inside a process this suite spawned: this test runs `make verify` or "
        "`pytest`, either of which runs this test again, without bound"
    ),
)
"""Skip a test that spawns a **marked** process re-entering the harness, one level down.

Only such a test. The descent stops one level down and the proof still runs in full at the
depth a person or CI invokes it from.
"""

depth_zero_only = pytest.mark.skipif(
    DEPTH_HERE > 0,
    reason=(
        "this test spawns a child with no nesting marker, because an unmarked run is what "
        "it is proving; the marker therefore cannot stop it running itself again, and "
        "depth does"
    ),
)
"""Skip a test that spawns an **unmarked** process re-entering the harness, at any depth.

``outermost_run_only`` cannot bound these two: they exist to observe what a run with no
marker does, so they must not set the marker their own child would be stopped by. Depth is
the only thing left that distinguishes their child from the run a person started.
"""


_STATIC = "tools/tests/test_gates_static.py"
_VERIFY = "tools/tests/test_verify.py"

SPAWNS_A_RE_ENTERING_PROCESS = frozenset(
    {
        f"{_STATIC}::test_tests_gate_fails_on_a_failing_test",
        f"{_STATIC}::test_make_verify_fails_and_names_gate_1",
        f"{_STATIC}::test_make_verify_fails_and_names_gate_2",
        f"{_STATIC}::test_make_verify_fails_and_names_gate_14",
        f"{_VERIFY}::test_make_verify_over_the_real_tree_exits_zero",
        f"{_VERIFY}::test_nothing_is_skipped_without_the_nesting_marker",
        f"{_VERIFY}::test_only_the_spawning_tests_skip_one_level_down",
        f"{_VERIFY}::test_a_full_run_is_visibly_different_from_a_nested_one",
    }
)
"""Exactly the tests skipped one level down, pinned by node id.

Every one of them spawns ``make verify`` or ``pytest``, either of which runs this suite
again, so each must be skipped in a child and no other test may be. The first six carry
``outermost_run_only`` and the last two ``depth_zero_only``; one level down both conditions
are true, so this is one set rather than two. Written out rather than derived from the
decorators: a set derived from the thing it is checking agrees with it by construction and
proves nothing. ``test_only_the_spawning_tests_skip_one_level_down`` compares this literal
against the node ids a marked run really skipped.

Add a test that spawns a re-entering process and it goes here too; a test that spawns
``ruff`` or ``mypy`` does not, because those tools are not this suite and cannot recurse.
"""


_NOT_INHERITED = frozenset({NESTED, "VIRTUAL_ENV"})
"""What a child must not inherit from this process.

``NESTED`` because ``_child_env`` decides it. ``VIRTUAL_ENV`` because a child rooted at a
*copied* tree would otherwise be told to use this checkout's environment for that tree's
project: ``uv`` then prints ``does not match the project environment path`` on stderr, and
since ``_summary_line`` takes a tool's **last** output line, that warning becomes the gate's
summary in place of ``pytest``'s counts — hiding exactly the difference DEC-0024 exists to
show. Observed: gate 14 of both a full and a nested ``make verify`` in a copy reported the
warning and nothing else. The gates read no environment; this is the caller not handing a
child a virtualenv that belongs to a different tree.
"""


def _child_env(*, marked: bool) -> dict[str, str]:
    """The environment for a process this suite spawns: one level deeper, marked or not.

    The depth counter always increments — it is what caps the descent whatever the marker
    says. ``NESTED`` is *removed* rather than left alone when ``marked`` is false, so an
    unmarked child of a marked run really is unmarked.
    """
    child = {
        name: value for name, value in os.environ.items() if name not in _NOT_INHERITED
    }
    child[DEPTH] = str(DEPTH_HERE + 1)
    if marked:
        child[NESTED] = "1"
    return child


def copied_tree(tmp_path: Path, edit: str = "") -> Path:
    """Copy this repository's harness into ``tmp_path`` and return the copy's root.

    The copy holds everything ``make verify`` needs and nothing else: the ``Makefile``, the
    ``pyproject.toml`` that configures every tool, the ``uv.lock`` the gates resolve their
    tools from, and ``tools/``. A gate run in the copy scans the copy, because
    ``tools.gates.REPO_ROOT`` is derived from the running module's own location.

    ``edit`` is appended to the copy's ``tools/verify.py`` when it is non-empty — the way
    the failing-gate proof registers its gate, through the runner's one real registration
    path rather than through a test-only door.

    ``__pycache__`` is not copied. It is not source, and a concurrent run writing bytecode
    into this checkout renames a temporary file into place, which ``shutil.copytree`` —
    which enumerates a directory before it copies it — can see vanish.
    """
    copy = tmp_path / "repo"
    copy.mkdir()
    for name in ("Makefile", "pyproject.toml", "uv.lock"):
        shutil.copy2(REPO_ROOT / name, copy / name)
    shutil.copytree(
        REPO_ROOT / "tools", copy / "tools", ignore=shutil.ignore_patterns("__pycache__")
    )
    if edit:
        with (copy / "tools" / "verify.py").open("a", encoding="utf-8") as runner:
            runner.write(edit)
    return copy


def make_verify(cwd: Path, *, marked: bool = True) -> subprocess.CompletedProcess[str]:
    """Run the real ``make verify`` in ``cwd``, one level deeper than this process.

    ``PYTHON`` is passed so the child runs under the interpreter this suite is running
    under, not whatever ``python3`` resolves to.

    ``marked`` is false only where an unmarked run is the thing being observed; the child
    then runs the whole suite, and its own descendants are bounded by the marker they set
    and by the depth cap.
    """
    return subprocess.run(
        ["make", "verify", f"PYTHON={sys.executable}"],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
        env=_child_env(marked=marked),
    )


def run_pytest(
    cwd: Path, extra: Sequence[str] = (), *, marked: bool
) -> subprocess.CompletedProcess[str]:
    """Run this suite in a child process rooted at ``cwd``, one level deeper.

    ``-p no:cacheprovider`` is passed because a child rooted at this checkout must not
    write a ``.pytest_cache`` into it.
    """
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "tools/tests/",
            "-q",
            "-p",
            "no:cacheprovider",
            *extra,
        ],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
        env=_child_env(marked=marked),
    )


_GATE_PROBE = """
import sys
from tools.gates import {gate}

result = {gate}.run()
sys.stdout.write("ok\\n" if result.ok else "failed\\n")
sys.stdout.write(result.detail)
"""


def gate_result_in(copy: Path, gate: str) -> GateResult:
    """Run one gate's own ``run()`` inside ``copy``, and return what it returned.

    A gate resolves the tree it checks from its own module's location, so proving a gate
    against a copied tree means running the *copy's* gate — in a process whose ``sys.path``
    starts at the copy. Nothing is faked: this is the real ``lint.run()``, ``types.run()``
    or ``tests.run()`` over a real ``ruff``, ``mypy`` or ``pytest``.

    The child is marked. That only matters for gate 14, whose tool is ``pytest`` and would
    otherwise run the copy's suite unmarked; for ``ruff`` and ``mypy`` the marker is inert.
    """
    completed = subprocess.run(
        [sys.executable, "-c", _GATE_PROBE.format(gate=gate)],
        cwd=copy,
        capture_output=True,
        text=True,
        check=False,
        env=_child_env(marked=True),
    )
    if completed.returncode != 0:
        raise AssertionError(
            f"the copy's {gate} gate could not be run at all "
            f"(exit {completed.returncode}):\n{completed.stdout}{completed.stderr}"
        )
    verdict, _, detail = completed.stdout.partition("\n")
    return GateResult(ok=verdict == "ok", detail=detail)
