"""Proof that gate 7 (the module contract checker, DEC-0011) matches and rejects correctly.

Unit tests call ``module_contract.problems_in`` and ``module_contract.module_directories``
directly over a constructed tree under ``tmp_path`` — pure filesystem reads, no registry —
to prove each conformance rule and the walk's scope. Integration tests plant a bad package
into a copy of the harness (``conftest.copied_tree``) and run the real gate over it, proving
the wiring, including that ``src/`` not existing yet is a clean pass rather than a failure.

The walk's scope is DEC-0026 and is the thing most worth testing here: the gate shipped at
T-0006 stopping at the topmost package on a path, which would have checked ``src/engine/``
and skipped every context beneath it.
``test_a_package_nested_inside_a_module_is_checked_too`` is that regression, planted through
the real ``make verify``; ``test_the_walk_finds_every_package_but_a_tests_tree`` is the same
rule stated directly over a constructed tree.

**Mocking: none.** Real files, real ``tools/readme.ai.md``, and — for the ``make verify``
proof — the real ``Makefile`` and runner.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tools.gates import module_contract
from tools.tests.conftest import (
    REPO_ROOT,
    copied_tree,
    gate_result_in,
    make_verify,
    only_gate,
)

_CONFORMING_SECTIONS = (
    "## Purpose\nWhat this does.\n\n"
    "## Context\nWhere it sits.\n\n"
    "## Contract\nWhat it exposes.\n\n"
    "## Invariants enforced here\nNone.\n\n"
    "## Depends on\nNothing.\n\n"
    "## Must not depend on\nNothing.\n\n"
    "## Tests\nSee tests/.\n\n"
    "## How to run it\n`python -m thing`\n\n"
    "## Open questions\nNone.\n"
)


def _write_package(directory: Path, readme_body: str | None) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "__init__.py").write_text("", encoding="utf-8")
    if readme_body is not None:
        (directory / "readme.ai.md").write_text(readme_body, encoding="utf-8")


# --- unit: each conformance rule ----------------------------------------------------


def test_a_package_with_no_readme_fails(tmp_path: Path) -> None:
    _write_package(tmp_path / "pkg", readme_body=None)

    problems = module_contract.problems_in(tmp_path / "pkg")

    assert any("missing" in problem and "readme.ai.md" in problem for problem in problems)


def test_a_package_missing_a_section_fails_naming_it(tmp_path: Path) -> None:
    body = _CONFORMING_SECTIONS.replace("## Contract\nWhat it exposes.\n\n", "")
    _write_package(tmp_path / "pkg", readme_body=body)

    problems = module_contract.problems_in(tmp_path / "pkg")

    assert any("'Contract'" in problem for problem in problems)


def test_a_package_with_sections_out_of_order_fails(tmp_path: Path) -> None:
    body = (
        "## Context\nWhere it sits.\n\n"
        "## Purpose\nWhat this does.\n\n"
        "## Contract\nWhat it exposes.\n\n"
        "## Invariants enforced here\nNone.\n\n"
        "## Depends on\nNothing.\n\n"
        "## Must not depend on\nNothing.\n\n"
        "## Tests\nSee tests/.\n\n"
        "## How to run it\n`python -m thing`\n\n"
        "## Open questions\nNone.\n"
    )
    _write_package(tmp_path / "pkg", readme_body=body)

    problems = module_contract.problems_in(tmp_path / "pkg")

    assert any("out of order" in problem for problem in problems)


def test_a_package_with_an_empty_open_questions_fails(tmp_path: Path) -> None:
    body = _CONFORMING_SECTIONS.replace("## Open questions\nNone.\n", "## Open questions\n")
    _write_package(tmp_path / "pkg", readme_body=body)

    problems = module_contract.problems_in(tmp_path / "pkg")

    assert any("'Open questions'" in problem and "empty" in problem for problem in problems)


# --- unit: the walk's scope (DEC-0026) ----------------------------------------------


def test_the_walk_finds_every_package_but_a_tests_tree(tmp_path: Path) -> None:
    """Every package at any depth; a ``tests/`` tree and what is under it, never."""
    for relative in (
        "outer",
        "outer/inner",
        "outer/inner/deeper",
        "outer/tests",
        "outer/tests/data",
    ):
        _write_package(tmp_path / relative, readme_body=_CONFORMING_SECTIONS)
    (tmp_path / "notapackage").mkdir()
    _write_package(tmp_path / "notapackage" / "under_it", readme_body=_CONFORMING_SECTIONS)

    found = module_contract.module_directories(tmp_path)

    assert found == [
        tmp_path / "notapackage" / "under_it",
        tmp_path / "outer",
        tmp_path / "outer" / "inner",
        tmp_path / "outer" / "inner" / "deeper",
    ]


def test_the_walk_of_a_missing_root_is_empty(tmp_path: Path) -> None:
    assert module_contract.module_directories(tmp_path / "nothing_here") == []


# --- integration -------------------------------------------------------------------


@pytest.mark.integration
def test_a_package_nested_inside_a_module_is_checked_too(tmp_path: Path) -> None:
    """DEC-0026's regression: a bad package *beneath* a conforming one must still fail.

    Under the topmost-only rule this gate shipped with, ``src/good`` was the module root and
    ``src/good/nested`` was never looked at, so ``make verify`` passed over a tree with a
    module carrying no contract at all.
    """
    copy = copied_tree(tmp_path, only_gate(7))
    _write_package(copy / "src" / "good", readme_body=_CONFORMING_SECTIONS)
    _write_package(copy / "src" / "good" / "nested", readme_body=None)

    result = make_verify(copy)

    assert result.returncode != 0, result.stdout + result.stderr
    assert "FAIL  gate 7  module-contract" in result.stdout
    assert "nested" in result.stdout


@pytest.mark.integration
def test_a_tests_tree_inside_a_module_is_not_a_module(tmp_path: Path) -> None:
    """The other half of DEC-0026: a module's own ``tests/`` owes no ``readme.ai.md``."""
    copy = copied_tree(tmp_path)
    _write_package(copy / "src" / "good", readme_body=_CONFORMING_SECTIONS)
    _write_package(copy / "src" / "good" / "tests", readme_body=None)

    result = gate_result_in(copy, "module_contract")

    assert result.ok is True, result.detail


