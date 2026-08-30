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

## Landed after the state file was first written
T-0004/5/6 shipped together as one session (DEC-0025 §4) — gates 5 jurisdiction-guard,
6 placeholder-scan, 7 module-contract. **Seven gates registered**, `make verify` exits 0 in
~5m23s, 53 tests, tree byte-identical across a full run (after DEC-0026: 5m31s, 58 tests). Each gate observed rejecting for real in
a copied tree. Verified by the Lead independently, not only reported.

**`make verify` is now 5m31s.** That is the number to attack if the loop gets painful; the lever
is the same one T-0002d used — copied-tree proofs registering only the gate under test.

## DEC-0026 is closed
Gate 7 shipped at T-0006 checking only the *topmost* `__init__.py`-bearing directory on a path.
Under that rule it checked `src/engine/` and skipped all seven `src/engine/*` contexts
`module-map.md` names — green while enforcing nothing on the code it exists to guard.

Closed the other way by the Lead: **a module directory is every package under `src/` or `tools/`,
at any depth, excluding a `tests/` tree.** `tools/gates/` is therefore a module and now carries
`tools/gates/readme.ai.md`; the gate-module contracts moved there out of `tools/readme.ai.md`,
which now stops at the runner. The regression is pinned by
`test_gate_module_contract.py::test_a_package_nested_inside_a_module_is_checked_too`, and it was
observed failing under the old rule before the fix landed: `make verify` printed
`PASS  gate 7  module-contract` over a tree with a module carrying no contract at all.

Still untested: `src/`. DEC-0026's Reopens-if is the thing the first `src/` task should read —
`src/engine` will be reported as a module directory in its own right if it carries an
`__init__.py`, which is correct, not an exception to carve out.

**Watch for this failure mode generally: a session narrowing a rule so its own tree passes.** The
review question that catches it is in DEC-0026's last section.

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
