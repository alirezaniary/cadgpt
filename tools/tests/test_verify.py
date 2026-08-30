"""Tests for the gate registry runner.

Four unit tests over the runner's own logic and three integration tests that invoke the
real `make verify` in a subprocess. No mocking: a runner whose failure path is faked is a
runner whose failure path has never run.

The failure proof goes through the **real registration path**. There is no plugin loader
and no injection flag — registering a gate is one ``REGISTRY`` entry plus one module, with
no exception — so the integration tests copy the repository's `Makefile`, `pyproject.toml`
and `tools/` into a temporary tree, append one literal ``REGISTRY.append(Gate(...))`` block
to the copied runner, and run the real `make verify` there.
"""

from __future__ import annotations

import io
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from tools.verify import REGISTRY, Gate, GateResult, main, run_gates

REPO_ROOT = Path(__file__).resolve().parents[2]

FAILING_GATE_REGISTRATION = """

REGISTRY.append(
    Gate(
        number=99,
        name="deliberately-failing-gate",
        cost=1,
        run=lambda: GateResult(ok=False, detail="this gate fails on purpose"),
    )
)
"""


def _passing(number: int, name: str, cost: int, log: list[str]) -> Gate:
    def run() -> GateResult:
        log.append(name)
        return GateResult(ok=True, detail="")

    return Gate(number=number, name=name, cost=cost, run=run)


# --- unit -------------------------------------------------------------------------


def test_gates_run_cheapest_first() -> None:
    """The runner sorts by cost so a broken change fails in seconds, not minutes."""
    log: list[str] = []
    gates = [
        _passing(3, "minutes", 3, log),
        _passing(1, "seconds", 1, log),
        _passing(2, "tens-of-seconds", 2, log),
    ]

    assert run_gates(gates, io.StringIO()) is True
    assert log == ["seconds", "tens-of-seconds", "minutes"]


def test_list_exits_zero_and_names_every_registered_gate(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """--list reports the registry without running anything."""
    exit_code = main(["--list"])
    out = capsys.readouterr().out

    assert exit_code == 0
    for gate in REGISTRY:
        assert gate.name in out
    assert f"{len(REGISTRY)} gates registered" in out


def test_failing_result_without_detail_is_rejected() -> None:
    """A failure that does not say what failed is not a usable failure."""
    with pytest.raises(ValueError):
        GateResult(ok=False, detail="   ")


def test_a_raising_gate_fails_and_the_gates_after_it_still_run() -> None:
    """A gate whose tool is missing must not abort the run and hide the rest."""
    log: list[str] = []

    def explode() -> GateResult:
        log.append("raiser")
        raise FileNotFoundError("ruff: command not found")

    gates = [
        Gate(number=1, name="raising-gate", cost=1, run=explode),
        _passing(2, "gate-after-the-raiser", 2, log),
    ]
    out = io.StringIO()

    assert run_gates(gates, out) is False
    printed = out.getvalue()
    assert "FAIL  gate 1  raising-gate" in printed
    assert "FileNotFoundError" in printed
    assert "ruff: command not found" in printed
    assert "Traceback (most recent call last)" in printed
    assert log == ["raiser", "gate-after-the-raiser"]
    assert "2 gates registered, 1 failed" in printed


# --- integration ------------------------------------------------------------------


def _make_verify(cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["make", "verify", f"PYTHON={sys.executable}"],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )


def _tree_with_one_failing_gate_registered(tmp_path: Path) -> Path:
    """Copy the repository's harness and register a failing gate the documented way."""
    copy = tmp_path / "repo"
    copy.mkdir()
    shutil.copy2(REPO_ROOT / "Makefile", copy / "Makefile")
    shutil.copy2(REPO_ROOT / "pyproject.toml", copy / "pyproject.toml")
    shutil.copytree(REPO_ROOT / "tools", copy / "tools")
    with (copy / "tools" / "verify.py").open("a", encoding="utf-8") as runner:
        runner.write(FAILING_GATE_REGISTRATION)
    return copy


def test_make_verify_over_the_real_tree_exits_zero() -> None:
    result = _make_verify(REPO_ROOT)
    assert result.returncode == 0, result.stdout + result.stderr
    assert f"{len(REGISTRY)} gates registered" in result.stdout


def test_make_verify_exits_non_zero_when_a_registered_gate_fails(
    tmp_path: Path,
) -> None:
    result = _make_verify(_tree_with_one_failing_gate_registered(tmp_path))
    assert result.returncode != 0, result.stdout + result.stderr


def test_failing_run_names_the_gate_and_prints_the_registered_count(
    tmp_path: Path,
) -> None:
    result = _make_verify(_tree_with_one_failing_gate_registered(tmp_path))
    assert "deliberately-failing-gate" in result.stdout
    assert "this gate fails on purpose" in result.stdout
    assert f"{len(REGISTRY) + 1} gates registered, 1 failed" in result.stdout
