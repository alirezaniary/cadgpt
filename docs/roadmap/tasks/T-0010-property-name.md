# T-0010 — A property name carries its convention, or it does not exist

Slice: S1.1.2 · Capability: C1.1 · Outcome: O1

## Prerequisites
| Requires | Evidence |
| --- | --- |
| P0 | `make verify` exits 0, "9 gates registered, 0 failed" |
| T-0009 | `docs/ddd/06-property-vocabulary.md` exists, 27 rows |
| DEC-0030, DEC-0031 | Both `DECIDED`; `prd.md` §5.3 amended |

## Objective
The first `src/` module. `PropertyName` parses a §5.3 property name into a base quantity and a
measurement convention, and **refuses to construct** a name that denotes a measurement and
carries no convention.

This is the invariant `docs/ddd/04-aggregates-and-invariants.md` puts on `Observation`
construction, built one slice before `Observation` itself so that it is a constructor
precondition rather than a validator over existing data. A validator can be skipped.

## Context — read these and nothing else
- `CLAUDE.md`
- `docs/ddd/06-property-vocabulary.md` — **the data this module encodes**; the closed sets come
  from its table, not from your reading of `prd.md`
- `decisions/DEC-0031-tread-length-and-exit-width-conventions.md`
- `decisions/DEC-0026-module-contract-scope.md` — read the Decision section before creating any
  directory
- `docs/architecture/module-map.md`
- `docs/process/readme-ai-convention.md`
- `pyproject.toml`
- `tools/gates/types.py` — gate 2's paths, which you extend

## Contract
```python
# src/engine/observation/property_name.py

CONVENTIONS: frozenset[str]
"""The closed set of measurement-convention segments, from
docs/ddd/06-property-vocabulary.md. 13 members."""

CONVENTION_FREE_BASES: frozenset[str]
"""Base quantities that legitimately carry no convention — counts, ratios, and the
single-reading dimensions that document justifies individually. 12 members."""

@dataclass(frozen=True)
class PropertyName:
    base: str
    convention: str | None

    @classmethod
    def parse(cls, raw: str) -> PropertyName: ...

    def __str__(self) -> str: ...

class ConventionMissing(ValueError): ...
class UnknownConvention(ValueError): ...
```

- `parse` splits on the **first** underscore: `NetFloorArea_InsideFace` → base
  `NetFloorArea`, convention `InsideFace`.
- A name with no underscore whose base is in `CONVENTION_FREE_BASES` parses with
  `convention=None`.
- A name with no underscore whose base is **not** in `CONVENTION_FREE_BASES` raises
  `ConventionMissing`, naming the base and saying a measurement must state its convention.
- A segment not in `CONVENTIONS` raises `UnknownConvention`, naming the segment and listing the
  set. A convention is added by amending `docs/ddd/06-property-vocabulary.md` and this constant
  together — say so in the error.
- `str(PropertyName.parse(n)) == n` for every one of the 27 names.

**The counts are given (13 and 12) so a mismatch is visible.** If your reading of the audit
produces different numbers, that is a finding — report it, do not adjust the constants to hit
the stated count, and do not adjust the count to match your reading without saying so.

## What this module is not
Not `Observation`. Not a quantity, a value, or a unit. It is the *name* and nothing else.
No convenience constructor takes a bare number — `docs/roadmap/L3-C11-slices.md` names that as
the beginning of the end of I4, and it will look reasonable when you want it.

## Layout, and what it costs
`docs/architecture/module-map.md` puts this at `src/engine/observation/`.
`docs/ddd/05-import-contracts.md`'s layers contract uses `containers = ["engine"]`, so `engine`
must be an importable package: **`src/engine/__init__.py` exists.**

DEC-0026's Reopens-if fires here and is already answered by that record's Decision: `src/engine`
therefore *is* a module directory and owes its own `readme.ai.md`. That is correct, not an
exception to carve out. Gate 7 will demand it and you write it.

