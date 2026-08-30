"""Tests for the gate registry runner, and the proof of this suite's nesting guard.

Seven unit tests over the runner's own logic and eight integration tests that invoke a real
process. No mocking: a runner whose failure path is faked is a runner whose failure path
has never run.

The failure proof goes through the **real registration path**. There is no plugin loader
and no injection flag — registering a gate is one ``REGISTRY`` entry plus one module, with
no exception — so the integration tests copy the harness into a temporary tree with
`conftest.copied_tree`, reset and re-register the copied runner's ``REGISTRY`` through that
same list, and run the real `make verify` there.

The copy's registry is **narrowed** rather than added to. Gate 14 runs `pytest`, so a
copied tree that kept the real gates would run this file, which would make another copy
and run `make verify` in it, without bound. Clearing the copied ``REGISTRY`` leaves
exactly the one deliberately failing gate this test is about, and `conftest.only_gate`
leaves exactly the one real gate a proof is about — a claim about gate 14's summary line
pays for gate 14 and not for `ruff` and `mypy` as well. Both go through the copied
``REGISTRY`` itself rather than a flag in `tools/verify.py`: the runner has one
registration path and gains no test-only surface.
`test_make_verify_over_the_real_tree_exits_zero` runs the *real* registry over this
checkout — it is the one test whose subject is the whole registry — so it carries the
nesting marker from `conftest.py` and is skipped one level down.

DEC-0024 asks three things of this module. `run_gates` must print a passing gate's detail,
so a gate that skipped part of its work can say so — two unit tests pin that, one for a gate
with something to report and one for a gate with nothing. The thing that *builds* that
detail must not throw it away —
`test_a_succeeding_command_reports_its_own_last_output_line` runs a real command through the
real `run_tools` and pins the surviving line, and
`test_a_succeeding_commands_summary_comes_from_stdout_not_stderr` pins that it is the tool's
line and not whatever `uv` wrote after it. And the whole chain has to hold at the
outermost real entry point, which is what
`test_a_full_run_is_visibly_different_from_a_nested_one` proves: two real `make verify` runs
over one copied tree, one plain and one marked, whose printed output must differ.

That last one closes the hole T-0002c was written for. Until it existed, the chain was
proven only in its middle: discarding gate 14's success detail in `tools/gates/tests.py`
made a full `make verify` byte-identical to a nested one again while all nineteen tests
passed and `ruff` and `mypy` stayed clean.

The nesting guard itself is proven too, because a guard nobody checks can quietly skip
everything and read as green forever:
`test_nothing_is_skipped_without_the_nesting_marker` runs the suite with the marker removed
and requires no skips, and `test_only_the_spawning_tests_skip_one_level_down` runs it *with*
the marker and pins the skipped node ids by name.
"""

from __future__ import annotations

import io
import re
from pathlib import Path
from xml.etree import ElementTree

import pytest

from tools.gates import run_tools
from tools.tests.conftest import (
    DEPTH,
    REPO_ROOT,
    SPAWNS_A_RE_ENTERING_PROCESS,
    copied_tree,
    depth_from,
    depth_zero_only,
    make_verify,
    only_gate,
    outermost_run_only,
    run_pytest,
)
from tools.verify import REGISTRY, Gate, GateResult, main, run_gates

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


def test_an_unparseable_depth_fails_the_way_too_deep_a_one_does() -> None:
    """A depth counter that is not a number is an unbounded descent, not a depth of 0.

    `conftest.DEPTH_HERE` is what caps this suite's recursion, and `int()` on a value that
    is not a number raises a bare `ValueError` naming neither the variable nor what to do
    about it. Reading it as 0 would be worse: the cap would then be applied to a depth the
    session does not actually have.
    """
    with pytest.raises(RuntimeError) as raised:
        depth_from("two")

    message = str(raised.value)
    assert DEPTH in message
    assert "'two'" in message
    assert "outermost_run_only" in message
    assert "depth_zero_only" in message


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


@outermost_run_only
@pytest.mark.integration
def test_make_verify_over_the_real_tree_exits_zero() -> None:
    result = make_verify(REPO_ROOT)
    assert result.returncode == 0, result.stdout + result.stderr
    assert f"{len(REGISTRY)} gates registered" in result.stdout


@pytest.mark.integration
def test_make_verify_exits_non_zero_when_a_registered_gate_fails(
    tmp_path: Path,
) -> None:
    result = make_verify(copied_tree(tmp_path, FAILING_GATE_REGISTRATION))
    assert result.returncode != 0, result.stdout + result.stderr


@pytest.mark.integration
def test_failing_run_names_the_gate_and_prints_the_registered_count(
    tmp_path: Path,
) -> None:
    result = make_verify(copied_tree(tmp_path, FAILING_GATE_REGISTRATION))
    assert "deliberately-failing-gate" in result.stdout
    assert "this gate fails on purpose" in result.stdout
    assert "1 gates registered, 1 failed" in result.stdout


