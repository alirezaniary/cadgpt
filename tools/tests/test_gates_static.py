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
"""

from __future__ import annotations

import shutil
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import pytest

from tools.gates import lint, tests, types
from tools.tests.conftest import NESTED, make_verify, outermost_run_only

REPO_ROOT = Path(__file__).resolve().parents[2]
BAD_FIXTURES = Path(__file__).parent / "badfixtures"

# Where each bad input is planted. Every destination is a path the gate's tool scans and
# a name the repository does not otherwise use — one per test, never shared.
LINT_PROBE = REPO_ROOT / "tools" / "unused_import_probe.py"
TYPES_PROBE = REPO_ROOT / "tools" / "mismatched_annotation_probe.py"
TESTS_PROBE = REPO_ROOT / "tools" / "tests" / "test_failing_probe.py"
VERIFY_LINT_PROBE = REPO_ROOT / "tools" / "unused_import_verify_probe.py"
VERIFY_TYPES_PROBE = REPO_ROOT / "tools" / "mismatched_annotation_verify_probe.py"


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
