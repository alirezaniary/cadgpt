"""Proof that gates 1, 2 and 14 can reject (DEC-0016).

A guard that has never rejected anything is indistinguishable from a guard that scans
nothing, and it reads as green forever. Each gate here is fed a deliberately bad input
from ``badfixtures/`` — twice: once directly through the gate's own ``run()``, and once
through the real ``make verify``, which is the only way anyone actually invokes it.

**Mocking: none.** The real ``ruff``, ``mypy`` and ``pytest`` run over a real file. The bad
inputs cannot simply sit in a scanned path, or the repository could never pass its own
verify, so they rest under a directory excluded from every gate in ``pyproject.toml`` and
are copied into place for the duration of one test.

**Why the nesting guard.** Gate 14 runs ``pytest``, so a test that runs ``make verify`` or
``pytest`` spawns a process that ends up running this module again. Those tests — and only
those — carry ``outermost_run_only`` from ``conftest.py``, which skips them one level down:
recursion stops there and the proof still runs at the depth a person or CI invokes it from.
The two tests that spawn ``ruff`` and ``mypy`` cannot recurse and are **not** skipped; a
test skipped for a reason that is untrue about it is a proof silently lost (DEC-0024). The
guard lives in the tests and not as a flag in ``tools/verify.py`` — the runner has exactly
one registration path and gains no test-only surface.

**Why two destinations per bad input.** A nested ``pytest`` runs the un-skipped tests in
this module again, so a probe path shared between a test here and a test that spawns
``make verify`` would be unlinked by the nested run while the outer test still holds it.
Each test therefore plants at a path no other test uses.

**Why every destination carries a process id.** The same collision happens between two
independent runs — two agents, a CI matrix, or one ``diff <(make verify) <(make verify)``.
Fixed destinations made those runs unlink each other's probes mid-test, which surfaced as
``FileNotFoundError`` inside ``_planted``'s cleanup and as spurious gate failures.
Deriving every destination from ``os.getpid()`` makes the plant private to the process
that made it. This is test code and the pid is read here; ``tools/verify.py`` and
``tools/gates/`` still read no environment and gain no surface.
``test_concurrent_verify_runs_do_not_collide`` is the proof.
"""

from __future__ import annotations

import os
import shutil
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from pathlib import Path

import pytest

from tools.gates import lint, tests, types
from tools.tests.conftest import NESTED, make_verify, outermost_run_only

REPO_ROOT = Path(__file__).resolve().parents[2]
BAD_FIXTURES = Path(__file__).parent / "badfixtures"

_PID = os.getpid()
"""Read once, at import, so every destination below belongs to exactly this process."""

# Where each bad input is planted. Every destination is a path the gate's tool scans and
# a name the repository does not otherwise use — one per test, never shared, and suffixed
# with the planting process's id so two concurrent runs cannot unlink each other's files.
LINT_PROBE = REPO_ROOT / "tools" / f"unused_import_probe_{_PID}.py"
TYPES_PROBE = REPO_ROOT / "tools" / f"mismatched_annotation_probe_{_PID}.py"
TESTS_PROBE = REPO_ROOT / "tools" / "tests" / f"test_failing_probe_{_PID}.py"
VERIFY_LINT_PROBE = REPO_ROOT / "tools" / f"unused_import_verify_probe_{_PID}.py"
VERIFY_TYPES_PROBE = REPO_ROOT / "tools" / f"mismatched_annotation_verify_probe_{_PID}.py"


@contextmanager
def _planted(fixture: str, destination: Path) -> Iterator[None]:
    """Copy one bad input into a scanned path, and take it away again afterwards."""
    shutil.copy2(BAD_FIXTURES / fixture, destination)
    try:
        yield
    finally:
        destination.unlink()


# --- unit: the gate itself rejects, and carries its tool's own words ---------------


def test_lint_gate_fails_on_an_unused_import() -> None:
    """No nesting marker: `ruff` is not this suite, so this test cannot spawn itself."""
    with _planted("unused_import.py", LINT_PROBE):
        result = lint.run()

    assert result.ok is False
    assert "F401" in result.detail
    assert LINT_PROBE.name in result.detail


def test_types_gate_fails_on_a_mismatched_annotation() -> None:
    """No nesting marker: `mypy` is not this suite, so this test cannot spawn itself."""
    with _planted("mismatched_annotation.py", TYPES_PROBE):
        result = types.run()

    assert result.ok is False
    assert "Incompatible types in assignment" in result.detail
    assert TYPES_PROBE.name in result.detail


@outermost_run_only
def test_tests_gate_fails_on_a_failing_test(monkeypatch: pytest.MonkeyPatch) -> None:
    """`tests.run()` spawns `pytest` itself, so the marker is set for the child here."""
    monkeypatch.setenv(NESTED, "1")

    with _planted("assertion_that_fails.py", TESTS_PROBE):
        result = tests.run()

    assert result.ok is False
    assert "test_the_probe_fails_on_purpose" in result.detail


# --- integration: the same bad input fails the real `make verify` ------------------


@outermost_run_only
def test_make_verify_fails_and_names_gate_1() -> None:
    with _planted("unused_import.py", VERIFY_LINT_PROBE):
        result = make_verify(REPO_ROOT)

    assert result.returncode != 0, result.stdout + result.stderr
    assert "FAIL  gate 1  format-and-lint" in result.stdout
    assert "F401" in result.stdout


@outermost_run_only
def test_make_verify_fails_and_names_gate_2() -> None:
    with _planted("mismatched_annotation.py", VERIFY_TYPES_PROBE):
        result = make_verify(REPO_ROOT)

    assert result.returncode != 0, result.stdout + result.stderr
    assert "FAIL  gate 2  types" in result.stdout
    assert "Incompatible types in assignment" in result.stdout


@outermost_run_only
def test_make_verify_fails_and_names_gate_14() -> None:
    with _planted("assertion_that_fails.py", TESTS_PROBE):
        result = make_verify(REPO_ROOT)

    assert result.returncode != 0, result.stdout + result.stderr
    assert "FAIL  gate 14  tests" in result.stdout
    assert "test_the_probe_fails_on_purpose" in result.stdout


@outermost_run_only
def test_concurrent_verify_runs_do_not_collide() -> None:
    """Two runs at once must not unlink each other's probes (T-0002b, H4).

    Every destination above is suffixed with the planting process's id, so a probe
    belongs to exactly one process. With fixed destinations these two runs deleted each
    other's files mid-test: `FileNotFoundError` out of `_planted`'s cleanup, and every
    plant-and-scan proof in this module failing for a reason that was not about the gate
    it was proving.

    Both children carry the nesting marker, so each one's gate 14 skips the tests that
    spawn in turn and the descent still stops one level down.
    """
    with ThreadPoolExecutor(max_workers=2) as pool:
        runs = [pool.submit(make_verify, REPO_ROOT) for _ in range(2)]
        results = [run.result() for run in runs]

    for result in results:
        assert result.returncode == 0, result.stdout + result.stderr
