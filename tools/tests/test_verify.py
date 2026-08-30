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

Both of those were proven only halfway until T-0002b, and the two integration tests it added
close the halves:

* the printing pins were over `GateResult`s built by hand, so nothing produced one.
  Replacing `_summary_line`'s body with `return ""` restored exactly the byte-identical
  silent green DEC-0024 was written to make impossible, and the whole suite stayed green.
  `test_a_succeeding_command_reports_its_own_last_output_line` runs a real command
  through the real `run_tools` and fails on that edit.
* `test_nothing_is_skipped_without_the_nesting_marker` runs its child with the marker
  removed, so every `skipif` is False by construction and only an *unconditional* skip
  could ever be caught. The skip set could widen back to anything.
  `test_only_the_spawning_tests_skip_one_level_down` runs a child *with* the marker and pins
  the skipped node ids by name.
"""

from __future__ import annotations

import io
import os
import shutil
import subprocess
import sys
from pathlib import Path
from xml.etree import ElementTree

import pytest

from tools.gates import run_tools
from tools.tests.conftest import (
    NESTED,
    SPAWNS_A_RE_ENTERING_PROCESS,
    make_verify,
    outermost_run_only,
)
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


TRANSIENT = shutil.ignore_patterns("__pycache__", "*_probe_*.py")
"""What a copy of `tools/` must not pick up.

`test_gates_static.py` plants its bad inputs as `*_probe_<pid>.py` inside the real tree
for the length of one test, so a concurrent run's probe can appear and vanish while this
copy is walking. `shutil.copytree` enumerates first and copies second, and a file that
disappears in between makes it raise `shutil.Error` — a second shape of the corruption
T-0002b's §4 is about, in the copy rather than in `_planted`'s cleanup. Neither a probe
nor a `__pycache__` entry belongs in the copy anyway: the copy exists to run one
deliberately failing gate.
"""


def _tree_with_one_failing_gate_registered(tmp_path: Path) -> Path:
    """Copy the repository's harness and register a failing gate the documented way."""
    copy = tmp_path / "repo"
    copy.mkdir()
    shutil.copy2(REPO_ROOT / "Makefile", copy / "Makefile")
    shutil.copy2(REPO_ROOT / "pyproject.toml", copy / "pyproject.toml")
    shutil.copytree(REPO_ROOT / "tools", copy / "tools", ignore=TRANSIENT)
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


def _summary_of(output: str) -> str:
    """The last non-empty line of a `pytest -q` run: its counts line."""
    return [line for line in output.splitlines() if line.strip()][-1]


def test_a_succeeding_command_reports_its_own_last_output_line() -> None:
    """DEC-0024, at the place the detail is actually produced (T-0002b, H1).

    `run_gates` printing a non-empty detail on PASS is worth nothing if the thing that
    builds the detail returns nothing. Replacing `_summary_line`'s body with `return ""`
    left every other test in this suite green while making a `make verify` that skipped
    all its proofs byte-identical to one that ran them — the exact silent green DEC-0024
    exists to prevent.

    So this asserts on a real `GateResult` from the real `run_tools`, over a real command
    that really succeeds, and pins that the surviving line is that command's own last
    output line rather than its first or nothing at all.
    """
    result = run_tools(
        [["python", "-c", "print('an earlier line'); print('the last line')"]]
    )

    assert result.ok is True
    assert result.detail != ""
    assert result.detail == "the last line"


@outermost_run_only
def test_only_the_spawning_tests_skip_one_level_down(tmp_path: Path) -> None:
    """The skip set is pinned by name, not merely bounded (T-0002b, H2).

    `test_nothing_is_skipped_without_the_nesting_marker` below runs its child with the
    marker *removed*, which makes every `skipif` in this suite False by construction: it
    can only ever catch an unconditional skip. Putting `outermost_run_only` back on the
    `ruff` and `mypy` tests — the precise regression T-0002a removed — left it green while
    a marked run skipped half the suite.

    This runs a child *with* the marker, which is the state the guard is about, and
    compares the node ids that really skipped against `SPAWNS_A_RE_ENTERING_PROCESS`.
    Widening the set or narrowing it then fails, naming the difference. The child reports
    through JUnit XML because `pytest`'s own short summary gives a file and a line number,
    not a node id, and a proof pinned to line numbers breaks on every edit above it.

    The child is bounded by the marker it carries: every test that would spawn again is
    skipped in it, which is the same set this test is checking.
    """
    report = tmp_path / "one-level-down.xml"
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "tools/tests/",
            "-q",
            "-p",
            "no:cacheprovider",
            f"--junit-xml={report}",
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
        env={**os.environ, NESTED: "1"},
    )
    assert result.returncode == 0, result.stdout + result.stderr

    skipped: set[str] = set()
    for case in ElementTree.parse(report).iter("testcase"):
        if case.find("skipped") is None:
            continue
        module = case.get("classname", "").replace(".", "/")
        skipped.add(f"{module}.py::{case.get('name', '')}")

    assert skipped == set(SPAWNS_A_RE_ENTERING_PROCESS)


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

    **The deselect is verified before anything is executed** (T-0002b, H3). `--deselect`
    with an id that matches nothing is silently ignored by `pytest` — exit 0, no warning —
    so a drifting id (parametrising this test, or losing the rootdir anchor) would let the
    child run this test, which would spawn its own child, without bound; nested processes
    were observed climbing 8 -> 18 over a minute. The collection-only run below executes no
    test and so can spawn nothing, and its summary must report exactly one deselected test.
    A drifting id therefore fails here, in hundredths of a second, before the child that
    would recurse is ever started. The real child then asserts the same thing, because a
    deselect that took effect at collection and not in the run would be a different defect
    with the same consequence.
    """
    unmarked = {name: value for name, value in os.environ.items() if name != NESTED}
    invocation = [
        sys.executable,
        "-m",
        "pytest",
        "tools/tests/",
        "-q",
        "--deselect",
        request.node.nodeid,
    ]

    collected = subprocess.run(
        [*invocation, "--collect-only"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
        env=unmarked,
    )
    assert collected.returncode == 0, collected.stdout + collected.stderr
    collection_summary = _summary_of(collected.stdout)
    assert "(1 deselected)" in collection_summary, (
        f"--deselect {request.node.nodeid} matched nothing, so a child would run this "
        f"test and spawn its own child without bound: {collection_summary}"
    )

    result = subprocess.run(
        invocation,
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
        env=unmarked,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    summary = _summary_of(result.stdout)
    assert "1 deselected" in summary, summary
    assert "skipped" not in summary, summary
