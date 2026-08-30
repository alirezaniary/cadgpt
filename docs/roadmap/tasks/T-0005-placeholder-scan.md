# T-0005 — Placeholder scan (gate 6)

Slice: S0.4 · Capability: P0 · Outcome: O1

## Prerequisites
| Requires | Evidence |
| --- | --- |
| T-0004 | `make verify` exits 0 and prints "5 gates registered" |

## Objective
Catch code that was never finished but looks finished. This is the gate against the specific
failure mode of generated code: a silent placeholder is worse than a missing feature, because a
missing feature is visible.

## Context — read these and nothing else
- `CLAUDE.md`
- `docs/process/definition-of-done.md`
- `tools/verify.py`, `tools/gates/jurisdiction.py` (shape reference)

## Contract
```python
# tools/gates/placeholder.py
def run() -> GateResult:
    """Fail on any of, under src/ and tools/:
      - TODO / FIXME / XXX / HACK in a comment or string
      - a function body that is only `pass` or `...`
      - a literal "placeholder" / "not implemented" / "dummy" returned or assigned
      - `raise NotImplementedError` that is unreachable, or a bare `NotImplementedError`
        with no message
    detail names file:line and which pattern matched."""
```

**The permitted case:** `raise NotImplementedError("<why, and what it blocks>")` reached on the
first line of a body. `docs/process/definition-of-done.md` condition 4 allows exactly this, and
requires it be listed as **NOT DONE** in the completion report. The gate enforces the message;
the report is a human obligation the gate cannot check.

Use `ast` for structure, not regex. A regex cannot tell a `pass` that is a stub from a `pass`
inside an `except` clause that is legitimately doing nothing — and a gate that flags the second
will be disabled within a week.

## Invariants this task must uphold
- No suppression mechanism. Do not add a `# noqa`-style escape hatch. If a pattern is wrong, fix
  the pattern; an escape hatch converts this gate into a suggestion.
- cost tier 1.

## Files
Create: `tools/gates/placeholder.py`, `tools/tests/test_gate_placeholder.py`
Modify: `tools/verify.py` (registration), `tools/readme.ai.md`
Forbidden: everything else.

## Tests
Unit (4): `TODO` in a comment fails; a body that is only `pass` fails; a bare
`raise NotImplementedError` fails; `raise NotImplementedError("blocked on T-0009")` passes.
Integration (4): a bad file makes `make verify` exit non-zero naming file:line; a `pass` inside
`except` passes; a `...` in a Protocol body or a stub `.pyi` passes; the real tree passes.
Mocking: none.

## Acceptance
```
make verify                      # exits 0, prints "6 gates registered"
uv run --group dev pytest tools/tests/test_gate_placeholder.py -q
```

## Deliverables
Code · tests (4/4) · `tools/readme.ai.md` updated · completion report.

## If you hit an unresolved decision
OPEN decision record, stop, report.
