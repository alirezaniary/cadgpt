"""Gate 5 — the jurisdiction guard (I4, DEC-0020, ``docs/architecture/harness.md``).

I4 says the engine cannot tell which country it is running in. DEC-0020 makes that
mechanical rather than remembered: a jurisdiction lives only in ``packs/`` — data, never
code — and this gate fails the build if a country, code body or clause reference is
compiled into an **identifier** under ``src/`` or ``tools/`` instead.

**Identifiers, not text.** A docstring, a comment or a clause quoted in a test may name a
country freely; only an actual Python identifier is scanned — a module's own file name, a
class, a function or its parameters, an assignment target, or a string literal used as a
dictionary key (the concrete case of "a string used as a property name"). ``ast`` gives
this for free: a docstring is a string *constant*, never a ``Name``, ``arg`` or
``ClassDef``/``FunctionDef`` name, so it is never visited by the checks below.

**Word-boundary, not substring.** A naive substring search for a two-letter ISO code turns
almost any English word into a false positive — ``iteration`` opens with ``IT`` (Italy),
``variance`` contains ``AR`` (Argentina), ``secant`` opens with ``SE`` (Sweden). A gate that
noisy gets disabled, which proves nothing forever after, so this gate never does a
substring search: every identifier is split into lowercase snake/camel/digit segments and a
token only matches a **whole segment**, never a fragment of one. Bare two-letter alpha-2
codes are deliberately left out of ``JURISDICTION_TOKENS`` for the same reason — they are
exactly the collision-prone case the false-positive guard above exists for. Extend the
country/code coverage with full names and three-letter (alpha-3) codes instead; a
two-letter code belongs here only once its collision risk against ordinary identifiers has
actually been checked.

Clause-reference shapes (``clause_5_3_2``, ``art14``, ``sec_302``) are not whole-word tokens
— they are a code word immediately followed by a digit segment — so they are matched by
``_clause_shape`` over the same segment list, not by membership in ``JURISDICTION_TOKENS``.
"""

from __future__ import annotations

import ast
import re
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from tools.gates import REPO_ROOT

if TYPE_CHECKING:
    from tools.verify import GateResult

SCAN_ROOTS: tuple[str, ...] = ("src", "tools")
"""Where an identifier may not name a jurisdiction. ``packs/`` is data (DEC-0020) and is
never scanned — a jurisdiction belongs there, named freely."""

EXCLUDE_DIR_NAMES: frozenset[str] = frozenset({"__pycache__"})
"""Directories skipped outright. No fixture directory is excluded here: every bad input
this gate's own tests plant is written straight into a copied tree's ``src/`` (or
``packs/``), never committed at rest, so there is nothing under ``tools/`` for this gate to
have to look past."""

JURISDICTION_TOKENS: frozenset[str] = frozenset(
    {
        # Country and region names. Extend by adding the lowercase, whole-word name.
        "iran",
        "iraq",
        "afghanistan",
        "pakistan",
        "turkey",
        "egypt",
        "india",
        "china",
        "japan",
        "germany",
        "france",
        "italy",
        "spain",
        "canada",
        "australia",
        "brazil",
        "russia",
        "mexico",
        "indonesia",
        "nigeria",
        "argentina",
        "singapore",
        "malaysia",
        "qatar",
        "oman",
        "kuwait",
        "bahrain",
        "jordan",
        "lebanon",
        "syria",
        "yemen",
        "america",
        "britain",
        "england",
        "scotland",
        "wales",
        "korea",
        "vietnam",
        # ISO 3166-1 alpha-3 codes. Alpha-2 codes are deliberately absent — see the module
        # docstring's false-positive guard.
        "irn",
        "irq",
        "afg",
        "pak",
        "tur",
        "egy",
        "ind",
        "chn",
        "jpn",
        "deu",
        "fra",
        "ita",
        "esp",
        "can",
        "aus",
        "bra",
        "rus",
        "mex",
        "idn",
        "nga",
        "arg",
        "sgp",
        "mys",
        "qat",
        "omn",
        "kwt",
        "bhr",
        "jor",
        "lbn",
        "syr",
        "yem",
        "usa",
        "gbr",
        "kor",
        "vnm",
        # Code-body acronyms named explicitly by T-0004.
        "ibc",
        "nbc",
        "eurocode",
        "ashrae",
        "nfpa",
        "bca",
        "ncc",
        "din",
        "nbr",
        # Native-script tokens.
        "ایران",
        "مقررات",
    }
)
"""Whole-segment tokens. A token matches only when it equals an entire identifier segment
— never a fragment of one — which is what keeps ``iteration``, ``variance`` and ``secant``
out of this set's reach without naming them as exceptions."""

