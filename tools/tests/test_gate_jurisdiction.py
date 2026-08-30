"""Proof that gate 5 (the jurisdiction guard, I4/DEC-0020) matches and rejects correctly.

Unit tests call ``jurisdiction.findings_in`` directly over a constructed source string —
pure, no filesystem walk, no registry — to prove the matching rule itself: what fails, what
does not, and why the false-positive guard exists. Integration tests plant real files into a
copy of the harness (``conftest.copied_tree``) and run the real gate or the real
``make verify`` over it, proving the wiring.

**Mocking: none.** Real ``ast``, real files, and — for the two ``make verify`` proofs — the
real ``Makefile`` and runner.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tools.gates import jurisdiction
from tools.tests.conftest import (
    copied_tree,
    gate_result_in,
    make_verify,
    only_gate,
)

# --- unit: the matching rule itself -------------------------------------------------


def test_a_module_named_for_a_country_fails() -> None:
    findings = jurisdiction.findings_in("x = 1\n", Path("src/iran.py"))

    assert len(findings) == 1
    assert findings[0].identifier == "iran"
    assert findings[0].token == "iran"


def test_a_function_named_for_a_clause_reference_fails() -> None:
    source = "def check_clause_5_3_2() -> None:\n    return None\n"

    findings = jurisdiction.findings_in(source, Path("src/checks.py"))

    assert any(f.identifier == "check_clause_5_3_2" for f in findings)


def test_a_docstring_naming_a_country_passes() -> None:
    source = '"""This module implements the rules of Iran, clause 5.3.2."""\n'

    findings = jurisdiction.findings_in(source, Path("src/notes.py"))

    assert findings == []


def test_iteration_variance_and_secant_pass() -> None:
    """The false-positive guard: none of these three names a jurisdiction, even though a
    naive substring search would catch ``iteration`` (opens with ``IT``, Italy's alpha-2
    code), ``variance`` (contains ``AR``, Argentina's) and ``secant`` (opens with ``SE``,
    Sweden's) — exactly why whole-segment matching is used instead of substring matching.
    """
    source = (
        "def iteration() -> int:\n"
        "    variance = 1\n"
        "    secant = 2\n"
        "    return variance + secant\n"
    )

    findings = jurisdiction.findings_in(source, Path("src/math_helpers.py"))

    assert findings == []


# --- integration: the same content, planted where the gate really scans ------------


@pytest.mark.integration
def test_make_verify_fails_and_names_gate_5(tmp_path: Path) -> None:
    copy = copied_tree(tmp_path, only_gate(5))
    (copy / "src").mkdir(exist_ok=True)
    (copy / "src" / "iran.py").write_text("x = 1\n", encoding="utf-8")

    result = make_verify(copy)

    assert result.returncode != 0, result.stdout + result.stderr
    assert "FAIL  gate 5  jurisdiction-guard" in result.stdout
    assert "src/iran.py:1" in result.stdout
    assert "'iran'" in result.stdout


@pytest.mark.integration
def test_the_same_content_in_a_comment_passes(tmp_path: Path) -> None:
    copy = copied_tree(tmp_path)
    (copy / "src").mkdir(exist_ok=True)
    (copy / "src" / "notes.py").write_text(
        "# This module implements the rules of Iran, clause 5.3.2.\nx = 1\n",
        encoding="utf-8",
    )

    result = gate_result_in(copy, "jurisdiction")

    assert result.ok is True


@pytest.mark.integration
def test_the_same_content_under_packs_passes(tmp_path: Path) -> None:
    copy = copied_tree(tmp_path)
    (copy / "packs").mkdir()
    (copy / "packs" / "iran.py").write_text("x = 1\n", encoding="utf-8")

    result = gate_result_in(copy, "jurisdiction")

    assert result.ok is True


@pytest.mark.integration
def test_the_real_tree_passes() -> None:
    result = jurisdiction.run()

    assert result.ok is True, result.detail


def test_python_files_under_a_missing_root_is_empty(tmp_path: Path) -> None:
    """A root that is not there is nothing to scan, not a failure.

    Pointed at a genuinely absent directory rather than at ``src/``: this test asserted
    ``src/`` was empty because ``src/`` did not exist when it was written, so it began
    failing the moment the first module landed there — testing a fact about the calendar
    rather than about the function.
    """
    assert jurisdiction._python_files_under(tmp_path / "not_here") == []


@pytest.mark.integration
def test_a_missing_src_is_a_clean_pass(tmp_path: Path) -> None:
    copy = copied_tree(tmp_path)

    result = gate_result_in(copy, "jurisdiction")

    assert result.ok is True, result.detail


# --- unit: coverage (C1, REVIEW-harness-p0.md) --------------------------------------


def test_an_existing_root_with_no_python_files_fails_closed(tmp_path: Path) -> None:
    """A scan root that exists but yields zero subjects is not a clean pass — it is
    indistinguishable from a scan that never ran unless it says so."""
    empty_root = tmp_path / "tools"
    empty_root.mkdir()

    result = jurisdiction.verdict([empty_root])

    assert result.ok is False
    assert "0 files scanned under tools/" in result.detail


def test_a_missing_root_stays_a_clean_pass_and_is_not_named(tmp_path: Path) -> None:
    """The other half of the same rule: a root that does not exist is nothing to scan,
    never zero subjects found — ``src/`` must stay green while it does not exist."""
    missing_root = tmp_path / "src"
    present_root = tmp_path / "tools"
    present_root.mkdir()
    (present_root / "ok.py").write_text("x = 1\n", encoding="utf-8")

    result = jurisdiction.verdict([missing_root, present_root])

    assert result.ok is True, result.detail
    assert "1 files scanned under tools/" in result.detail
    assert "src/" not in result.detail


def test_a_dead_root_beside_a_live_one_still_fails_closed(tmp_path: Path) -> None:
    """A healthy root must not launder a dead one: ``src/`` existing but empty beside a
    ``tools/`` full of files is exactly the tree the moment ``src/`` is first created
    (C1.1), and this is the case C1 was raised about — the per-root check, not an
    aggregate across all roots, is what catches it."""
    dead_root = tmp_path / "src"
    dead_root.mkdir()
    live_root = tmp_path / "tools"
    live_root.mkdir()
    (live_root / "ok.py").write_text("x = 1\n", encoding="utf-8")

    result = jurisdiction.verdict([dead_root, live_root])

    assert result.ok is False
    assert "0 files scanned under src/" in result.detail
    assert "tools/" not in result.detail


def test_no_root_existing_at_all_says_so(tmp_path: Path) -> None:
    """With nothing to scan at all, the detail must say what happened rather than trail
    off after "under" — a coverage line that stops mid-sentence is not a coverage line."""
    result = jurisdiction.verdict([tmp_path / "src", tmp_path / "tools"])

    assert result.ok is True, result.detail
    assert result.detail == "no scan root exists under src/, tools/ — nothing to scan"
