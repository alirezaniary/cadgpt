# The verification harness

The harness is how this repository stays correct without a human reading every diff. It is
the mechanism behind `CLAUDE.md` §3 and §9, and it is the answer to *"how do you get
AI-generated code you can trust?"* — you do not trust it, you constrain it and then you
check it deterministically.

**One command.**

```
make verify
```

If it passes, the change is admissible. If it fails, the task is not done. There is no
third state, and no reviewer judgement in the loop.

## What it runs, in order

Ordered cheapest-first so a broken change fails in seconds rather than minutes.

| # | Gate | Tool | Fails when |
| --- | --- | --- | --- |
| 1 | Format & lint | `ruff` | Style drift, unused imports, common defects |
| 2 | Types | `mypy --strict` | Any untyped boundary; `Any` crossing a module edge |
| 3 | **Import contracts** | `import-linter` | I1/I2 violated; layering violated (`docs/ddd/05-import-contracts.md`) |
| 4 | **Isolation proof** | `uv` + import probe | The engine environment resolves an inference SDK |
| 5 | **Jurisdiction guard** | `tools/` | A country, code, jurisdiction or clause reference appears in any identifier under `src/` (I4) |
| 6 | **Placeholder scan** | `tools/` | `TODO`, `FIXME`, `pass  # stub`, `"placeholder"`, or an unraised `NotImplementedError` |
| 7 | **Module contract** | `tools/` | A `src/` module directory lacks a conforming `readme.ai.md` |
| 8 | **Quote linter** | `tools/` | An encoded parameter disagrees with its stored source quote, under numeral and unit normalisation |
| 9 | **IDS audit** | IDS-Audit-tool | A compiled `.ids` is not valid IDS 1.0 |
| 10 | **Compile drift** | `tools/` | Regenerating compiled output from source does not reproduce the committed artefact |
| 11 | **Fixture gate** | `tools/` | A rule lacks a passing and a failing fixture, or a pack's fixtures do not run |
| 12 | **Missing derivation** | `tools/` | A rule requires an observation type no registered derivation can produce |
| 13 | **Derivation promotion** | `tools/` | A derivation is in the shared set below 3 rules across 2 clauses |
| 14 | Tests | `pytest` | Any test fails |
| 15 | **Test balance** | `tools/` | A module's unit/integration split is outside 40–60% |
| 16 | **Determinism** | `pytest` ×2, seeds varied | Two runs disagree |

Gates 3–13 and 15–16 are the ones that make this repository different from a normal one.
Each exists because a specific silent failure is possible without it, and each is named in
`prd.md` or in `docs/ddd/`.

## Why gate 4 exists separately from gate 3

Gate 3 checks that nobody *wrote* a forbidden import. Gate 4 checks that the forbidden thing
is *not installable* in the engine environment at all.

Gate 3 alone can be defeated by `importlib`, a plugin entry point, or a raw HTTP call to an
inference endpoint. Gate 4 cannot: if the package is not in the resolved environment, the
call cannot be made regardless of how it is spelled. This is the difference between a policy
and a fact, and I1 needs to be a fact.

## Gate 8 in particular

The quote linter is small and it guards the largest correctness risk in the product.

A mistranscribed bound — 1.10 encoded where the source says 1.20 — produces a **cited,
deterministic, reproducible, wrong PASS**. Every other guard passes. The rule runs. The
finding cites a real clause. The report is defensible-looking and wrong. The only other
check on it is fixtures, written by whoever wrote the rule, carrying the same misreading.

With the source quote stored beside the parameter, the error is visible in a diff and
mechanically detectable. It requires numeral and unit normalisation for each script the
corpus is written in — Persian numerals and Persian unit words for the first corpus.

`prd.md` §11 Gate 1 asks us to *measure* the rate at which drafts fail this linter, because
that number is the size of the confident-wrong-PASS risk and it is only observable during
ratification.

## What the harness deliberately does not do

- **It does not check that a rule is right.** No machine can. That is what ratification is for, and why a named human is in the path and not automatable away.
- **It does not measure coverage-by-line.** Line coverage over generated code measures nothing. Behaviour coverage across layers is the standard here (`docs/process/testing-strategy.md`).
- **It does not review design.** Design is decided in `decisions/` before the task exists.

## The harness is the product's own subject matter

This repository's oracle problem is the one the product exists to solve. A green suite over
a broken system is precisely the failure `prd.md` §2 describes, and it has happened before
in this workspace. That is why `CLAUDE.md` §9 requires the real path executed and the wiring
line quoted, *in addition to* a clean harness — the harness is necessary and it is not
sufficient.