`pyproject.toml` needs `src/` importable as a package root. `[tool.uv] package = false` and the
comment above it saying "No src/ layout exists yet" both stop being true.

## Gates you must leave green
Registering the first `src/` package changes what four existing gates see. All of this is your
task, not a follow-up:

- **Gate 2** — `tools/gates/types.py` runs `mypy --strict tools/`. Extend it to `src/` too.
  `tools/readme.ai.md` already records that the task creating the first `src/` package does this.
- **Gate 5, 6** — now scan `src/` as a real root. They fail closed on a root that exists and
  yields nothing (T-0008), so an empty `src/` is a failing build.
- **Gate 7** — `src/engine/` and `src/engine/observation/` are both module directories and both
  need a conforming `readme.ai.md`, nine sections, in order, none empty.
- **Gate 15** — `src/engine/observation/` owns a `tests/` directory, so it enters the balance
  table and must land inside 40–60%. Mark integration tests `@pytest.mark.integration`. Do not
  touch the band.

## Invariants this task must uphold
- **I4.** No jurisdiction, country, code body or clause reference in any identifier. Gate 5 now
  scans this module.
- **Immutable.** `PropertyName` is a frozen value object. No setter, no `with_convention`.
- **No scaffolding.** Only what this slice needs. No `Observation`, no `Quantity`, no base class
  with one implementation, no `py.typed` unless something requires it.
- **No new dependency.** `import-linter` and gate 3 are T-0011's, deliberately — see below.

## Why gate 3 is not here
DEC-0022 puts a gate in the task that creates the artefact it guards, and gate 3 guards `src/`
modules. It is split out because registering it means adding `import-linter`, and
`docs/architecture/stack.md` makes a dependency a decision record rather than a task-level
choice. Splitting the dependency decision from the module keeps both reviewable.

**I1 is not unguarded in the interval.** Gate 4 proves the engine environment resolves no
inference SDK, which is tier-1 enforcement (`docs/ddd/05-import-contracts.md`) and independent of
gate 3. T-0011 follows immediately and before any second `src/` module.

## Files
Create: `src/engine/__init__.py`, `src/engine/readme.ai.md`,
`src/engine/observation/__init__.py`, `src/engine/observation/property_name.py`,
`src/engine/observation/readme.ai.md`, `src/engine/observation/tests/test_property_name.py`
Modify: `pyproject.toml`, `tools/gates/types.py`, `tools/readme.ai.md`,
`tools/gates/readme.ai.md`
Forbidden: everything else. In particular `prd.md`, `docs/ddd/06-property-vocabulary.md`, and
`tools/tests/conftest.py` — this task adds no test that spawns the harness.

## Tests
In `src/engine/observation/tests/`, beside the module (`module-map.md`).
Unit: each rejection path with its own name; `convention=None` for a convention-free base;
round-trip `str(parse(n)) == n`.
Integration: **every one of the 27 names in `docs/ddd/06-property-vocabulary.md` parses**, driven
from the document's own table rather than a list retyped into the test — a retyped list proves
the test agrees with itself. Parse the Markdown table.
Mocking: none.

## Acceptance
```
env -u CADGPT_NESTED_VERIFY -u CADGPT_VERIFY_DEPTH make verify   # exits 0, 9 gates, 0 failed
uv run --group dev python -c "
from engine.observation.property_name import PropertyName
print(PropertyName.parse('NetFloorArea_InsideFace'))
print(PropertyName.parse('StallCount'))
try: PropertyName.parse('Area')
except Exception as e: print(type(e).__name__, e)"
```
Quote gate 5, 6, 7 and 15's coverage lines — each must now show `src/` counted.

## Deliverables
The module · both `readme.ai.md` files · tests · a report quoting the four coverage lines and
the real-path output above.

## If you hit an unresolved decision
OPEN decision record, next free number from `decisions/INDEX.md`, stop, report.
