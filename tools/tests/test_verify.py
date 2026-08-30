"""Tests for the gate registry runner.

Three unit tests over the runner's own logic and three integration tests that invoke the
real `make verify` in a subprocess. No mocking: a runner whose failure path is faked is a
runner whose failure path has never run.
"""

from __future__ import annotations

import io
import os
import subprocess
import sys
from pathlib import Path

import pytest

from tools.verify import REGISTRY, Gate, GateResult, main, run_gates

REPO_ROOT = Path(__file__).resolve().parents[2]

FAILING_GATE_MODULE = """
from tools.verify import Gate, GateResult

GATES = [
    Gate(
        number=99,
        name="deliberately-failing-gate",
        cost=1,
        run=lambda: GateResult(ok=False, detail="this gate fails on purpose"),
    )
]
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
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """--list reports the registry without running anything."""
    (tmp_path / "listed_gates.py").write_text(FAILING_GATE_MODULE, encoding="utf-8")
    monkeypatch.syspath_prepend(str(tmp_path))

    exit_code = main(["--list", "--extra-gate", "listed_gates"])
    out = capsys.readouterr().out

    assert exit_code == 0
    assert "deliberately-failing-gate" in out
    for gate in REGISTRY:
        assert gate.name in out
    assert f"{len(REGISTRY) + 1} gates registered" in out


def test_failing_result_without_detail_is_rejected() -> None:
    """A failure that does not say what failed is not a usable failure."""
    with pytest.raises(ValueError):
        GateResult(ok=False, detail="   ")


# --- integration ------------------------------------------------------------------


def _make_verify(
    extra_gate_dir: Path | None = None, verify_args: str = ""
) -> subprocess.CompletedProcess[str]:
    env = None
    if extra_gate_dir is not None:
        env = dict(os.environ, PYTHONPATH=str(extra_gate_dir))
    return subprocess.run(
        ["make", "verify", f"VERIFY_ARGS={verify_args}", f"PYTHON={sys.executable}"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )


def _with_failing_gate(tmp_path: Path) -> subprocess.CompletedProcess[str]:
    (tmp_path / "meta_failing_gate.py").write_text(
        FAILING_GATE_MODULE, encoding="utf-8"
    )
    return _make_verify(tmp_path, "--extra-gate meta_failing_gate")


def test_make_verify_over_the_real_tree_exits_zero() -> None:
    result = _make_verify()
    assert result.returncode == 0, result.stdout + result.stderr
    assert f"{len(REGISTRY)} gates registered" in result.stdout


def test_make_verify_exits_non_zero_when_a_gate_fails(tmp_path: Path) -> None:
    result = _with_failing_gate(tmp_path)
    assert result.returncode != 0, result.stdout + result.stderr


def test_failing_run_names_the_gate_and_prints_the_registered_count(
    tmp_path: Path,
) -> None:
    result = _with_failing_gate(tmp_path)
    assert "deliberately-failing-gate" in result.stdout
    assert "this gate fails on purpose" in result.stdout
    assert f"{len(REGISTRY) + 1} gates registered, 1 failed" in result.stdout