def _summary_of(output: str) -> str:
    """The last non-empty line of a `pytest -q` run: its counts line."""
    return [line for line in output.splitlines() if line.strip()][-1]


def _counts(word: str, number: int, summary: str) -> bool:
    """Whether `summary` reports exactly `number` of `word`, not a number ending in it.

    `"1 deselected" in summary` also matches `11 deselected`, which would let the count
    this suite is pinning drift upwards unnoticed.
    """
    return re.search(rf"\b{number} {word}\b", summary) is not None


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

    This is the middle of the chain.
    `test_a_full_run_is_visibly_different_from_a_nested_one` is the same property at the
    outermost entry point, where a person reads it.
    """
    result = run_tools(
        [["python", "-c", "print('an earlier line'); print('the last line')"]]
    )

    assert result.ok is True
    assert result.detail != ""
    assert result.detail == "the last line"


_PRINTS_THEN_CHATTERS = (
    "import sys\n"
    "print('the tool reporting what it checked')\n"
    "sys.stderr.write('Installed 12 packages in 23ms\\n')\n"
)
"""A command that summarises on stdout and is then talked over on stderr.

The stderr line is what `uv` really prints when it populates a cold environment, which is
every first run against a freshly copied tree.
"""


def test_a_succeeding_commands_summary_comes_from_stdout_not_stderr() -> None:
    """DEC-0024: the gate's summary is the *tool's* report, not its runner's chatter.

    `run_tools` used to take the last non-empty line of stdout and stderr merged, so
    anything written to stderr after the tool finished became the gate's summary. Observed
    over a cold copied tree: gate 1 reported `Installed 12 packages in 23ms` and, warm,
    `All checks passed!` — the tool's own line displaced by whoever ran it, which is the
    one thing that line exists to carry.

    Failure detail is deliberately not narrowed this way, and this test says nothing about
    it: on a failure both streams are wanted, unedited.
    """
    result = run_tools([["python", "-c", _PRINTS_THEN_CHATTERS]])

    assert result.ok is True
    assert result.detail == "the tool reporting what it checked"


def _gate_14_detail(output: str) -> str:
    """The line `make verify` printed under its passing gate 14, indented by the runner."""
    lines = output.splitlines()
    header = "PASS  gate 14  tests"
    assert header in lines, f"gate 14 did not pass:\n{output}"
    detail = lines[lines.index(header) + 1]
    assert detail.startswith("        "), (
        "gate 14 passed and printed no detail under it, so a run that skipped its proofs "
        f"reads exactly like one that ran them (DEC-0024):\n{output}"
    )
    return detail.strip()


def _passed(summary: str) -> int:
    """How many tests a `pytest` summary line reports as passed."""
    match = re.search(r"(\d+) passed", summary)
    assert match is not None, f"not a pytest summary line: {summary!r}"
    return int(match.group(1))


@depth_zero_only
@pytest.mark.integration
def test_a_full_run_is_visibly_different_from_a_nested_one(tmp_path: Path) -> None:
    """DEC-0024 end to end, at the entry point a person uses (T-0002c, D1).

    The behaviour DEC-0024 was written for is a chain: gate 14 returns `pytest`'s summary
    as its detail, `run_tools` keeps that line, and `run_gates` prints a detail on PASS as
    well as FAIL. Each link had a test. Nothing entered at `make verify` and looked at what
    it printed, so discarding gate 14's success detail in `tools/gates/tests.py` made a full
    run byte-identical to a nested one again while the whole suite stayed green — the silent
    green DEC-0024 exists to make impossible, reproduced inside the mechanism meant to
    prevent it. `CLAUDE.md` §7 requires every behaviour to have one test that enters at the
    outermost real entry point and exits at the real output; this is gate 14's.

    Both runs are the real `make verify` over one copied tree, differing only in whether the
    child carries `CADGPT_NESTED_VERIFY`. The marked one skips the tests that spawn, so it
    reports fewer passes — and must *say* so.

    The copy registers **gate 14 only**. The claim is about gate 14's summary line; `ruff`
    and `mypy` contribute nothing to it and running them here twice bought nothing. It also
    restores the `full.stdout != nested.stdout` assertion below to something that can fail:
    while a success summary came from stdout and stderr merged, the first run against a cold
    copy carried `uv`'s `Installed N packages` in gate 1's detail and the second did not, so
    the two runs differed whatever gate 14 did.

    This test spawns a child with **no** marker, so the marker cannot stop it running
    itself: `depth_zero_only` does. Its unmarked child runs the tests that spawn marked
    children, which is the deepest a correct run of this suite goes.
    """
    copy = copied_tree(tmp_path, only_gate(14))

    full = make_verify(copy, marked=False)
    nested = make_verify(copy, marked=True)

    assert full.returncode == 0, full.stdout + full.stderr
    assert nested.returncode == 0, nested.stdout + nested.stderr
    assert full.stdout != nested.stdout, (
        "a nested `make verify` printed exactly what a full one printed, so a run that "
        f"skipped every proof is indistinguishable from one that ran them:\n{full.stdout}"
    )

    full_detail = _gate_14_detail(full.stdout)
    nested_detail = _gate_14_detail(nested.stdout)
    assert full_detail != nested_detail
    assert "skipped" in nested_detail, nested_detail
    assert _passed(full_detail) > _passed(nested_detail), (
        f"full run reported {full_detail!r}, nested run {nested_detail!r}"
    )


@outermost_run_only
@pytest.mark.integration
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

    DEC-0027 §2 adds a second, independent comparison: the node ids
    `conftest.pytest_collection_modifyitems` actually tagged `spawns_harness` — read via a
    separate `--collect-only -q -m spawns_harness`, which executes nothing and so cannot
    itself spawn anything — must equal the same frozenset. The skip set above is driven by
    each test's own `outermost_run_only`/`depth_zero_only` decorator; this one is driven by
    the hook. Both are meant to name the same eight tests, and this is what stops them
    drifting apart silently.
    """
    report = tmp_path / "one-level-down.xml"
    result = run_pytest(REPO_ROOT, [f"--junit-xml={report}"], marked=True)
    assert result.returncode == 0, result.stdout + result.stderr

    skipped: set[str] = set()
    for case in ElementTree.parse(report).iter("testcase"):
        if case.find("skipped") is None:
            continue
        module = case.get("classname", "").replace(".", "/")
        skipped.add(f"{module}.py::{case.get('name', '')}")

    assert skipped == set(SPAWNS_A_RE_ENTERING_PROCESS)

    marked_result = run_pytest(
        REPO_ROOT, ["--collect-only", "-m", "spawns_harness"], marked=True
    )
    assert marked_result.returncode == 0, marked_result.stdout + marked_result.stderr
    marked = {line.strip() for line in marked_result.stdout.splitlines() if "::" in line}
    assert marked == set(SPAWNS_A_RE_ENTERING_PROCESS), (
        "DEC-0027 §2: the spawns_harness-marked node ids must equal "
        f"SPAWNS_A_RE_ENTERING_PROCESS. Marked: {marked}"
    )


