"""Read an IDS rule set without running it.

Uploaded rule sets are arbitrary files. A malformed one must be refused at the door rather
than half-parsed at check time, because a rule set that partly loads under-checks the
model while producing a report that looks complete.

`ifctester.ids.open(validate=True)` checks against the bundled buildingSMART schema. The
stricter check is buildingSMART's own IDS-Audit-tool, which is a .NET dependency and not
wired in here; `docs/decisions.md` records the trap it carries -- it can exit with upstream
status 256, which truncates to shell exit code 0, so its output lines have to be asserted
rather than its exit code.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import ifctester.ids

from cadgpt_engine.errors import InvalidIdsError


@dataclass(frozen=True, slots=True)
class SpecificationSummary:
    name: str
    description: str
    instructions: str
    cardinality: str
    ifc_versions: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class RuleSetSummary:
    """What a rule set says about itself, plus what it will actually check.

    The specification list is the useful half: it is how a user confirms the file they
    uploaded contains the rules they meant, before they spend a model check finding out.
    """

    title: str
    description: str
    author: str
    version: str
    date: str
    specifications: tuple[SpecificationSummary, ...]

    @property
    def specification_count(self) -> int:
        return len(self.specifications)


def _info(specs: Any, key: str) -> str:
    return str(specs.info.get(key, "") or "")


def inspect_ruleset(ids_path: Path) -> RuleSetSummary:
    """Validate `ids_path` against the IDS schema and describe what it contains."""
    try:
        specs = ifctester.ids.open(str(ids_path), validate=True)
    except Exception as exc:
        raise InvalidIdsError(str(exc)) from exc

    specifications = tuple(
        SpecificationSummary(
            name=spec.name or "",
            description=spec.description or "",
            instructions=spec.instructions or "",
            cardinality=str(spec.get_usage()),
            ifc_versions=tuple(spec.ifcVersion or ()),
        )
        for spec in specs.specifications
    )

    if not specifications:
        # A rule set that checks nothing would report a clean pass over any model. That
        # is precisely the false confidence this product exists to prevent.
        raise InvalidIdsError("The rule set contains no specifications.")

    return RuleSetSummary(
        title=_info(specs, "title"),
        description=_info(specs, "description"),
        author=_info(specs, "author"),
        version=_info(specs, "version"),
        date=_info(specs, "date"),
        specifications=specifications,
    )
