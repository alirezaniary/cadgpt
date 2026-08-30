"""Gate 15 — test balance (DEC-0010, `docs/process/testing-strategy.md`).

50/50 unit and integration by count, enforced per module at 40-60%. Classification is
**explicit**, never inferred from a file's path or name: a test carrying
`@pytest.mark.integration` is integration, every other test is unit. Inferring from a
filename would miscount silently the moment a file is renamed.

A module is in scope for this gate when it is a module directory
(`tools.gates.module_contract`'s walk: any directory under `src/` or `tools/` carrying an
`__init__.py`, at any depth) that owns its own `tests/` subdirectory. A module with no
`tests/` of its own has nothing this gate reports on — `tools/gates` today shares
`tools/tests/` with its parent rather than owning a tree of its own
(`tools/gates/readme.ai.md`'s own Tests section), so only `tools` is in scope until that
changes.

A module with fewer than `MIN_TESTS_TO_ENFORCE` tests is reported in the table but never
fails: a ratio over so few tests is noise, not signal
(`docs/roadmap/tasks/T-0007-test-discipline-gates.md`).
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from tools.gates import REPO_ROOT
from tools.gates.module_contract import SCAN_ROOTS, module_directories

if TYPE_CHECKING:
    from tools.verify import GateResult

MIN_INTEGRATION_RATIO = 0.40
MAX_INTEGRATION_RATIO = 0.60

MIN_TESTS_TO_ENFORCE = 4
"""Below this many tests in a module, the ratio is reported but does not fail the gate."""


@dataclass(frozen=True)
class ModuleCounts:
    """One module's test counts. `module` is a path relative to the repository root, for
    a stable, reviewable table row."""

    module: str
    unit: int
    integration: int

    @property
    def total(self) -> int:
        return self.unit + self.integration

    @property
    def integration_ratio(self) -> float:
        """0.0 when a module has no tests at all. `verdict` never sees such a module —
        `_counts_for` only reports modules with at least one test — so this is purely a
        safe default against a directly constructed zero-test `ModuleCounts`."""
        return self.integration / self.total if self.total else 0.0

    @property
    def enforced(self) -> bool:
        return self.total >= MIN_TESTS_TO_ENFORCE

    @property
    def in_band(self) -> bool:
        return MIN_INTEGRATION_RATIO <= self.integration_ratio <= MAX_INTEGRATION_RATIO


def _row(counts: ModuleCounts) -> str:
    ratio_pct = round(counts.integration_ratio * 100)
    band = "in band" if counts.in_band else "OUTSIDE 40-60% band"
    enforcement = "" if counts.enforced else " (fewer than 4 tests, not enforced)"
    return (
        f"{counts.module}: {counts.unit} unit / {counts.integration} integration "
        f"({ratio_pct}% integration, {band}){enforcement}"
    )


def verdict(counts: list[ModuleCounts]) -> GateResult:
    """The whole rule, over already-computed counts — a constructed list of
    `ModuleCounts` proves it directly, with no filesystem or subprocess involved.

    `detail` is the per-module table, always, on PASS as well as FAIL (DEC-0024) — a run
    that checked the balance and found it fine still says what it found, so a run that
    checked nothing cannot look the same as one that did.
    """
    from tools.verify import GateResult

    failing = [c for c in counts if c.enforced and not c.in_band]
    detail = "\n".join(_row(c) for c in counts)
    return GateResult(ok=not failing, detail=detail)


def _modules_with_tests() -> list[Path]:
    """Every module directory, under every `SCAN_ROOTS` root, that owns its own `tests/`
    subdirectory — the module-contract walk (DEC-0026), filtered to the modules this gate
    has anything to report on."""
    modules: list[Path] = []
    for root_name in SCAN_ROOTS:
        for module in module_directories(REPO_ROOT / root_name):
            if (module / "tests").is_dir():
                modules.append(module)
    return modules


def _collected_ids(*marker_args: str) -> list[str]:
    """Every test node id `pytest --collect-only -q` reports under `marker_args` — a real
    collection, nothing executed, so this cannot itself spawn anything that runs a test
    body."""
    completed = subprocess.run(
        ["uv", "run", "--group", "dev", "pytest", "--collect-only", "-q", *marker_args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode not in (0, 1, 5):
        # 0: tests collected. 5: no tests collected (a marker matched nothing). 1: a
        # collection error. Anything else is `pytest` itself failing to run at all.
        raise RuntimeError(
            f"$ uv run --group dev pytest --collect-only -q {' '.join(marker_args)}\n"
            f"exited {completed.returncode}\n{completed.stdout}{completed.stderr}"
        )
    return [line.strip() for line in completed.stdout.splitlines() if "::" in line]


def _owning_module(node_id: str, modules: list[Path]) -> Path | None:
    """The module in `modules` whose own `tests/` directory `node_id`'s file sits under,
    or `None` if it sits under none of them. Ties broken by the deepest module, so a
    module nested inside another's `tests/` tree is not mistakenly credited to the
    outer one — no such nesting exists today, but the walk that finds `modules` does not
    assume it never will (DEC-0026)."""
    file_part = node_id.partition("::")[0]
    file_path = (REPO_ROOT / file_part).resolve()
    best: Path | None = None
    for module in modules:
        owns = (module / "tests").resolve()
        if not file_path.is_relative_to(owns):
            continue
        if best is None or len(module.parts) > len(best.parts):
            best = module
    return best


def _counts_for(modules: list[Path]) -> list[ModuleCounts]:
    """Real per-module unit/integration counts, from a real, unmocked collection of the
    whole test tree. Collection only — nothing here executes a test."""
    integration_ids = _collected_ids("-m", "integration")
    unit_ids = _collected_ids("-m", "not integration")

    tallies: dict[Path, list[int]] = {module: [0, 0] for module in modules}
    for node_id in unit_ids:
        owner = _owning_module(node_id, modules)
        if owner is not None:
            tallies[owner][0] += 1
    for node_id in integration_ids:
        owner = _owning_module(node_id, modules)
        if owner is not None:
            tallies[owner][1] += 1

    return [
        ModuleCounts(
            module=str(module.relative_to(REPO_ROOT)), unit=unit, integration=integration
        )
        for module, (unit, integration) in tallies.items()
        if unit + integration > 0
    ]


def run() -> GateResult:
    """Gate 15. Real, per-module counts from a real `pytest` collection, never mocked and
    never executed — classification comes from `@pytest.mark.integration` alone."""
    return verdict(_counts_for(_modules_with_tests()))
