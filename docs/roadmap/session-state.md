# Session state — handoff

Written at the end of the first build session. A cold session should be able to resume from
this file plus `CLAUDE.md` and `decisions/INDEX.md`, without reading any transcript.

## Done, on `main`

| Commit | What |
| --- | --- |
| `f371b96` | T-0001 — gate registry, `make verify` |
| `9a1e0e7` | Lead — DEC-0023 closed, gate 4 overclaim corrected in `harness.md`, T-0001 spec defects fixed |
| `55acdec` | T-0001a — single registration path, runner survives a raising gate, `tools/readme.ai.md` |
| `7ff744a` | T-0002 — gates 1, 2, 14 (ruff, mypy --strict, pytest) |
| `e493c03` | T-0002a — a gate reports what it did not run (DEC-0024) |
| `1811d91` | T-0002b — the harness's guards demonstrated failing, not asserted |
| `c6cc194` | T-0002c — tests plant into a copied tree; DEC-0024 proven end to end |
| `519067f` | T-0002d — summary from stdout; copied-tree proofs register only the gate under test |
| `709ea58` | T-0003 — gate 4, the isolation proof; I1 is a fact |
| `dec0025` | DEC-0025 — stop recursing on harness self-proof; Sonnet builds; siblings ship together |

**Five gates registered**: 1 format-and-lint, 2 types, 4 isolation-proof, 14 tests.
`make verify` ≈ 2.5 min, exit 0. 25 tests, 0 skipped. `git status` is byte-identical across a
full suite run — no test writes into this checkout.

## In flight when the session ended
One Sonnet build session implementing **T-0004, T-0005 and T-0006 together** (gates 5
jurisdiction, 6 placeholder scan, 7 module contract) per DEC-0025 §4. Its result was not
integrated. **Check `git status` first**: if `tools/gates/{jurisdiction,placeholder,module_contract}.py`
are present and uncommitted, verify and commit them; if the tree is clean, the task never landed
and must be re-dispatched.

Verification for those three, before committing:
```
make verify                                  # exits 0, "7 gates registered, 0 failed"
python3 -m tools.verify --list               # seven gates, cost order
uv run --group dev pytest tools/tests/ -q    # all pass, 0 skipped
git status --porcelain                       # identical before and after the pytest run
```
Plus each gate observed **rejecting** in a copied tree (DEC-0016). No `src/` exists, so gates 5
and 7 must PASS cleanly on an absent `src/` and be proven to reject against a bad `src/` created
inside a copy.

## Next, in order
1. **T-0007** — `docs/roadmap/tasks/T-0007-test-discipline-gates.md`, gates 15 (test balance) and
   16 (determinism). Last P0 task. Its spec carries a warning: under a strict reading of the
   unit/integration rule `tools/` sits at 32%, **below** the 40–60% band, so the gate may fail on
   arrival. That is the gate working — report it, do not tune the rule to pass.
2. **P0 complete** → run `/adversarial-review` over the whole harness, then the first `src/` slice.
   `docs/roadmap/L3-P0-slices.md` and `docs/roadmap/dependency-order.md` are the schedule.

## Standing corrections a new session should not rediscover
- `pytest` is not on the system interpreter. Every acceptance command is
  `uv run --group dev pytest ...`. Bare `uvx mypy` cannot see the dev group either; use
  `uvx --with pytest mypy --strict tools/`.
- `ruff check --select RUF100` alone reports every *unselected* rule as non-enabled and so calls
  live suppressions dead. The `# noqa: BLE001` in `tools/verify.py` is load-bearing.
- Gate 4 needs a warm `uv` cache or a reachable index. It fails closed when it has neither, which
  is correct and has been observed for real.
- Known and deliberately not fixed (DEC-0025 §1): the gate 1 and gate 2 rejection proofs no longer
  spawn `pytest`, so they cannot re-enter the harness, yet they still carry `outermost_run_only`.
  Two proofs are skipped in a depth-1 child for a reason no longer true of them. Depth-0 runs are
  unaffected.
