# T-0003 — Prove the engine environment cannot resolve an inference client (gate 4)

Slice: S0.3 · Capability: P0 · Outcome: O1

## Prerequisites
| Requires | Evidence |
| --- | --- |
| T-0002 | `make verify` exits 0 and prints "3 gates registered" |

## Objective
The most important gate in the repository. It proves I1 is a **fact** rather than a policy: in
an environment built from the `engine` dependency group, importing an inference SDK raises
`ImportError` regardless of what any source file says.

## Context — read these and nothing else
- `CLAUDE.md`
- `docs/ddd/05-import-contracts.md`
- `decisions/DEC-0004-distributions-enforce-i1.md`
- `docs/architecture/module-map.md`
- `tools/verify.py`, `tools/gates/lint.py` (as a shape reference)

## Why this is separate from gate 3
Gate 3 checks that nobody *wrote* a forbidden import. It is defeatable by `importlib`, a plugin
entry point, or a raw HTTP call to an inference endpoint. Gate 4 checks the forbidden thing is
**not installable**. If the package is not in the resolved environment, the call cannot be made
however it is spelled.

## Contract
```python
# tools/gates/isolation.py
FORBIDDEN_IN_ENGINE: tuple[str, ...] = ("anthropic", "openai", "httpx", "requests", "aiohttp")

def run() -> GateResult:
    """Resolve the engine dependency group into a throwaway environment and assert that
    importing each FORBIDDEN_IN_ENGINE module raises ImportError there.
    ok=False if any import succeeds; detail names which one and via which dependency."""
```

HTTP clients are on the list deliberately. An inference client reached over raw HTTP is still an
inference client, and forbidding only SDK names invites exactly that workaround.

## Invariants this task must uphold
- **I1**, in its strongest form. This gate is its enforcement.
- The gate must fail if a *transitive* dependency pulls a forbidden package in. Check the
  resolved environment, not the declared list.
- cost tier 3. It builds an environment; it is allowed to be slow.

## Files
Create: `tools/gates/isolation.py`, `tools/tests/test_gate_isolation.py`
Modify: `tools/verify.py` (registration), `pyproject.toml` (only if the engine group is
mis-declared), `tools/readme.ai.md`
Forbidden: everything else.

## Tests
Unit (2): a resolved environment containing a forbidden package produces `ok=False` naming it;
a clean one produces `ok=True`.
Integration (2): the real engine group resolves and every forbidden import fails there; adding a
forbidden package to the engine group makes `make verify` exit non-zero (add it, assert, revert
— the test must leave `pyproject.toml` unchanged).
Mocking: none.

## Acceptance
```
make verify                      # exits 0, prints "4 gates registered"
python -m tools.verify --list    # gate 4 present
pytest tools/tests/test_gate_isolation.py -q
```
Report the gate 4 output line verbatim. This is the line a customer or regulator gets shown.

## Deliverables
Code · tests (2/2) · `tools/readme.ai.md` updated · completion report.

## If you hit an unresolved decision
OPEN decision record, stop, report.
