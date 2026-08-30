"""Gate 6 — the placeholder scan (``docs/process/definition-of-done.md`` condition 4).

Catches code that was never finished but looks finished. A missing feature is visible; a
silent stand-in for one is not, and that is the specific failure mode of generated code
this gate exists to close.

Four patterns, under ``src/`` and ``tools/``:

1. A ``TODO`` / ``FIXME`` / ``XXX`` / ``HACK`` marker in a real ``#`` comment. Matched with
   ``tokenize``, over comment tokens only — never over arbitrary string content. A module
   documenting *this gate itself* has to say these four words in prose, in its own
   docstring, and a scan that flagged its own explanation would be exactly the noisy gate
   that gets disabled within a week (``docs/roadmap/tasks/T-0005-placeholder-scan.md``).
   Comments are unambiguous in a way prose is not: nobody writes an explanatory essay about
   the *concept* of a left-in marker inside a bare ``#`` line next to unrelated code.
2. A function or async function body that is only ``pass`` — checked structurally on
   ``FunctionDef``/``AsyncFunctionDef.body``, which is what lets ``except Exception: pass``
   (an ``ExceptHandler.body``, a different node entirely) pass untouched without a special
   case for it. An ``...``-only body is the same failure *unless* the enclosing class bases
   include ``Protocol`` or the file is a ``.pyi`` stub — the one shape this convention uses
   for a real, deliberate "no implementation here" signature.
3. ``"placeholder"`` / ``"not implemented"`` / ``"dummy"`` (case-insensitively) as the
   **direct** value of a ``return`` or an assignment — ``return "placeholder"``,
   ``x = "dummy"``. Direct, not merely present somewhere in the tree: a tuple or a
   ``frozenset`` literal holding these words as *data* — this module's own
   ``PLACEHOLDER_VALUES`` below — is not a stand-in return value and does not match, because
   its assigned value is a container, not a bare string constant.
4. ``raise NotImplementedError`` with no message, anywhere, or one that is not the first
   statement (after an optional docstring) of the function body it sits in.
   ``docs/process/definition-of-done.md`` condition 4 permits exactly
   ``raise NotImplementedError("<why, and what it blocks>")`` reached unconditionally on
   entry to a stub; the report lists that stub as **NOT DONE** — a human obligation this
   gate cannot check, only the message and the position.

Structure, not regex, decides (2) and (4): a regex cannot tell a stub ``pass`` from one
inside an ``except`` clause, or a permitted first-line raise from a buried one, and a gate
that gets either wrong is disabled the first time it is wrong about legitimate code.

No suppression mechanism exists here and none should be added. A pattern that is wrong is
fixed in the pattern; an escape hatch turns this gate into a suggestion.
"""

from __future__ import annotations

import ast
import io
import re
import tokenize
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from tools.gates import REPO_ROOT

if TYPE_CHECKING:
    from tools.verify import GateResult

SCAN_ROOTS: tuple[str, ...] = ("src", "tools")

EXCLUDE_DIR_NAMES: frozenset[str] = frozenset({"__pycache__"})

_COMMENT_MARKERS: tuple[str, ...] = ("TODO", "FIXME", "XXX", "HACK")
"""Markers looked for in a real comment. A tuple literal, not a bare assigned string, so
this constant is itself never mistaken for pattern 3 above."""

_COMMENT_MARKER_RE = re.compile(
    "|".join(rf"\b{re.escape(marker)}\b" for marker in _COMMENT_MARKERS)
)

PLACEHOLDER_VALUES: frozenset[str] = frozenset({"placeholder", "not implemented", "dummy"})
"""Literal stand-in values, matched case-insensitively as a whole string."""


@dataclass(frozen=True)
class Finding:
    """One placeholder pattern, at the place it was found."""

    path: Path
    line: int
    identifier: str
    pattern: str


