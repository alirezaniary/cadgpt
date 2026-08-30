"""Gate 16 — determinism (DEC-0027).

Runs the suite twice — a different `PYTHONHASHSEED` and a different collection order each
time — and fails if the two runs disagree about which tests passed. The eight tests that
spawn a process re-entering this harness carry a `spawns_harness` marker and are deselected
from both runs (`-m "not spawns_harness"`, DEC-0027 §1): including them would spend
roughly 8.6 of this gate's minutes re-running the harness's own proof of its scaffolding,
the exact allocation DEC-0025 exists to stop. This module does not import
`tools.tests.conftest.SPAWNS_A_RE_ENTERING_PROCESS` — a gate must not depend on the test
suite it checks (`tools/gates/readme.ai.md`'s Must-not-depend-on) — so the two are tied
together only by `tools/tests/test_verify.py`'s own assertion that the marked set equals
that frozenset.

Order is varied for real by `pytest-randomly` (DEC-0027 §3, added to the `dev` group).
`[tool.pytest.ini_options].addopts` carries `-p no:randomly` so every *other* run — gate
14, a developer's plain `pytest`, every copied-tree proof in `tools/tests/` — stays exactly
as order-stable as it always was; this gate is the only caller that turns randomisation
back on, with two different seeds.
"""

from __future__ import annotations

import os
import re
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING
from xml.etree import ElementTree

from tools.gates import REPO_ROOT

if TYPE_CHECKING:
    from tools.verify import GateResult

DESELECT_MARKER = "spawns_harness"

_SEEDS: tuple[tuple[str, int], ...] = (("1", 1_000_003), ("2", 2_000_017))
"""Two (`PYTHONHASHSEED`, `pytest-randomly` seed) pairs. Fixed rather than truly random —
`CLAUDE.md` §7 forbids randomness with no pinned seed — different from each other, which is
all DEC-0027 asks, and reproducible run to run."""

_DESELECTED_RE = re.compile(r"(\d+) deselected")


@dataclass(frozen=True)
class RunResult:
    """One pytest run's outcome: which tests passed, which failed, and how many were
    deselected by the `spawns_harness` filter."""

    passed: frozenset[str]
    failed: frozenset[str]
    deselected: int


def verdict(first: RunResult, second: RunResult, seeds: tuple[str, str]) -> GateResult:
    """The whole rule, over two already-computed runs — a constructed pair of
    `RunResult`s proves it directly, with no subprocess involved.

    Disagreement is a test whose pass/fail outcome differs between the two runs. `detail`
    names every one of them on FAIL, and reports how many tests ran, both seeds and how
    many were deselected on PASS too (DEC-0024, DEC-0027 §4) — a run that deselected part
    of the suite says so whether or not it agreed with itself.
    """
    from tools.verify import GateResult

    disagreed = sorted((first.passed & second.failed) | (first.failed & second.passed))
    if disagreed:
        return GateResult(
            ok=False,
            detail=(
                f"disagreed between seeds {seeds[0]}/{seeds[1]}: " + ", ".join(disagreed)
            ),
        )
    total = len(first.passed) + len(first.failed)
    return GateResult(
        ok=True,
        detail=(
            f"{total} tests, 2 runs, seeds {seeds[0]}/{seeds[1]}, agreed; "
            f"{first.deselected} deselected ({DESELECT_MARKER})"
        ),
    )


def _outcomes(report: Path) -> tuple[frozenset[str], frozenset[str]]:
    """The passed and failed node ids in a JUnit report, rebuilt from `classname` and
    `name` the way `tools/tests/test_verify.py` already does, so both modules read the
    same shape of id from the same kind of report."""
    passed: set[str] = set()
    failed: set[str] = set()
    for case in ElementTree.parse(report).iter("testcase"):
        module = case.get("classname", "").replace(".", "/")
        node_id = f"{module}.py::{case.get('name', '')}"
        if case.find("failure") is not None or case.find("error") is not None:
            failed.add(node_id)
        else:
            passed.add(node_id)
    return frozenset(passed), frozenset(failed)


def _deselected_count(stdout: str) -> int:
    match = _DESELECTED_RE.search(stdout)
    return int(match.group(1)) if match else 0


def execute(
    *, hash_seed: str, random_seed: int, report: Path, cwd: Path = REPO_ROOT
) -> RunResult:
    """Run the suite in `cwd` once, for real, with `hash_seed`, `random_seed` and
    `spawns_harness` deselected. Never mocked: a real `pytest` subprocess, reported
    through a real JUnit report.

    `cwd` defaults to this repository, which is what the registered gate always uses;
    a test proving this module's own rule points it at a small constructed fixture
    directory instead, so the harness is never re-entered by a proof of this gate.
    """
    command = [
        "uv",
        "run",
        "--group",
        "dev",
        "pytest",
        "-m",
        f"not {DESELECT_MARKER}",
        "-p",
        "randomly",
        f"--randomly-seed={random_seed}",
        f"--junit-xml={report}",
        "-q",
    ]
    completed = subprocess.run(
        command,
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
        env={**os.environ, "PYTHONHASHSEED": hash_seed},
    )
    if not report.exists():
        raise RuntimeError(
            f"$ {' '.join(command)} (cwd={cwd})\n"
            f"exited {completed.returncode}, no JUnit report produced:\n"
            f"{completed.stdout}{completed.stderr}"
        )
    passed, failed = _outcomes(report)
    return RunResult(
        passed=passed, failed=failed, deselected=_deselected_count(completed.stdout)
    )


def run() -> GateResult:
    """Gate 16. Runs `tools/tests/` twice for real, with `spawns_harness` deselected, a
    different `PYTHONHASHSEED` and a different collection order each time, and fails if
    the two runs disagree about any test's outcome (DEC-0027)."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        (hash_a, rand_a), (hash_b, rand_b) = _SEEDS
        first = execute(hash_seed=hash_a, random_seed=rand_a, report=tmp_path / "a.xml")
        second = execute(hash_seed=hash_b, random_seed=rand_b, report=tmp_path / "b.xml")
    return verdict(first, second, seeds=(hash_a, hash_b))
