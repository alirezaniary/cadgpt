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
    (copy / "src").mkdir()
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
    (copy / "src").mkdir()
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
    (copy / "src").mkdir()
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
    copy = copied_tree(tmp_path)
    (copy / "src").mkdir()
    (copy / "src" / "thing.pyi").write_text("def run() -> None: ...\n", encoding="utf-8")

    result = gate_result_in(copy, "placeholder")

    assert result.ok is True, result.detail


@pytest.mark.integration
def test_the_real_tree_passes() -> None:
    result = placeholder.run()

    assert result.ok is True, result.detail