def _is_docstring_position(body: list[ast.stmt], index: int) -> bool:
    """Whether ``body[index]`` is a real docstring — the first statement of the body, a
    bare string-constant expression."""
    if index != 0 or not body:
        return False
    first = body[0]
    return (
        isinstance(first, ast.Expr)
        and isinstance(first.value, ast.Constant)
        and isinstance(first.value.value, str)
    )


def _comment_findings(source: str, path: Path) -> list[Finding]:
    """Every ``TODO``/``FIXME``/``XXX``/``HACK`` marker in a real ``#`` comment."""
    findings: list[Finding] = []
    try:
        tokens = tokenize.generate_tokens(io.StringIO(source).readline)
        for token in tokens:
            if token.type == tokenize.COMMENT:
                match = _COMMENT_MARKER_RE.search(token.string)
                if match is not None:
                    findings.append(
                        Finding(
                            path,
                            token.start[0],
                            token.string.strip(),
                            f"{match.group(0)} marker in a comment",
                        )
                    )
    except (tokenize.TokenError, SyntaxError, IndentationError):
        # Structurally broken enough that ast.parse below will raise on the same file,
        # which is that failure's own gate to report, not this one's to swallow.
        pass
    return findings


def _is_protocol_class(node: ast.ClassDef) -> bool:
    """Whether ``node`` declares itself a ``Protocol`` (bare or ``typing.Protocol``)."""
    return any(
        (isinstance(base, ast.Name) and base.id == "Protocol")
        or (isinstance(base, ast.Attribute) and base.attr == "Protocol")
        for base in node.bases
    )


def _stub_body_finding(
    node: ast.FunctionDef | ast.AsyncFunctionDef, path: Path, *, in_protocol: bool
) -> Finding | None:
    """The stub-body finding for ``node``, or ``None`` if its body is not only a stub."""
    body = node.body
    if len(body) != 1:
        return None
    (statement,) = body
    if isinstance(statement, ast.Pass):
        return Finding(path, statement.lineno, node.name, "function body is only `pass`")
    is_ellipsis = (
        isinstance(statement, ast.Expr)
        and isinstance(statement.value, ast.Constant)
        and statement.value.value is Ellipsis
    )
    if is_ellipsis and not in_protocol and path.suffix != ".pyi":
        return Finding(path, statement.lineno, node.name, "function body is only `...`")
    return None


def _literal_value_finding(
    node: ast.Assign | ast.AnnAssign | ast.Return, path: Path
) -> Finding | None:
    """The stand-in-literal finding for ``node``, or ``None``.

    Only the **direct** value counts: ``node.value`` must itself be a string constant, not
    a container that merely holds one. ``PLACEHOLDER_VALUES`` above is a ``frozenset``
    literal for exactly this reason — its assigned value is a call, not a bare string.
    """
    value = node.value
    if not (isinstance(value, ast.Constant) and isinstance(value.value, str)):
        return None
    if value.value.strip().lower() not in PLACEHOLDER_VALUES:
        return None
    kind = "returned" if isinstance(node, ast.Return) else "assigned"
    return Finding(path, value.lineno, value.value, f"literal {value.value!r} {kind}")


def _raises_notimplementederror(node: ast.Raise) -> bool:
    exc = node.exc
    if isinstance(exc, ast.Name):
        return exc.id == "NotImplementedError"
    if isinstance(exc, ast.Call) and isinstance(exc.func, ast.Name):
        return exc.func.id == "NotImplementedError"
    return False


def _raise_has_message(node: ast.Raise) -> bool:
    exc = node.exc
    if not isinstance(exc, ast.Call) or not exc.args:
        return False
    first = exc.args[0]
    return (
        isinstance(first, ast.Constant)
        and isinstance(first.value, str)
        and first.value.strip() != ""
    )


