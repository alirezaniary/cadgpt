# T-0002 — Register ruff, mypy --strict and pytest as gates 1, 2 and 14

Slice: S0.2 · Capability: P0 · Outcome: O1

## Prerequisites
| Requires | Evidence |
| --- | --- |
| T-0001 | `make verify` exits 0 and prints a registered-gate count; `pytest tools/tests/ -q` passes |

STOP if absent. Do not stub it.

## Objective
Three inherited tools become three registered gates, each proven to reject a bad input.

## Context — read these and nothing else
- `CLAUDE.md`
- `docs/architecture/harness.md`
- `tools/verify.py`, `tools/readme.ai.md`
- `decisions/DEC-0016-harness-before-code.md`

## Contract
Three modules exposing `run() -> GateResult`, registered in `REGISTRY`:

| # | Module | Wraps | cost |
| --- | --- | --- | --- |
| 1 | `tools/gates/lint.py` | `ruff check` + `ruff format --check` | 1 |
| 2 | `tools/gates/types.py` | `mypy --strict` | 2 |
| 14 | `tools/gates/tests.py` | `pytest` | 3 |

On failure, `detail` carries the tool's own output. Do not summarize or reformat it — the agent
reading it needs the real message.

## Invariants this task must uphold
- **Every gate ships with a proof it fails** (DEC-0016). A gate with no failing fixture is not
  merged.
- Configure `ruff` and `mypy` in `pyproject.toml`, not in separate config files — one place.
- `mypy --strict` covers `tools/` with no blanket ignores. A needed ignore is narrow, inline,
  and carries a reason.

## Files
Create: `tools/gates/__init__.py`, `tools/gates/lint.py`, `tools/gates/types.py`,
`tools/gates/tests.py`, `tools/tests/badfixtures/` (three deliberately bad files),
`tools/tests/test_gates_static.py`
Modify: `pyproject.toml` (tool config), `tools/verify.py` (registration only),
`tools/readme.ai.md`
Forbidden: everything else. No `src/`. **Gate 3 (import-linter) is not in scope** — it needs
`src/` packages and ships with C1.1 (DEC-0022).

## Tests
Unit (3): each gate returns `ok=False` and non-empty `detail` when its tool exits non-zero.
Integration (3): each bad fixture, placed where the tool scans it, makes `make verify` exit
non-zero and name that gate.
Mocking: none. Run the real tools.

The bad fixtures must sit somewhere the gates scan but the repo's own quality gates do not
reject at rest — put them under an excluded path and have the test copy them into place, or the
repository cannot pass its own verify. Solve this explicitly; do not disable a gate to work
around it.

## Acceptance
```
make verify                      # exits 0, prints "3 gates registered"
uv run --group dev pytest tools/tests/ -q
```
Report the `make verify` output and the three gate lines.

## Deliverables
Code · tests (3/3) · `tools/readme.ai.md` updated · completion report.

## If you hit an unresolved decision
OPEN decision record, stop, report.
