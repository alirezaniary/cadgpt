"""Gate 7 — the module contract checker (DEC-0011,
``docs/process/readme-ai-convention.md``).

Every module directory carries a ``readme.ai.md`` — the contract a bounded session reads
*instead of* the code. This gate checks presence and conformance, never quality: a machine
cannot judge whether a ``Purpose`` is honest, but it can tell whether the nine required
headings are all there, in order, and none of them is empty. An empty heading is the
concrete, common way this convention decays, which is why it is the one content check worth
making.

**Module, not directory.** ``docs/architecture/module-map.md`` treats ``tools/`` as a
single module even though ``tools/gates/`` and ``tools/tests/`` are separate Python
packages beneath it — one ``readme.ai.md`` already documents ``tools.verify``,
``tools.gates`` and ``tools.gates.isolation`` together. So a *module directory*, for this
gate, is the **topmost** package found walking down from ``src/`` or ``tools/`` — the first
directory on a given path that carries an ``__init__.py`` — and its own nested packages are
not walked past: they are internal to the module root's contract, not modules of their own.
This is what keeps ``tools/gates/`` from needing a ``readme.ai.md`` of its own that would
duplicate the one at ``tools/readme.ai.md``, and it generalises to ``src/``: a distribution
root such as ``src/engine`` is itself the module-map's namespace, and the *context*
directories beneath it (``src/engine/ingest``, ``src/engine/derivation``, ...) are each the
first ``__init__.py`` this walk finds on the way down to them.

``src/`` does not exist yet at P0, so this gate is proven by its fixtures, not by its scan
target (DEC-0016) — the one thing it can and must find in the real tree today is
``tools/readme.ai.md`` itself.
"""

from __future__ import annotations

import re
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

EXCLUDE_DIR_NAMES: frozenset[str] = frozenset({"__pycache__"})

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


def _module_roots(root: Path) -> list[Path]:
    """The topmost package directories under ``root`` — see the module docstring for why
    a package's own subpackages are not walked past."""
    if not root.exists():
        return []

    found: list[Path] = []

    def walk(directory: Path) -> None:
        if (directory / "__init__.py").exists():
            found.append(directory)
            return
        for child in sorted(p for p in directory.iterdir() if p.is_dir()):
            if child.name not in EXCLUDE_DIR_NAMES:
                walk(child)

    walk(root)
    return found


def run() -> GateResult:
    """Gate 7. Check every module root under ``src/`` and ``tools/``, or an empty, passing
    result if none has a problem."""
    from tools.verify import GateResult

    problems: list[str] = []
    for root_name in SCAN_ROOTS:
        for directory in _module_roots(REPO_ROOT / root_name):
            problems.extend(problems_in(directory))

    if problems:
        return GateResult(ok=False, detail="\n".join(problems))
    return GateResult(ok=True, detail="")
