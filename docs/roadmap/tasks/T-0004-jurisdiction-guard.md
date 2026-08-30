# T-0004 — Jurisdiction guard (gate 5)

Slice: S0.4 · Capability: P0 · Outcome: O1

## Prerequisites
| Requires | Evidence |
| --- | --- |
| T-0003 | `make verify` exits 0 and prints "4 gates registered" |

## Objective
I4 enforced mechanically rather than remembered: a country, code, jurisdiction or clause
reference appearing in any **identifier** under `src/` fails the build.

## Context — read these and nothing else
- `CLAUDE.md`
- `docs/ddd/02-ubiquitous-language.md`
- `decisions/DEC-0020-rules-are-data.md`
- `docs/architecture/module-map.md`
- `tools/verify.py`, `tools/gates/isolation.py` (shape reference)

## Contract
```python
# tools/gates/jurisdiction.py
def run() -> GateResult:
    """Parse every Python file under src/ and tools/ with ast.
    Fail if any identifier — module, class, function, variable, constant, or a string used
    as a property name — contains a jurisdictional token.
    detail names file:line and the offending identifier."""
```

**Identifiers, not text.** A docstring, a comment, or a clause quoted in a test may name a
country freely. `packs/` is data and is never scanned. The failure being prevented is a
jurisdiction compiled into the engine, not a mention of one.

Token list lives in one module-level constant with a comment on how to extend it. Cover at
minimum: country names and ISO codes, common code identifiers (`IBC`, `NBC`, `Eurocode`,
`ASHRAE`, `مقررات`), and clause-reference shapes (`clause_5_3_2`, `art14`, `sec_302`).

Match on word boundaries and on snake/camel segment boundaries. `iran` must fail;
`iteration`, `variance`, `secant` must not. Getting this wrong in either direction makes the
gate useless — noisy gates get disabled, silent ones prove nothing.

## Invariants this task must uphold
- **I4.** This gate is its enforcement.
- Zero false positives on the current tree, which must still pass.
- cost tier 1. AST parsing only, no environment work.

## Files
Create: `tools/gates/jurisdiction.py`, `tools/tests/test_gate_jurisdiction.py`
Modify: `tools/verify.py` (registration), `tools/readme.ai.md`
Forbidden: everything else. Do not create `src/`.

## Tests
Unit (4): a module named for a country fails; a function named `check_clause_5_3_2` fails; a
docstring naming a country passes; `iteration`/`variance`/`secant` pass (the false-positive
guard).
Integration (4): a bad file placed under `src/` makes `make verify` exit non-zero and names
file:line; the same content in a comment passes; the same content under `packs/` passes; the
real tree passes.
Mocking: none. `tmp_path` for constructed trees.

## Acceptance
```
make verify                      # exits 0, prints "5 gates registered"
uv run --group dev pytest tools/tests/test_gate_jurisdiction.py -q
```
Report the failure output for the bad fixture — it must name file, line and identifier.

## Deliverables
Code · tests (4/4) · `tools/readme.ai.md` updated · completion report.

## If you hit an unresolved decision
OPEN decision record, stop, report.
