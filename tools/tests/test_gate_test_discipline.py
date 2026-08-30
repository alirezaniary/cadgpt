"""Tests for gate 15 (test balance, DEC-0010) and gate 16 (determinism, DEC-0027).

Unit, over gate 15's own rule (`test_balance.verdict`) — a constructed list of
`ModuleCounts` proves each rule directly, with no filesystem or subprocess involved:
- a module with a real skew (5 unit / 0 integration) fails and is named;
- a module at 50/50 passes;
- a module with only 2 tests is reported but not failed — a ratio over so few tests is
  noise, per `docs/roadmap/tasks/T-0007-test-discipline-gates.md`;
- the per-module table is produced on PASS as well as FAIL (DEC-0024).

Integration, over gate 16's own rule (`determinism.execute`/`verdict`) — real, small,
constructed fixture directories, never the real `tools/tests/` tree: a two-line pytest
project run through the real `uv run --group dev pytest` subprocess, twice, with the real
`PYTHONHASHSEED`/`-p randomly` machinery gate 16 itself uses. Pointing at a real fixture
this way means these proofs never re-enter this suite — `determinism.execute` accepts a
`cwd` precisely so a proof of gate 16's own rule does not have to run over the tree it
is defined in.

**Mocking: none.**
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from tools.gates import determinism, test_balance
from tools.gates.determinism import RunResult
from tools.gates.test_balance import ModuleCounts
from tools.tests.conftest import (
    copied_tree,
    make_verify,
    only_gate,
    outermost_run_only,
)

# --- unit: gate 15 -----------------------------------------------------------------


def test_a_skewed_module_fails_and_is_named() -> None:
    """5 unit / 0 integration is 0% integration, outside the 40-60% band, and the module
    has enough tests (5 >= MIN_TESTS_TO_ENFORCE) for the band to be enforced."""
    result = test_balance.verdict([ModuleCounts(module="tools", unit=5, integration=0)])

    assert result.ok is False
    assert "tools" in result.detail
    assert "OUTSIDE 40-60% band" in result.detail


def test_a_balanced_module_passes() -> None:
    """3 unit / 3 integration is exactly 50%, inside the band."""
    result = test_balance.verdict([ModuleCounts(module="tools", unit=3, integration=3)])

    assert result.ok is True


def test_a_module_with_too_few_tests_is_reported_not_failed() -> None:
    """2 tests total is fewer than MIN_TESTS_TO_ENFORCE (4): the ratio (0%, well outside
    the band) is reported in the table but does not fail the gate."""
    result = test_balance.verdict([ModuleCounts(module="tools", unit=2, integration=0)])

    assert result.ok is True
    assert "tools" in result.detail
    assert "not enforced" in result.detail


def test_the_per_module_table_is_produced_even_on_success() -> None:
    """DEC-0024: a passing run still says what it checked, so a run that checked less
    cannot read the same as one that checked everything."""
    result = test_balance.verdict(
        [
            ModuleCounts(module="tools", unit=3, integration=3),
            ModuleCounts(module="tools/gates", unit=2, integration=2),
        ]
    )

    assert result.ok is True
    assert result.detail != ""
    assert "tools:" in result.detail
    assert "tools/gates:" in result.detail


# --- unit: gate 16's M1 fix (REVIEW-harness-p0.md) ----------------------------------


def test_an_unmatched_summary_line_is_deselected_count_none() -> None:
    """A parse failure is not the same claim as `0 deselected` — it means this run cannot
    say what it skipped, not that it skipped nothing."""
    assert determinism._deselected_count("65 passed in 3s") is None


def test_a_matched_summary_line_still_parses() -> None:
    assert determinism._deselected_count("57 passed, 8 deselected in 9s") == 8


def test_an_unknown_deselected_count_fails_and_says_unknown() -> None:
    """`verdict` must not render an unparsed count as `0 deselected` — the strongest claim
    the gate can make ("nothing was skipped") for exactly the case where it knows the
    least. It renders `unknown` and fails instead (M1)."""
    first = RunResult(passed=frozenset({"a"}), failed=frozenset(), deselected=None)
    second = RunResult(passed=frozenset({"a"}), failed=frozenset(), deselected=3)

    result = determinism.verdict(first, second, seeds=("1", "2"))

    assert result.ok is False
    assert "unknown" in result.detail
    assert "0 deselected" not in result.detail


# --- integration: gate 16 -----------------------------------------------------------


@pytest.mark.integration
def test_a_hash_seed_dependent_test_makes_determinism_fail_and_is_named(
    tmp_path: Path,
) -> None:
    """A real, tiny fixture whose one test's outcome is pinned to `PYTHONHASHSEED` (not
    real hash randomisation, which is nondeterministic to construct a proof from —
    `CLAUDE.md` §7 forbids a proof with no pinned seed). Gate 16 uses two different
    `PYTHONHASHSEED`s by design (DEC-0027), so this test disagrees between the two runs
    every time, and `verdict` must fail and name it.
    """
    fixture = tmp_path / "hashy"
    fixture.mkdir()
    (fixture / "test_hashy.py").write_text(
        "import os\n\n\ndef test_seed_dependent():\n"
        '    assert os.environ.get("PYTHONHASHSEED") == "1"\n',
        encoding="utf-8",
    )

    first = determinism.execute(
        hash_seed="1", random_seed=1_000_003, report=tmp_path / "a.xml", cwd=fixture
    )
    second = determinism.execute(
        hash_seed="2", random_seed=2_000_017, report=tmp_path / "b.xml", cwd=fixture
    )
    result = determinism.verdict(first, second, seeds=("1", "2"))

    assert result.ok is False
    assert "test_hashy.py::test_seed_dependent" in result.detail


@pytest.mark.integration
def test_a_stable_fixture_passes_and_reports_what_it_deselected(tmp_path: Path) -> None:
    """A real, tiny fixture with two ordinary tests and one `spawns_harness`-marked test
    that would raise if it ever ran. Gate 16 must deselect it in both runs, agree on the
    other two, and report the deselected count on PASS (DEC-0024, DEC-0027 §4)."""
    fixture = tmp_path / "stable"
    fixture.mkdir()
    (fixture / "test_stable.py").write_text(
        "import pytest\n\n\n"
        "def test_ok():\n    assert True\n\n\n"
        "def test_ok2():\n    assert 1 + 1 == 2\n\n\n"
        "@pytest.mark.spawns_harness\n"
        "def test_spawner():\n    raise RuntimeError('must be deselected')\n",
        encoding="utf-8",
    )

    first = determinism.execute(
        hash_seed="1", random_seed=1_000_003, report=tmp_path / "a.xml", cwd=fixture
    )
    second = determinism.execute(
        hash_seed="2", random_seed=2_000_017, report=tmp_path / "b.xml", cwd=fixture
    )
    result = determinism.verdict(first, second, seeds=("1", "2"))

    assert result.ok is True
    assert "2 tests, 2 runs, seeds 1/2, agreed" in result.detail
    assert "1 deselected (spawns_harness)" in result.detail


@pytest.mark.integration
def test_a_fresh_copy_of_the_harness_lists_nine_gates(tmp_path: Path) -> None:
    """`python -m tools.verify --list` prints every registered gate without running any
    of them — cheap, and listing spawns nothing that re-enters this suite.

    Run against a *fresh, unedited* `conftest.copied_tree`, not `sys.executable` against
    this checkout directly: `copied_tree` always rebuilds `tools/verify.py` from the text
    before its `REGISTRY_EDIT` marker, so it restores the full, original `REGISTRY`
    regardless of how many levels of narrowing sit between this test and the tree it was
    collected from. A version of this proof that asserted against `REPO_ROOT` directly
    failed the moment it was collected inside another proof's narrowed copy — not because
    the registry was wrong, but because the assertion assumed it was never anyone else's
    copy to narrow.
    """
    copy = copied_tree(tmp_path)
    completed = subprocess.run(
        [sys.executable, "-m", "tools.verify", "--list"],
        cwd=copy,
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert "9 gates registered" in completed.stdout
    assert "gate 15  cost 1  test-balance" in completed.stdout
    assert "gate 16  cost 2  determinism" in completed.stdout


# --- integration: H1 — gates 15 and 16 reject through the shipped registration path --


@pytest.mark.integration
@outermost_run_only
def test_a_skewed_module_fails_gate_15_through_make_verify(tmp_path: Path) -> None:
    """H1 (`REVIEW-harness-p0.md`): gate 15's rule was proven only by calling `verdict`
    directly with constructed `ModuleCounts`. This plants a real, skewed module — five
    unit tests, no integration tests, enough to be enforced — where the gate really
    collects from, and proves the real `test_balance.run()` reaches it through `REGISTRY`
    and fails a real `make verify`.
    """
    copy = copied_tree(tmp_path, only_gate(15))
    module = copy / "src" / "skewed"
    module.mkdir(parents=True)
    (module / "__init__.py").write_text("", encoding="utf-8")
    tests_dir = module / "tests"
    tests_dir.mkdir()
    (tests_dir / "test_skewed.py").write_text(
        "\n\n\n".join(f"def test_unit_{i}() -> None:\n    assert True" for i in range(5))
        + "\n",
        encoding="utf-8",
    )

    result = make_verify(copy)

    assert result.returncode != 0, result.stdout + result.stderr
    assert "FAIL  gate 15  test-balance" in result.stdout
    assert "src/skewed" in result.stdout
    assert "OUTSIDE 40-60% band" in result.stdout


@pytest.mark.integration
@outermost_run_only
def test_a_hash_seed_dependent_test_fails_gate_16_through_make_verify(
    tmp_path: Path,
) -> None:
    """H1 (`REVIEW-harness-p0.md`): gate 16's rule was proven only by calling
    `execute`/`verdict` directly against a small fixture pointed at by `cwd`. This plants a
    real, hash-seed-dependent test inside the copy's own `tools/tests/` — where the
    registered gate, whose `cwd` defaults to its own tree, really collects from — and
    proves the real `determinism.run()` reaches it through `REGISTRY` and fails a real
    `make verify`.
    """
    copy = copied_tree(tmp_path, only_gate(16))
    (copy / "tools" / "tests" / "test_hashy_probe.py").write_text(
        "import os\n\n\ndef test_seed_dependent() -> None:\n"
        '    assert os.environ.get("PYTHONHASHSEED") == "1"\n',
        encoding="utf-8",
    )

    result = make_verify(copy)

    assert result.returncode != 0, result.stdout + result.stderr
    assert "FAIL  gate 16  determinism" in result.stdout
    assert "test_seed_dependent" in result.stdout
