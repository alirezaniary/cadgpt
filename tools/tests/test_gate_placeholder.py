"""Proof that gate 6 (the placeholder scan) matches and rejects correctly.

Unit tests call ``placeholder.findings_in`` directly over a constructed source string —
pure, no filesystem walk, no registry — to prove each of the four patterns and the cases
that must not match. Integration tests plant real files into a copy of the harness
(``conftest.copied_tree``) and run the real gate or the real ``make verify`` over it,
proving the wiring.

**Mocking: none.** Real ``ast``, real ``tokenize``, real files, and — for the ``make
verify`` proof — the real ``Makefile`` and runner.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tools.gates import placeholder
from tools.tests.conftest import copied_tree, gate_result_in, make_verify, only_gate

# --- unit: each pattern, and the cases that must not match --------------------------


def test_a_todo_comment_fails() -> None:
    source = "x = 1  # TODO: revisit this once T-0009 lands\n"

    findings = placeholder.findings_in(source, Path("src/thing.py"))

    assert any("TODO" in f.pattern for f in findings)


def test_a_body_that_is_only_pass_fails() -> None:
    source = "def handler() -> None:\n    pass\n"

    findings = placeholder.findings_in(source, Path("src/thing.py"))

    assert any("only `pass`" in f.pattern for f in findings)


def test_a_bare_raise_notimplementederror_fails() -> None:
    source = "def handler() -> None:\n    raise NotImplementedError\n"

    findings = placeholder.findings_in(source, Path("src/thing.py"))

    assert any("bare, with no message" in f.pattern for f in findings)


def test_a_raise_with_a_reason_on_the_first_line_passes() -> None:
    source = 'def handler() -> None:\n    raise NotImplementedError("blocked on T-0009")\n'

    findings = placeholder.findings_in(source, Path("src/thing.py"))

    assert findings == []


# --- integration: the same shapes, planted where the gate really scans -------------


@pytest.mark.integration
def test_make_verify_fails_and_names_gate_6(tmp_path: Path) -> None:
    copy = copied_tree(tmp_path, only_gate(6))
    (copy / "src").mkdir(exist_ok=True)
    (copy / "src" / "thing.py").write_text(
        "def handler() -> None:\n    pass\n", encoding="utf-8"
    )

    result = make_verify(copy)

    assert result.returncode != 0, result.stdout + result.stderr
    assert "FAIL  gate 6  placeholder-scan" in result.stdout
    assert "src/thing.py" in result.stdout
    assert "only `pass`" in result.stdout


@pytest.mark.integration
def test_a_pass_inside_except_passes(tmp_path: Path) -> None:
    copy = copied_tree(tmp_path)
    (copy / "src").mkdir(exist_ok=True)
    (copy / "src" / "thing.py").write_text(
        "def handler() -> None:\n"
        "    try:\n"
        "        raise ValueError\n"
        "    except ValueError:\n"
        "        pass\n",
        encoding="utf-8",
    )

    result = gate_result_in(copy, "placeholder")

    assert result.ok is True, result.detail


@pytest.mark.integration
def test_an_ellipsis_in_a_protocol_body_passes(tmp_path: Path) -> None:
    copy = copied_tree(tmp_path)
    (copy / "src").mkdir(exist_ok=True)
    (copy / "src" / "thing.py").write_text(
        "from typing import Protocol\n\n\n"
        "class Thing(Protocol):\n"
        "    def run(self) -> None: ...\n",
        encoding="utf-8",
    )

    result = gate_result_in(copy, "placeholder")

    assert result.ok is True, result.detail


@pytest.mark.integration
def test_an_ellipsis_in_a_stub_file_passes(tmp_path: Path) -> None:
    """``*.pyi`` is outside this gate's ``*.py`` glob, so ``thing.pyi`` alone would leave
    ``src/`` a root that exists but yields zero scanned files — the empty-scan case C1
    fails closed on (``REVIEW-harness-p0.md``), not the exemption this test is about. A
    real, unrelated companion file keeps ``src/`` a genuine, non-empty scan."""
    copy = copied_tree(tmp_path)
    (copy / "src").mkdir(exist_ok=True)
    (copy / "src" / "thing.pyi").write_text("def run() -> None: ...\n", encoding="utf-8")
    (copy / "src" / "ok.py").write_text("x = 1\n", encoding="utf-8")

    result = gate_result_in(copy, "placeholder")

    assert result.ok is True, result.detail


@pytest.mark.integration
def test_the_real_tree_passes() -> None:
    result = placeholder.run()

    assert result.ok is True, result.detail


# --- unit: coverage (C1, REVIEW-harness-p0.md) --------------------------------------


def test_an_existing_root_with_no_python_files_fails_closed(tmp_path: Path) -> None:
    """A scan root that exists but yields zero subjects is not a clean pass — it is
    indistinguishable from a scan that never ran unless it says so."""
    empty_root = tmp_path / "tools"
    empty_root.mkdir()

    result = placeholder.verdict([empty_root])

    assert result.ok is False
    assert "0 files scanned under tools/" in result.detail


def test_a_missing_root_stays_a_clean_pass_and_is_not_named(tmp_path: Path) -> None:
    """The other half of the same rule: a root that does not exist is nothing to scan,
    never zero subjects found — ``src/`` must stay green while it does not exist."""
    missing_root = tmp_path / "src"
    present_root = tmp_path / "tools"
    present_root.mkdir()
    (present_root / "ok.py").write_text("x = 1\n", encoding="utf-8")

    result = placeholder.verdict([missing_root, present_root])

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

    result = placeholder.verdict([dead_root, live_root])

    assert result.ok is False
    assert "0 files scanned under src/" in result.detail
    assert "tools/" not in result.detail


def test_no_root_existing_at_all_says_so(tmp_path: Path) -> None:
    """With nothing to scan at all, the detail must say what happened rather than trail
    off after "under" — a coverage line that stops mid-sentence is not a coverage line."""
    result = placeholder.verdict([tmp_path / "src", tmp_path / "tools"])

    assert result.ok is True, result.detail
    assert result.detail == "no scan root exists under src/, tools/ — nothing to scan"
