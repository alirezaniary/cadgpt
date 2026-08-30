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

**How the gates invoke their tools.** Each shells out via `uv run --group dev <tool> ...`, and
`ruff`, `mypy` and `pytest` are declared in the `dev` dependency group. DEC-0005 already settled
that these three are the static enforcement layer, so declaring them executes a settled decision
rather than taking a new one — but do not add a fourth tool.

`uvx mypy --strict tools/` is **not** viable and must not be used: `uvx` builds an isolated
environment with no dev dependencies, so `tools/tests/test_verify.py` importing `pytest` yields
`Cannot find implementation or library stub for module named "pytest"`. Gate 2 must run mypy in
an environment where the dev group is present.

**Gate 14 recurses unless you stop it.** `tools/tests/test_verify.py` proves the runner can fail
by copying `Makefile`, `pyproject.toml` and `tools/` into `tmp_path` and running real `make
verify` there. Once gate 14 wraps `pytest`, that copied tree's `make verify` would run pytest,
which would copy a tree and run `make verify` again, without bound. Fix it in the **test**, not
with a production flag: the helper must **reset** the copied `REGISTRY` — emit `REGISTRY.clear()`
before the `REGISTRY.append(Gate(...))` block it writes into the copied `tools/verify.py` — so the
copy runs exactly the one deliberately-failing gate and nothing else. Do not reintroduce a
registry-injection surface in `tools/verify.py`; T-0001a removed one for good reason.

## Invariants this task must uphold
- **Every gate ships with a proof it fails** (DEC-0016). A gate with no failing fixture is not
  merged.
- Configure `ruff` and `mypy` in `pyproject.toml`, not in separate config files — one place.
- `mypy --strict` covers `tools/` with no blanket ignores. A needed ignore is narrow, inline,
  and carries a reason.
- The `ruff` rule selection must include **`RUF100`** (unused `noqa`). `CLAUDE.md` forbids
  suppressing a warning, so every `noqa` that survives must be load-bearing; one left behind for
  a rule the selection later drops reads as though a real defect were being silenced. Note that
  `ruff check --select RUF100` alone reports every *other* rule as "non-enabled" and so calls
  live suppressions dead — RUF100 must be enabled **alongside** the real selection, never on its
  own. Getting this backwards already cost one round of review here.

## Files
Create: `tools/gates/__init__.py`, `tools/gates/lint.py`, `tools/gates/types.py`,
`tools/gates/tests.py`, `tools/tests/badfixtures/` (three deliberately bad files),
`tools/tests/test_gates_static.py`
Modify: `pyproject.toml` (tool config, and `ruff`/`mypy`/`pytest` in the `dev` group),
`tools/verify.py` (registration only), `tools/tests/test_verify.py` (reset the copied `REGISTRY`
in the failure-proof helper, per the recursion note above), `tools/readme.ai.md`
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
