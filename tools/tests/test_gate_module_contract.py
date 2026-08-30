"""Proof that gate 7 (the module contract checker, DEC-0011) matches and rejects correctly.

Unit tests call ``module_contract.problems_in`` directly over a constructed package
directory under ``tmp_path`` — pure filesystem reads, no registry — to prove each
conformance rule. Integration tests plant a bad package into a copy of the harness
(``conftest.copied_tree``) and run the real gate over it, proving the wiring, including
that ``src/`` not existing yet is a clean pass rather than a failure.

**Mocking: none.** Real files, real ``tools/readme.ai.md``, and — for the ``make verify``
proof — the real ``Makefile`` and runner.
"""

from __future__ import annotations

from pathlib import Path

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


# --- integration -------------------------------------------------------------------


def test_make_verify_fails_and_names_gate_7(tmp_path: Path) -> None:
    copy = copied_tree(tmp_path, only_gate(7))
    _write_package(copy / "src" / "bad", readme_body=None)

    result = make_verify(copy)

    assert result.returncode != 0, result.stdout + result.stderr
    assert "FAIL  gate 7  module-contract" in result.stdout
    assert "readme.ai.md is missing" in result.stdout


def test_a_directory_without_init_is_skipped(tmp_path: Path) -> None:
    copy = copied_tree(tmp_path)
    (copy / "src" / "notapackage").mkdir(parents=True)
    (copy / "src" / "notapackage" / "scratch.py").write_text("x = 1\n", encoding="utf-8")

    result = gate_result_in(copy, "module_contract")

    assert result.ok is True, result.detail


def test_tools_readme_passes() -> None:
    problems = module_contract.problems_in(REPO_ROOT / "tools")

    assert problems == []


def test_the_real_tree_passes() -> None:
    result = module_contract.run()

    assert result.ok is True, result.detail


def test_a_missing_src_is_a_clean_pass(tmp_path: Path) -> None:
    """``src/`` does not exist yet at P0; nothing to scan is not a failure."""
    copy = copied_tree(tmp_path)

    result = gate_result_in(copy, "module_contract")

    assert result.ok is True, result.detail
