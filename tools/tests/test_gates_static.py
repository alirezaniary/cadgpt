"""Proof that gates 1, 2 and 14 can reject (DEC-0016).

A guard that has never rejected anything is indistinguishable from a guard that scans
nothing, and it reads as green forever. Each gate here is fed a deliberately bad input from
``badfixtures/`` — twice: once directly through the gate's own ``run()``, and once through
the real ``make verify``, which is the only way anyone actually invokes it.

**Mocking: none.** The real ``ruff``, ``mypy`` and ``pytest`` run over a real file, driven
by the real runner and, for the second half, the real ``Makefile``.

**Every bad input is planted into a copy of this repository, never into this repository.**
``conftest.copied_tree`` makes the copy; the probe goes into it and the gate runs there. A
gate resolves the tree it checks from its own module's location, so the copy's gate checks
the copy — which is why the ``run()`` proofs go through ``conftest.gate_result_in``, a
process rooted at the copy, rather than calling ``run()`` in this one.

Nothing is lost by not planting into this checkout: the gate scans its own root either way.
What is gained is that this suite stops mutating the tree it is being run from. Planting
into the real ``tools/`` made three concurrent ``make verify`` runs fail six of twelve,
across gates — one run's lint probe vanishing mid-walk made another run's gate 2 report
``Cannot read file`` — and it left probe files behind whenever a run was killed. Per-process
probe names narrowed that window; they did not close it, and they are gone.

**Why the nesting guard.** Gate 14 runs ``pytest``, so a test that runs ``make verify`` (or
gate 14's ``run()``) spawns a process that ends up running this module again. Those tests —
and only those — carry ``outermost_run_only`` from ``conftest.py``, which skips them one
level down: recursion stops there and the proof still runs at the depth a person or CI
invokes it from. The two tests that drive ``ruff`` and ``mypy`` cannot recurse and are
**not** skipped; a test skipped for a reason untrue about it is a proof silently lost
(DEC-0024). Beyond that, ``conftest`` caps the depth, so a mistake in the skip set fails a
session in seconds instead of forking.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from tools.tests.conftest import (
    REPO_ROOT,
    copied_tree,
    gate_result_in,
    make_verify,
    outermost_run_only,
)

BAD_FIXTURES = REPO_ROOT / "tools" / "tests" / "badfixtures"

# Where each bad input is planted inside a copy. Every destination is a path the gate's
# tool scans and a name the repository does not otherwise use. No process id and no
# per-test uniqueness is needed any more: each test gets its own copy, so no two plants can
# ever meet.
LINT_PROBE = Path("tools") / "unused_import_probe.py"
TYPES_PROBE = Path("tools") / "mismatched_annotation_probe.py"
TESTS_PROBE = Path("tools") / "tests" / "test_failing_probe.py"


def plant(fixture: str, copy: Path, destination: Path) -> None:
    """Copy one bad input into a path the copy's gate will scan."""
    shutil.copy2(BAD_FIXTURES / fixture, copy / destination)


# --- unit: the gate itself rejects, and carries its tool's own words ---------------


def test_lint_gate_fails_on_an_unused_import(tmp_path: Path) -> None:
    """No nesting marker: `ruff` is not this suite, so this test cannot spawn itself."""
    copy = copied_tree(tmp_path)
    plant("unused_import.py", copy, LINT_PROBE)

    result = gate_result_in(copy, "lint")

    assert result.ok is False
    assert "F401" in result.detail
    assert LINT_PROBE.name in result.detail


def test_types_gate_fails_on_a_mismatched_annotation(tmp_path: Path) -> None:
    """No nesting marker: `mypy` is not this suite, so this test cannot spawn itself."""
    copy = copied_tree(tmp_path)
    plant("mismatched_annotation.py", copy, TYPES_PROBE)

    result = gate_result_in(copy, "types")

    assert result.ok is False
    assert "Incompatible types in assignment" in result.detail
    assert TYPES_PROBE.name in result.detail


@outermost_run_only
def test_tests_gate_fails_on_a_failing_test(tmp_path: Path) -> None:
    """`tests.run()` spawns `pytest`, so the child `gate_result_in` starts is marked."""
    copy = copied_tree(tmp_path)
    plant("assertion_that_fails.py", copy, TESTS_PROBE)

    result = gate_result_in(copy, "tests")

    assert result.ok is False
    assert "test_the_probe_fails_on_purpose" in result.detail


# --- integration: the same bad input fails the real `make verify` ------------------


@outermost_run_only
def test_make_verify_fails_and_names_gate_1(tmp_path: Path) -> None:
    copy = copied_tree(tmp_path)
    plant("unused_import.py", copy, LINT_PROBE)

    result = make_verify(copy)

    assert result.returncode != 0, result.stdout + result.stderr
    assert "FAIL  gate 1  format-and-lint" in result.stdout
    assert "F401" in result.stdout


@outermost_run_only
def test_make_verify_fails_and_names_gate_2(tmp_path: Path) -> None:
    copy = copied_tree(tmp_path)
    plant("mismatched_annotation.py", copy, TYPES_PROBE)

    result = make_verify(copy)

    assert result.returncode != 0, result.stdout + result.stderr
    assert "FAIL  gate 2  types" in result.stdout
    assert "Incompatible types in assignment" in result.stdout


@outermost_run_only
def test_make_verify_fails_and_names_gate_14(tmp_path: Path) -> None:
    copy = copied_tree(tmp_path)
    plant("assertion_that_fails.py", copy, TESTS_PROBE)

    result = make_verify(copy)

    assert result.returncode != 0, result.stdout + result.stderr
    assert "FAIL  gate 14  tests" in result.stdout
    assert "test_the_probe_fails_on_purpose" in result.stdout
