"""Proof that gates 1, 2 and 14 can reject (DEC-0016).

A guard that has never rejected anything is indistinguishable from a guard that scans
nothing, and it reads as green forever. Each gate here is fed a deliberately bad input
from ``badfixtures/`` — twice: once directly through the gate's own ``run()``, and once
through the real ``make verify``, which is the only way anyone actually invokes it.

**Mocking: none.** The real ``ruff``, ``mypy`` and ``pytest`` run over a real file. The bad
inputs cannot simply sit in a scanned path, or the repository could never pass its own
verify, so they rest under a directory excluded from every gate in ``pyproject.toml`` and
are copied into place for the duration of one test.

**Why the nesting guard.** Gate 14 runs ``pytest``, so every test in this module spawns a
process that ends up running this module again. Each spawn is therefore marked in the
environment, and a marked run skips these tests: recursion stops one level down, and the
proof still runs at the depth a person or CI invokes it from. The guard lives here, in the
tests, and not as a flag in ``tools/verify.py`` — the runner has exactly one registration
path and gains no test-only surface.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import pytest

from tools.gates import lint, tests, types

REPO_ROOT = Path(__file__).resolve().parents[2]
BAD_FIXTURES = Path(__file__).parent / "badfixtures"

NESTED = "CADGPT_NESTED_VERIFY"
"""Marks a process this module spawned. Also spelled in ``test_verify.py``."""

outermost_run_only = pytest.mark.skipif(
    os.environ.get(NESTED) == "1",
    reason=(
        "already inside a process this suite spawned: gate 14 runs pytest, so these "
        "tests would spawn themselves without bound"
    ),
)

# Where each bad input is planted. Every destination is a path the gate's tool scans and
# a name the repository does not otherwise use.
LINT_PROBE = REPO_ROOT / "tools" / "unused_import_probe.py"
TYPES_PROBE = REPO_ROOT / "tools" / "mismatched_annotation_probe.py"
TESTS_PROBE = REPO_ROOT / "tools" / "tests" / "test_failing_probe.py"


@pytest.fixture(autouse=True)
def _mark_spawned_processes(monkeypatch: pytest.MonkeyPatch) -> None:
    """Everything these tests spawn is one level down and must not spawn in turn."""
    monkeypatch.setenv(NESTED, "1")


@contextmanager
def _planted(fixture: str, destination: Path) -> Iterator[None]:
    """Copy one bad input into a scanned path, and take it away again afterwards."""
    shutil.copy2(BAD_FIXTURES / fixture, destination)
    try:
        yield
    finally:
        destination.unlink()


def _make_verify() -> subprocess.CompletedProcess[str]:
    """Run the real `make verify` over this repository, as a person or CI would."""
    return subprocess.run(
        ["make", "verify", f"PYTHON={sys.executable}"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


# --- unit: the gate itself rejects, and carries its tool's own words ---------------


@outermost_run_only
def test_lint_gate_fails_on_an_unused_import() -> None:
    with _planted("unused_import.py", LINT_PROBE):
        result = lint.run()

    assert result.ok is False
    assert "F401" in result.detail
    assert LINT_PROBE.name in result.detail


@outermost_run_only
def test_types_gate_fails_on_a_mismatched_annotation() -> None:
    with _planted("mismatched_annotation.py", TYPES_PROBE):
        result = types.run()

    assert result.ok is False
    assert "Incompatible types in assignment" in result.detail
    assert TYPES_PROBE.name in result.detail


@outermost_run_only
def test_tests_gate_fails_on_a_failing_test() -> None:
    with _planted("assertion_that_fails.py", TESTS_PROBE):
        result = tests.run()

    assert result.ok is False
    assert "test_the_probe_fails_on_purpose" in result.detail


# --- integration: the same bad input fails the real `make verify` ------------------


@outermost_run_only
def test_make_verify_fails_and_names_gate_1() -> None:
    with _planted("unused_import.py", LINT_PROBE):
        result = _make_verify()

    assert result.returncode != 0, result.stdout + result.stderr
    assert "FAIL  gate 1  format-and-lint" in result.stdout
    assert "F401" in result.stdout


@outermost_run_only
def test_make_verify_fails_and_names_gate_2() -> None:
    with _planted("mismatched_annotation.py", TYPES_PROBE):
        result = _make_verify()

    assert result.returncode != 0, result.stdout + result.stderr
    assert "FAIL  gate 2  types" in result.stdout
    assert "Incompatible types in assignment" in result.stdout


@outermost_run_only
def test_make_verify_fails_and_names_gate_14() -> None:
    with _planted("assertion_that_fails.py", TESTS_PROBE):
        result = _make_verify()

    assert result.returncode != 0, result.stdout + result.stderr
    assert "FAIL  gate 14  tests" in result.stdout
    assert "test_the_probe_fails_on_purpose" in result.stdout
