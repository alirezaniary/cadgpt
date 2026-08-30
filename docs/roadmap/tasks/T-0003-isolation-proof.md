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
- `decisions/DEC-0023-engine-group-transitive-http-client.md`
- `docs/architecture/module-map.md`
- `tools/verify.py`, `tools/gates/lint.py` (as a shape reference)

## Why this is separate from gate 3
Gate 3 checks that nobody *wrote* a forbidden import. It is defeatable by `importlib` or a plugin
entry point. Gate 4 checks the forbidden thing is **not installable**. If the package is not in
the resolved environment, the call cannot be made however it is spelled.

**Read `decisions/DEC-0023` before writing a line of this.** It settles what this gate asserts and
what it does not. `ifctester` is a forced inherited component and it pulls `requests`, `urllib3`,
`flask` and `bcf-client` into the engine closure. They cannot be removed, so gate 4 does not
assert their absence — it asserts they are the *only* HTTP-capable packages there and that each
arrives by its recorded path. The raw-HTTP path is closed by gate 3 at C1.1, not here.

## Contract
```python
# tools/gates/isolation.py
FORBIDDEN_IN_ENGINE: tuple[str, ...] = ("anthropic", "openai")
"""Inference SDKs. Importing one in the engine environment must raise ImportError."""

HTTP_CAPABLE: tuple[str, ...] = ("requests", "urllib3", "httpx", "aiohttp", "flask", "bcf-client")
"""Every package we know can open a socket. Presence is not itself a failure — see below."""

ALLOWED_HTTP: tuple[tuple[str, str], ...] = (
    ("requests", "ifctester"),
    ("urllib3", "ifctester"),
    ("flask", "ifctester"),
    ("bcf-client", "ifctester"),
)
"""(package, reached_via) — an HTTP-capable package a forced inherited component drags in,
recorded with the component that forces it (DEC-0023). Adding a pair here is a decision record."""

def run() -> GateResult:
    """Resolve the engine dependency group into a throwaway environment, then assert:
    (a) importing each FORBIDDEN_IN_ENGINE module there raises ImportError;
    (b) every HTTP_CAPABLE package in the resolved closure appears in ALLOWED_HTTP and is
        reached via the dependency named beside it.
    ok=False if an inference SDK imports, or an HTTP-capable package is present that is
    unlisted or arrives by an unrecorded path; detail names it and prints its dependency path."""
```

(b) is the ratchet. `requests` is in the engine closure today and cannot be removed without
forking an inherited component, which I3 forbids. What the gate can guarantee is that the set
does not *grow* — a newly-introduced `httpx`, or a `requests` that starts arriving through
something other than `ifctester`, fails the build.

## Invariants this task must uphold
- **I1** as a fact: no inference SDK is importable in the engine environment.
- The gate must read the *resolved environment*, not the declared list — a transitive inference
  SDK fails it, and the HTTP allowlist is checked against the resolved closure with its paths.
- The gate must fail closed: if the environment cannot be resolved, that is `ok=False` with the
  resolver's error in `detail`, never a skip.
- cost tier 3. It builds an environment; it is allowed to be slow.

## Files
Create: `tools/gates/isolation.py`, `tools/tests/test_gate_isolation.py`
Modify: `tools/verify.py` (registration), `pyproject.toml` (only if the engine group is
mis-declared), `tools/readme.ai.md`
Forbidden: everything else.

## Tests
Unit (2): a resolved closure containing an inference SDK produces `ok=False` naming it; a
closure whose HTTP-capable packages are exactly `ALLOWED_HTTP`, by their recorded paths,
produces `ok=True`.
Integration (2): the real engine group resolves, every `FORBIDDEN_IN_ENGINE` import raises
ImportError there, and its HTTP-capable set is exactly `ALLOWED_HTTP`; adding `openai` to the
engine group makes `make verify` exit non-zero (add it, assert, revert — the test must leave
`pyproject.toml` unchanged).
Mocking: none.

## Acceptance
```
make verify                      # exits 0, prints "4 gates registered"
python -m tools.verify --list    # gate 4 present
uv run --group dev pytest tools/tests/test_gate_isolation.py -q
```
Report the gate 4 output line verbatim. This is the line a customer or regulator gets shown.

## Deliverables
Code · tests (2/2) · `tools/readme.ai.md` updated · completion report.

## If you hit an unresolved decision
OPEN decision record, stop, report.