_CLAUSE_WORDS: frozenset[str] = frozenset({"clause", "art", "article", "sec", "section"})
"""A code-word segment that, followed immediately by a digit segment, is a clause
reference — ``clause_5_3_2``, ``art14``, ``sec_302`` — rather than a token looked up by
whole-word equality."""

_CAMEL_BOUNDARY = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")
_SEGMENT_RUN = re.compile(r"[A-Za-z]+|[0-9]+")


def _segments(identifier: str) -> tuple[str, ...]:
    """``identifier`` split into lowercase snake/camel/digit segments.

    ``check_clause_5_3_2`` becomes ``("check", "clause", "5", "3", "2")``; ``art14``
    becomes ``("art", "14")``; ``CheckClause`` becomes ``("check", "clause")``. Splitting on
    letter/digit runs as well as on case and underscore boundaries is what lets a clause
    shape like ``art14`` be recognised without its digits ever being glued to the word.
    """
    marked = _CAMEL_BOUNDARY.sub("_", identifier)
    return tuple(token.lower() for token in _SEGMENT_RUN.findall(marked))


def _clause_shape(segments: tuple[str, ...]) -> str | None:
    """The clause reference named by ``segments``, or ``None``.

    A code word immediately followed by a digit segment — not a whole-word token lookup,
    because the digits are what make a bare ``sec`` or ``clause`` a reference rather than
    an ordinary word.
    """
    for index, segment in enumerate(segments[:-1]):
        if segment in _CLAUSE_WORDS and segments[index + 1].isdigit():
            return f"{segment}{segments[index + 1]}"
    return None


def token_in(identifier: str) -> str | None:
    """The jurisdiction token named by ``identifier``, or ``None`` if it names none."""
    segments = _segments(identifier)
    for segment in segments:
        if segment in JURISDICTION_TOKENS:
            return segment
    return _clause_shape(segments)


@dataclass(frozen=True)
class Finding:
    """One identifier that names a jurisdiction, at the place it was found."""

    path: Path
    line: int
    identifier: str
    token: str


def _module_identifier(path: Path) -> str:
    """The identifier a module's own file name contributes.

    ``__init__.py`` names no module of its own; what it names is its *package*, so the
    identifier checked there is the enclosing directory's name.
    """
    return path.parent.name if path.stem == "__init__" else path.stem


def findings_in(source: str, path: Path) -> list[Finding]:
    """Every jurisdiction-naming identifier in one file, real or constructed.

    A pure function over source text: no filesystem walk, no registry, so a single
    constructed snippet proves the matching rule directly.
    """
    findings: list[Finding] = []
    module_token = token_in(_module_identifier(path))
    if module_token is not None:
        findings.append(Finding(path, 1, _module_identifier(path), module_token))

    tree = ast.parse(source, filename=str(path))
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef):
            token = token_in(node.name)
            if token is not None:
                findings.append(Finding(path, node.lineno, node.name, token))
        elif isinstance(node, ast.arg):
            token = token_in(node.arg)
            if token is not None:
                findings.append(Finding(path, node.lineno, node.arg, token))
        elif isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
            token = token_in(node.id)
            if token is not None:
                findings.append(Finding(path, node.lineno, node.id, token))
        elif isinstance(node, ast.Dict):
            for key in node.keys:
                if isinstance(key, ast.Constant) and isinstance(key.value, str):
                    token = token_in(key.value)
                    if token is not None:
                        findings.append(Finding(path, key.lineno, key.value, token))
    return findings


