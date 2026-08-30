# Session state — handoff

Written at the end of the first build session. A cold session should be able to resume from
this file plus `CLAUDE.md` and `decisions/INDEX.md`, without reading any transcript.

## Where this is

**P0 is complete, reviewed, and its review findings are closed.** `make verify` exits 0 with
nine gates and 0 failed, 82 tests, none skipped, in about 4m50s. Every gate reports what it
scanned, and every gate has a committed proof it can fail.

```
PASS  gate 1   format-and-lint   All checks passed! / 20 files already formatted
PASS  gate 5   jurisdiction-guard  23 files scanned under tools/
PASS  gate 6   placeholder-scan    23 files scanned under tools/
PASS  gate 7   module-contract     2 module directories checked
PASS  gate 15  test-balance        tools: 47 unit / 35 integration (43% integration, in band)
PASS  gate 2   types               Success: no issues found in 20 source files
PASS  gate 16  determinism         72 tests, 2 runs, seeds 1/2, agreed; 10 deselected
PASS  gate 4   isolation-proof     51 packages resolved; anthropic, openai raise ImportError
PASS  gate 14  tests               82 passed in 293.69s
9 gates registered, 0 failed
```

Gates still unbuilt: 3 (ships with the first `src/` package, S1.1.2), 8–13 (O2, C1.3, C1.5).
`docs/architecture/harness.md` says which and when.

## In flight
**T-0009** — the property vocabulary audit, S1.1.1, the first slice of C1.1. Writes no code:
one table in `docs/ddd/06-property-vocabulary.md` resolving every `prd.md` §5.3 name to an
inherited IFC quantity or an authored-here reason.

## Next, in order
1. Review and integrate T-0009.
2. **S1.1.2** — the property name carries its convention, or it does not exist. This creates the
   first `src/` package, and **gate 3 (import contracts) ships in the same task** (DEC-0022).
   Read DEC-0026's Reopens-if before creating `src/engine`: if it needs an `__init__.py`, it
   becomes a module directory owing a `readme.ai.md`, which is correct, not an exception.
3. S1.1.3 the `Observation` atom, S1.1.4 corroboration conflict. See
   `docs/roadmap/L3-C11-slices.md`.

## Decisions taken this session
- **DEC-0026** — a module, for gate 7, is every package except a `tests/` tree. The record was
  first written DECIDED and signed "Lead" *by the subagent that raised it*; reopened and closed
  the other way. Under the shipped rule gate 7 checked `src/engine/` and skipped all five
  `engine/*` modules `module-map.md` names.
- **DEC-0027** — gate 16 deselects the harness-spawning tests. Six tests were 234 of the suite's
  258 seconds; including them would have put `make verify` past fourteen minutes.
- **DEC-0028** — `docs/ddd/05-import-contracts.md` named a layer `compilation` that is not a
  module, omitted `observation` entirely, and forbade a module that does not exist. Gate 3's
  contracts would not have loaded. Fixed before S1.1.2 meets them.
- **DEC-0029** — pre-existing tests are marked `integration` by what they do; the 40–60% band was
  not moved.

## What actually finds defects here
Three of the four real defects this session were found by **probing a boundary, not reading a
diff**, and each had passing tests over it:

- gate 7 skipping five modules — found by reading `module-map.md` against the rule;
- gates 5 and 6 masking a dead scan root while reporting it as scanned — found by constructing
  a dead root beside a live one;
- gate 15 returning `ok=True, detail=''` over an empty scan with the whole suite still green —
  found by neutering its walk in a copied tree.

The review that found the last one is `REVIEW-harness-p0.md`. Its M3 (JUnit node ids break for
class-based tests) is recorded and unfixed; no such test exists yet.

## Standing corrections a new session should not rediscover
- `pytest` is not on the system interpreter. Every command is `uv run --group dev pytest ...`.
- **Run `make verify` as `env -u CADGPT_NESTED_VERIFY -u CADGPT_VERIFY_DEPTH make verify`.** With
  either set, gate 14 silently skips the ten spawning proofs and the evidence is from a nested
  run. A real depth-0 run reports 82 tests, none skipped. One session's completion evidence was
  quietly nested; the printed skip count is the only reason it was catchable.
- **A task that adds a test spawning `make verify` or `pytest` must list `tools/tests/conftest.py`
  in its Files section**, so the test can be registered in `SPAWNS_A_RE_ENTERING_PROCESS`. Omitting
  it has now cost two sessions; `docs/process/task-spec.md` carries the rule.
- `ruff check --select RUF100` alone calls live suppressions dead. The `# noqa: BLE001` in
  `tools/verify.py` is load-bearing.
- Gate 4 needs a warm `uv` cache or a reachable index, and fails closed without either.
- bSDD's `TextSearch/v2` returns zero for everything — including `IfcWall` — when given a
  `DictionaryUris` filter. Without the filter it works. A zero from a filtered query is a broken
  query, not an absent term.
- Known and deliberately not fixed (DEC-0025 §1): the gate 1 and gate 2 rejection proofs no
  longer spawn `pytest` yet still carry `outermost_run_only`.
