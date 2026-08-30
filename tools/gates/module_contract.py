"""Gate 7 — the module contract checker (DEC-0011,
``docs/process/readme-ai-convention.md``).

Every module directory carries a ``readme.ai.md`` — the contract a bounded session reads
*instead of* the code. This gate checks presence and conformance, never quality: a machine
cannot judge whether a ``Purpose`` is honest, but it can tell whether the nine required
headings are all there, in order, and none of them is empty. An empty heading is the
concrete, common way this convention decays, which is why it is the one content check worth
making.

**What counts as a module** (DEC-0026): any directory under ``src/`` or ``tools/`` that
carries an ``__init__.py``, at any depth. The walk does not stop when it finds a package —
``docs/architecture/module-map.md`` §Per-module obligations reads "Every directory under
``src/`` carries ``readme.ai.md``", and it names ``engine/ingest``, ``engine/observation``,
``engine/derivation``, ``engine/packs``, ``engine/resolution``, ``engine/evaluation`` and
``engine/findings`` as distinct modules with distinct responsibilities. A walk that stopped
at the topmost package would check ``src/engine/`` and skip all seven, which is a gate that
looks green while enforcing nothing on the code it exists to guard.

A ``tests/`` tree is the one exclusion, and it is not an exception to the rule so much as a
consequence of it: the same section puts ``tests/`` *inside* a module, so a module's tests
are covered by that module's contract and are not a module themselves. ``tests`` is not
descended into at all, so a package nested under one needs no ``readme.ai.md`` either.

``src/`` does not exist yet at P0, so this gate is proven by its fixtures, not by its scan
target (DEC-0016) — what it finds in the real tree today is ``tools/readme.ai.md`` and
``tools/gates/readme.ai.md``.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from tools.gates import REPO_ROOT

if TYPE_CHECKING:
    from tools.verify import GateResult

REQUIRED_SECTIONS: tuple[str, ...] = (
    "Purpose",
    "Context",
    "Contract",
    "Invariants enforced here",
    "Depends on",
    "Must not depend on",
    "Tests",
    "How to run it",
    "Open questions",
)
"""Fixed, in this order, per ``docs/process/readme-ai-convention.md``. Reordering these is
a change to the convention and a decision record, not a task-level choice."""

SCAN_ROOTS: tuple[str, ...] = ("src", "tools")

EXCLUDE_DIR_NAMES: frozenset[str] = frozenset({"__pycache__", "tests"})
"""Directory names the walk does not enter. ``tests`` is a module's own test tree
(DEC-0026), not a module; ``__pycache__`` is not source at all."""

_HEADING_RE = re.compile(r"^##[ \t]+(.+?)[ \t]*$", re.MULTILINE)


@dataclass(frozen=True)
class _Section:
    name: str
    body: str


def _sections_in(text: str) -> list[_Section]:
    """Every ``## `` heading in ``text``, in the order it appears, paired with the text
    between it and the next heading (or the end of the file)."""
    matches = list(_HEADING_RE.finditer(text))
    sections: list[_Section] = []
    for index, match in enumerate(matches):
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        sections.append(_Section(name=match.group(1).strip(), body=text[start:end]))
    return sections


def problems_in(directory: Path) -> list[str]:
    """Everything wrong with ``directory``'s ``readme.ai.md``, or an empty list.

    A pure function over one directory: no tree walk, no registry, so a single constructed
    package proves each rule directly.
    """
    readme = directory / "readme.ai.md"
    if not readme.exists():
        return [f"{directory}: readme.ai.md is missing"]

    sections = _sections_in(readme.read_text(encoding="utf-8"))
    present = [section.name for section in sections if section.name in REQUIRED_SECTIONS]

    missing = [name for name in REQUIRED_SECTIONS if name not in present]
    if missing:
        return [
            f"{directory}: readme.ai.md is missing section {name!r}" for name in missing
        ]

    if present != list(REQUIRED_SECTIONS):
        return [
            f"{directory}: readme.ai.md has its sections out of order — expected "
            f"{list(REQUIRED_SECTIONS)}, found {present}"
        ]

    bodies = {section.name: section.body for section in sections}
    return [
        f"{directory}: readme.ai.md section {name!r} has an empty body"
        for name in REQUIRED_SECTIONS
        if not bodies[name].strip()
    ]


def module_directories(root: Path) -> list[Path]:
    """Every package directory under ``root``, at any depth, ``tests/`` trees excluded.

    Finding a package is not a reason to stop descending (DEC-0026): a package nested inside
    another is its own module and owes its own contract.
    """
    if not root.exists():
        return []

    found: list[Path] = []

    def walk(directory: Path) -> None:
        if (directory / "__init__.py").exists():
            found.append(directory)
        for child in sorted(p for p in directory.iterdir() if p.is_dir()):
            if child.name not in EXCLUDE_DIR_NAMES:
                walk(child)

    walk(root)
    return found


def _scan(roots: Sequence[Path]) -> list[tuple[Path, list[Path]]]:
    """Every ``root`` that exists, paired with the module directories found under **that**
    root alone — never aggregated across roots, so one healthy root cannot mask another
    that exists and found nothing (a live ``tools/`` must not hide a dead ``src/``). A root
    that does not exist contributes no pair at all: it is nothing to scan, never a root
    that scanned zero subjects.
    """
    return [(root, module_directories(root)) for root in roots if root.exists()]


def verdict(roots: Sequence[Path]) -> GateResult:
    """Gate 7's whole rule, over explicit scan roots — a constructed pair of directories
    proves the empty-scan and missing-root cases directly, independent of ``REPO_ROOT``.

    Checked **per root**, not in aggregate: a root that **exists** but holds no module
    directory fails closed on its own, naming only itself, even while a sibling root is
    full of packages — a scan that ran and found nothing is byte-identical to one that
    never ran, unless it says so, and one healthy root must not launder a dead one (C1,
    ``REVIEW-harness-p0.md``). A root that does not exist — ``src/`` at P0 — is not that
    case and stays a clean pass.
    """
    from tools.verify import GateResult

    scanned = _scan(roots)
    dead = [root for root, directories in scanned if not directories]
    if dead:
        names = ", ".join(f"{root.name}/" for root in dead)
        return GateResult(
            ok=False,
            detail=(
                f"0 module directories found under {names} — a scan root that exists but "
                f"yields no module directories is a failed scan, not a clean pass"
            ),
        )

    directories = [directory for _, root_dirs in scanned for directory in root_dirs]
    problems: list[str] = []
    for directory in directories:
        problems.extend(problems_in(directory))

    if problems:
        return GateResult(ok=False, detail="\n".join(problems))

    if not scanned:
        names = ", ".join(f"{root.name}/" for root in roots)
        return GateResult(
            ok=True, detail=f"no scan root exists under {names} — nothing to scan"
        )
    return GateResult(ok=True, detail=f"{len(directories)} module directories checked")


def run() -> GateResult:
    """Gate 7. Check every module directory under ``src/`` and ``tools/``, or a passing
    result naming how many it checked."""
    return verdict([REPO_ROOT / root_name for root_name in SCAN_ROOTS])