def _python_files_under(root: Path) -> list[Path]:
    """Every ``*.py`` file under ``root``, or an empty list if ``root`` does not exist.

    A missing ``src/`` is not a failure to report — it is nothing to scan, and ``src/``
    does not exist yet at P0.
    """
    if not root.exists():
        return []
    return sorted(
        path
        for path in root.rglob("*.py")
        if not (EXCLUDE_DIR_NAMES & set(path.relative_to(root).parts[:-1]))
    )


def _relative(path: Path) -> Path:
    """``path`` relative to ``REPO_ROOT`` when it sits under it, or ``path`` unchanged.

    A finding's own file always sits under ``REPO_ROOT`` in a real run; a proof of
    ``verdict`` over roots it constructed itself does not, and must not raise trying to
    print one.
    """
    try:
        return path.relative_to(REPO_ROOT)
    except ValueError:
        return path


def _scan(roots: Sequence[Path]) -> list[tuple[Path, list[Path]]]:
    """Every ``root`` that exists, paired with the ``*.py`` files found under **that**
    root alone — never aggregated across roots, so one healthy root cannot mask another
    that exists and found nothing (a live ``tools/`` must not hide a dead ``src/``). A root
    that does not exist contributes no pair at all: it is nothing to scan, never a root
    that scanned zero subjects.
    """
    return [(root, _python_files_under(root)) for root in roots if root.exists()]


def verdict(roots: Sequence[Path]) -> GateResult:
    """Gate 5's whole rule, over explicit scan roots — a constructed pair of directories
    proves the empty-scan and missing-root cases directly, independent of ``REPO_ROOT``.

    Checked **per root**, not in aggregate: a root that **exists** but holds no ``*.py``
    file fails closed on its own, naming only itself, even while a sibling root is full of
    files — a scan that ran and found nothing is byte-identical to one that never ran,
    unless it says so, and one healthy root must not launder a dead one (C1,
    ``REVIEW-harness-p0.md``). A root that does not exist — ``src/`` at P0 — is not that
    case and stays a clean pass.
    """
    from tools.verify import GateResult

    scanned = _scan(roots)
    dead = [root for root, files in scanned if not files]
    if dead:
        names = ", ".join(f"{root.name}/" for root in dead)
        return GateResult(
            ok=False,
            detail=(
                f"0 files scanned under {names} — a scan root that exists but yields no "
                f"files is a failed scan, not a clean pass"
            ),
        )

    files = [path for _, root_files in scanned for path in root_files]
    findings: list[Finding] = []
    for path in files:
        findings.extend(findings_in(path.read_text(encoding="utf-8"), path))

    if findings:
        detail = "\n".join(
            f"{_relative(finding.path)}:{finding.line}: identifier "
            f"{finding.identifier!r} names jurisdiction token {finding.token!r} (I4) — a "
            f"jurisdiction may live only in packs/, never in an identifier under src/ or "
            f"tools/"
            for finding in findings
        )
        return GateResult(ok=False, detail=detail)

    if not scanned:
        names = ", ".join(f"{root.name}/" for root in roots)
        return GateResult(
            ok=True, detail=f"no scan root exists under {names} — nothing to scan"
        )

    names = ", ".join(f"{root.name}/" for root, _ in scanned)
    return GateResult(ok=True, detail=f"{len(files)} files scanned under {names}")


def run() -> GateResult:
    """Gate 5. Parse every file under ``src/`` and ``tools/`` and report every identifier
    that names a jurisdiction, or a passing result naming how many files it scanned."""
    return verdict([REPO_ROOT / root_name for root_name in SCAN_ROOTS])