def test_the_gates_package_carries_its_own_contract() -> None:
    """``tools/gates/`` is a module under DEC-0026, and owes a conforming contract."""
    assert module_contract.problems_in(REPO_ROOT / "tools" / "gates") == []


@pytest.mark.integration
def test_make_verify_fails_and_names_gate_7(tmp_path: Path) -> None:
    copy = copied_tree(tmp_path, only_gate(7))
    _write_package(copy / "src" / "bad", readme_body=None)

    result = make_verify(copy)

    assert result.returncode != 0, result.stdout + result.stderr
    assert "FAIL  gate 7  module-contract" in result.stdout
    assert "readme.ai.md is missing" in result.stdout


@pytest.mark.integration
def test_a_directory_without_init_is_skipped(tmp_path: Path) -> None:
    """``notapackage`` alone would leave ``src/`` a root that exists but yields zero
    module directories — the empty-scan case C1 fails closed on (``REVIEW-harness-p0.md``),
    not the skip this test is about. A real, conforming companion package keeps ``src/`` a
    genuine, non-empty scan."""
    copy = copied_tree(tmp_path)
    (copy / "src" / "notapackage").mkdir(parents=True)
    (copy / "src" / "notapackage" / "scratch.py").write_text("x = 1\n", encoding="utf-8")
    _write_package(copy / "src" / "good", readme_body=_CONFORMING_SECTIONS)

    result = gate_result_in(copy, "module_contract")

    assert result.ok is True, result.detail


def test_tools_readme_passes() -> None:
    problems = module_contract.problems_in(REPO_ROOT / "tools")

    assert problems == []


@pytest.mark.integration
def test_the_real_tree_passes() -> None:
    result = module_contract.run()

    assert result.ok is True, result.detail


@pytest.mark.integration
def test_a_missing_src_is_a_clean_pass(tmp_path: Path) -> None:
    """``src/`` does not exist yet at P0; nothing to scan is not a failure."""
    copy = copied_tree(tmp_path)

    result = gate_result_in(copy, "module_contract")

    assert result.ok is True, result.detail


# --- unit: coverage (C1, REVIEW-harness-p0.md) --------------------------------------


def test_an_existing_root_with_no_module_directories_fails_closed(tmp_path: Path) -> None:
    """A scan root that exists but yields zero module directories is not a clean pass —
    it is indistinguishable from a scan that never ran unless it says so."""
    empty_root = tmp_path / "tools"
    empty_root.mkdir()
    (empty_root / "scratch.py").write_text("x = 1\n", encoding="utf-8")

    result = module_contract.verdict([empty_root])

    assert result.ok is False
    assert "0 module directories found under tools/" in result.detail


def test_a_missing_root_stays_a_clean_pass_and_is_not_named(tmp_path: Path) -> None:
    """The other half of the same rule: a root that does not exist is nothing to scan,
    never zero subjects found — ``src/`` must stay green while it does not exist."""
    missing_root = tmp_path / "src"
    present_root = tmp_path / "tools"
    _write_package(present_root, readme_body=_CONFORMING_SECTIONS)

    result = module_contract.verdict([missing_root, present_root])

    assert result.ok is True, result.detail
    assert "1 module directories checked" in result.detail


def test_a_dead_root_beside_a_live_one_still_fails_closed(tmp_path: Path) -> None:
    """A healthy root must not launder a dead one: ``src/`` existing but empty beside a
    ``tools/`` full of packages is exactly the tree the moment ``src/`` is first created
    (C1.1), and this is the case C1 was raised about — the per-root check, not an
    aggregate across all roots, is what catches it."""
    dead_root = tmp_path / "src"
    dead_root.mkdir()
    live_root = tmp_path / "tools"
    _write_package(live_root, readme_body=_CONFORMING_SECTIONS)

    result = module_contract.verdict([dead_root, live_root])

    assert result.ok is False
    assert "0 module directories found under src/" in result.detail
    assert "tools/" not in result.detail


def test_no_root_existing_at_all_says_so(tmp_path: Path) -> None:
    """With nothing to scan at all, the detail must say what happened rather than trail
    off after "under" — a coverage line that stops mid-sentence is not a coverage line."""
    result = module_contract.verdict([tmp_path / "src", tmp_path / "tools"])

    assert result.ok is True, result.detail
    assert result.detail == "no scan root exists under src/, tools/ — nothing to scan"
