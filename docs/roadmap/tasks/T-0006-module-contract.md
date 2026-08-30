# T-0006 — Module contract checker (gate 7)

Slice: S0.4 · Capability: P0 · Outcome: O1

## Prerequisites
| Requires | Evidence |
| --- | --- |
| T-0005 | `make verify` exits 0 and prints "6 gates registered" |

## Objective
Every module directory carries a conforming `readme.ai.md`. This is the file the next agent
reads *instead of* the code, so its absence or drift is what turns short sessions back into long
ones.

## Context — read these and nothing else
- `CLAUDE.md`
- `docs/process/readme-ai-convention.md`
- `decisions/DEC-0011-readme-ai-as-contract.md`
- `tools/verify.py`, `tools/gates/placeholder.py` (shape reference)

## Contract
```python
# tools/gates/module_contract.py
REQUIRED_SECTIONS: tuple[str, ...] = (
    "Purpose", "Context", "Contract", "Invariants enforced here",
    "Depends on", "Must not depend on", "Tests", "How to run it", "Open questions",
)

def run() -> GateResult:
    """For every directory under src/ and tools/ containing an __init__.py:
      - readme.ai.md exists
      - all nine sections present, as `## ` headings, in order
      - no section body is empty
      - 'Open questions' says 'None.' or lists something — never blank
    detail names the directory and what is missing."""
```

Presence and order, not content quality — a machine cannot judge whether a Purpose is honest.
Empty-body detection is the one quality check worth making, because a heading with nothing
under it is the common way this convention decays.

## Invariants this task must uphold
- Nine sections, in the order given in `docs/process/readme-ai-convention.md`. Do not reorder
  them here; if the order is wrong, that is a change to the convention and a decision record.
- `src/` is empty at P0, so **this gate is proven by its fixtures, not by its scan target**
  (DEC-0016). It must still find and check `tools/readme.ai.md`, which exists.
- cost tier 1.

## Files
Create: `tools/gates/module_contract.py`, `tools/tests/test_gate_module_contract.py`
Modify: `tools/verify.py` (registration), `tools/readme.ai.md` (bring it into full conformance)
Forbidden: everything else.

## Tests
Unit (4): a package with no `readme.ai.md` fails; one missing a section fails naming it; one
with sections out of order fails; one with an empty "Open questions" fails.
Integration (4): a bad package under `tmp_path` makes the gate exit non-zero; a directory
without `__init__.py` is skipped; `tools/readme.ai.md` passes; the real tree passes.
Mocking: none.

## Acceptance
```
make verify                      # exits 0, prints "7 gates registered"
pytest tools/tests/test_gate_module_contract.py -q
```

## Deliverables
Code · tests (4/4) · `tools/readme.ai.md` conforming · completion report.

## If you hit an unresolved decision
OPEN decision record, stop, report.