def _permitted_raises(tree: ast.Module) -> set[ast.Raise]:
    """``raise NotImplementedError("<why>")`` reached unconditionally on entry to its
    function — the one permitted shape (``docs/process/definition-of-done.md`` condition
    4)."""
    permitted: set[ast.Raise] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            continue
        body = node.body
        index = 1 if _is_docstring_position(body, 0) else 0
        if len(body) <= index:
            continue
        candidate = body[index]
        if (
            isinstance(candidate, ast.Raise)
            and _raises_notimplementederror(candidate)
            and _raise_has_message(candidate)
        ):
            permitted.add(candidate)
    return permitted


def _raise_findings(tree: ast.Module, path: Path) -> list[Finding]:
    permitted = _permitted_raises(tree)
    findings: list[Finding] = []
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Raise)
            and _raises_notimplementederror(node)
            and node not in permitted
        ):
            if _raise_has_message(node):
                findings.append(
                    Finding(
                        path,
                        node.lineno,
                        "raise NotImplementedError(...)",
                        "not the first statement of its function body",
                    )
                )
            else:
                findings.append(
                    Finding(
                        path,
                        node.lineno,
                        "raise NotImplementedError",
                        "bare, with no message",
                    )
                )
    return findings


def _body_findings(body: list[ast.stmt], path: Path, *, in_protocol: bool) -> list[Finding]:
    """Walk one statement list, tracking which class body (if any) encloses it, so a
    ``Protocol`` method's ``...`` body is told apart from an ordinary one without ``ast``
    having to be asked to carry that context itself."""
    findings: list[Finding] = []
    for statement in body:
        if isinstance(statement, ast.FunctionDef | ast.AsyncFunctionDef):
            stub = _stub_body_finding(statement, path, in_protocol=in_protocol)
            if stub is not None:
                findings.append(stub)
            findings.extend(_body_findings(statement.body, path, in_protocol=False))
        elif isinstance(statement, ast.ClassDef):
            findings.extend(
                _body_findings(
                    statement.body, path, in_protocol=_is_protocol_class(statement)
                )
            )
        else:
            for field in ("body", "orelse", "finalbody"):
                nested = getattr(statement, field, None)
                if isinstance(nested, list):
                    findings.extend(_body_findings(nested, path, in_protocol=in_protocol))
            for handler in getattr(statement, "handlers", []):
                findings.extend(_body_findings(handler.body, path, in_protocol=in_protocol))
        if isinstance(statement, ast.Assign | ast.AnnAssign):
            found = _literal_value_finding(statement, path)
            if found is not None:
                findings.append(found)
        elif isinstance(statement, ast.Return):
            found = _literal_value_finding(statement, path)
            if found is not None:
                findings.append(found)
    return findings


def findings_in(source: str, path: Path) -> list[Finding]:
    """Every placeholder pattern in one file, real or constructed.

    A pure function over source text: no filesystem walk, no registry, so a single
    constructed snippet proves each pattern directly.
    """
    findings = _comment_findings(source, path)
    tree = ast.parse(source, filename=str(path))
    findings.extend(_body_findings(tree.body, path, in_protocol=False))
    findings.extend(_raise_findings(tree, path))
    return findings


def _python_files_under(root: Path) -> list[Path]:
    """Every ``*.py`` file under ``root``, or an empty list if ``root`` does not exist."""
    if not root.exists():
        return []
    return sorted(
        path
        for path in root.rglob("*.py")
        if not (EXCLUDE_DIR_NAMES & set(path.relative_to(root).parts[:-1]))
    )


def run() -> GateResult:
    """Gate 6. Scan every file under ``src/`` and ``tools/`` for the four placeholder
    patterns, or an empty, passing result if none is found."""
    from tools.verify import GateResult

    findings: list[Finding] = []
    for root_name in SCAN_ROOTS:
        for path in _python_files_under(REPO_ROOT / root_name):
            findings.extend(findings_in(path.read_text(encoding="utf-8"), path))

    if findings:
        detail = "\n".join(
            f"{finding.path.relative_to(REPO_ROOT)}:{finding.line}: {finding.pattern} "
            f"({finding.identifier})"
            for finding in findings
        )
        return GateResult(ok=False, detail=detail)
    return GateResult(ok=True, detail="")
