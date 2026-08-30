"""Tests for the gate registry runner, and the proof of this suite's nesting guard.

Six unit tests over the runner's own logic and four integration tests that invoke a real
process. No mocking: a runner whose failure path is faked is a runner whose failure path
has never run.

The failure proof goes through the **real registration path**. There is no plugin loader
and no injection flag — registering a gate is one ``REGISTRY`` entry plus one module, with
no exception — so the integration tests copy the repository's `Makefile`, `pyproject.toml`
and `tools/` into a temporary tree, reset and re-register the copied runner's ``REGISTRY``
through that same list, and run the real `make verify` there.

The copy's registry is **reset** rather than added to. Gate 14 runs `pytest`, so a copied
tree that kept the real gates would run this file, which would make another copy and run
`make verify` in it, without bound. Clearing the copied ``REGISTRY`` leaves exactly the one
deliberately failing gate this test is about, and the reset lives here rather than as a
flag in `tools/verify.py`: the runner has one registration path and gains no test-only
surface. `test_make_verify_over_the_real_tree_exits_zero` runs the *real* registry, so it
carries the nesting marker from `conftest.py` and is skipped one level down.

DEC-0024 asks two things of this module. `run_gates` must print a passing gate's detail, so
a gate that skipped part of its work can say so — two unit tests pin that, one for a gate
with something to report and one for a gate with nothing. And the nesting guard itself must
be proven, because a guard nobody checks can quietly skip everything and read as green
forever; `test_nothing_is_skipped_without_the_nesting_marker` is that proof.
"""

from __future__ import annotations

import io
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from tools.tests.conftest import NESTED, make_verify, outermost_run_only
from tools.verify import REGISTRY, Gate, GateResult, main, run_gates

REPO_ROOT = Path(__file__).resolve().parents[2]

FAILING_GATE_REGISTRATION = """

REGISTRY.clear()
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


def test_a_passing_gate_prints_a_detail_it_has_something_to_say_in() -> None:
    """DEC-0024: a run that skipped its proofs must not read like one that ran them."""
    skipping_gate = Gate(
        number=14,
        name="tests",
        cost=3,
        run=lambda: GateResult(ok=True, detail="6 passed, 7 skipped in 0.42s"),
    )
    out = io.StringIO()

    assert run_gates([skipping_gate], out) is True
    assert out.getvalue() == (
        "PASS  gate 14  tests\n"
        "        6 passed, 7 skipped in 0.42s\n"
        "1 gates registered, 0 failed\n"
    )


def test_a_passing_gate_with_an_empty_detail_prints_only_its_own_line() -> None:
    """A gate with nothing to report stays silent, so a clean run stays readable."""
    out = io.StringIO()

    assert run_gates([_passing(1, "quiet-gate", 1, [])], out) is True
    assert out.getvalue() == ("PASS  gate 1  quiet-gate\n1 gates registered, 0 failed\n")


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


@outermost_run_only
def test_make_verify_over_the_real_tree_exits_zero() -> None:
    result = make_verify(REPO_ROOT)
    assert result.returncode == 0, result.stdout + result.stderr
    assert f"{len(REGISTRY)} gates registered" in result.stdout


def test_make_verify_exits_non_zero_when_a_registered_gate_fails(
    tmp_path: Path,
) -> None:
    result = make_verify(_tree_with_one_failing_gate_registered(tmp_path))
    assert result.returncode != 0, result.stdout + result.stderr


def test_failing_run_names_the_gate_and_prints_the_registered_count(
    tmp_path: Path,
) -> None:
    result = make_verify(_tree_with_one_failing_gate_registered(tmp_path))
    assert "deliberately-failing-gate" in result.stdout
    assert "this gate fails on purpose" in result.stdout
    assert "1 gates registered, 1 failed" in result.stdout


@outermost_run_only
def test_nothing_is_skipped_without_the_nesting_marker(
    request: pytest.FixtureRequest,
) -> None:
    """DEC-0016: the guard that bounds this suite ships with a proof of what it does.

    A skip guard nobody checks is the failure it exists to prevent: it can widen until it
    skips everything, and the suite still reads green. So the suite is run in a child with
    the marker removed — the way a person or CI invokes it — and must report no skips at
    all.

    This one test is deselected from that child. It is the single test that cannot be its
    own subject: with the marker absent it would spawn itself again, which is exactly the
    descent every other guard here exists to stop. The node id is taken from pytest rather
    than written out, so renaming this test cannot silently stop deselecting it.
    """
    unmarked = {name: value for name, value in os.environ.items() if name != NESTED}
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "tools/tests/",
            "-q",
            "--deselect",
            request.node.nodeid,
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
        env=unmarked,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    summary = [line for line in result.stdout.splitlines() if line.strip()][-1]
    assert "skipped" not in summary, summary