@depth_zero_only
@pytest.mark.integration
def test_nothing_is_skipped_without_the_nesting_marker(
    request: pytest.FixtureRequest,
) -> None:
    """DEC-0016: the guard that bounds this suite ships with a proof of what it does.

    A skip guard nobody checks is the failure it exists to prevent: it can widen until it
    skips everything, and the suite still reads green. So the suite is run in a child with
    the marker removed — the way a person or CI invokes it — and must report no skips at
    all.

    Two tests are deselected from that child: this one and
    `test_a_full_run_is_visibly_different_from_a_nested_one`. They are exactly the tests
    that cannot be their own subject, because each spawns a child with **no** marker, and
    with the marker absent they would spawn themselves again. Both node ids are built from
    the objects rather than written out, so renaming either cannot silently stop deselecting
    it.

    **The deselect is verified before anything is executed** (T-0002b, H3). `--deselect`
    with an id that matches nothing is silently ignored by `pytest` — exit 0, no warning —
    so a drifting id (parametrising a test, or losing the rootdir anchor) would let the
    child run one of them, which would spawn its own child; nested processes were observed
    climbing 8 -> 18 over a minute. The collection-only run below executes no test and so
    can spawn nothing, and its summary must report exactly two deselected tests. A drifting
    id therefore fails here, in hundredths of a second, before the child that would recurse
    is ever started. The real child then asserts the same thing, because a deselect that
    took effect at collection and not in the run would be a different defect with the same
    consequence.
    """
    module = request.node.nodeid.split("::")[0]
    deselected = (
        request.node.nodeid,
        f"{module}::{test_a_full_run_is_visibly_different_from_a_nested_one.__name__}",
    )
    arguments = [argument for node in deselected for argument in ("--deselect", node)]

    collected = run_pytest(REPO_ROOT, [*arguments, "--collect-only"], marked=False)
    assert collected.returncode == 0, collected.stdout + collected.stderr
    collection_summary = _summary_of(collected.stdout)
    assert _counts("deselected", len(deselected), collection_summary), (
        f"--deselect {deselected} did not match both tests, so a child would run one of "
        f"them and spawn its own child: {collection_summary}"
    )

    result = run_pytest(REPO_ROOT, arguments, marked=False)

    assert result.returncode == 0, result.stdout + result.stderr
    summary = _summary_of(result.stdout)
    assert _counts("deselected", len(deselected), summary), summary
    assert "skipped" not in summary, summary
