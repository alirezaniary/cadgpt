# L3 — slices of P0

> **P0 — the verification harness exists, and every gate has proven it can fail.**

Five slices, strictly ordered. Seven tasks. Scope is nine gates plus the registry, per DEC-0022.

## The shape

```
S0.1 ──▶ S0.2 ──▶ S0.3 ──▶ S0.4 ──▶ S0.5
 T-0001   T-0002   T-0003   T-0004     T-0007
                            T-0005
                            T-0006
```

## S0.1 — The gate registry runs and can fail
**Task:** T-0001
The repository skeleton — `pyproject.toml` with distributions and dependency groups, `Makefile`,
and `tools/verify.py`, which holds the registry, orders gates cheapest-first, runs all of them,
reports how many are registered, and exits non-zero if any fail.

**Proves:** a deliberately failing gate makes `make verify` exit non-zero. Without this
demonstrated first, every gate built afterwards is trusted rather than checked.

## S0.2 — Inherited static gates
**Task:** T-0002 — gates 1, 2, 14 (ruff, mypy --strict, pytest)
Configuration and registration, not new logic. Each gets a fixture that violates it and a test
asserting the gate rejects that fixture.

Gate 3 (import contracts) is **not** here — it needs `src/` packages and ships with C1.1.

## S0.3 — The isolation proof
**Task:** T-0003 — gate 4
Build the engine-only environment and assert that importing an inference SDK raises
`ImportError`. This is the one gate that makes I1 a fact rather than a policy (DEC-0004), and it
is the only gate that tests the *environment* rather than the source.

Buildable at P0 with zero `src/` code: the claim under test is about what the dependency group
resolves, which is decided in `pyproject.toml`.

## S0.4 — Source guards
**Tasks:** T-0004 (jurisdiction), T-0005 (placeholder), T-0006 (module contract) — gates 5, 6, 7
Three scanners over `src/`, `tools/` and `packs/`. Split into three tasks because each is an
independent scanner with its own rules and its own adversarial fixtures, and three small specs
review better than one large one.

**All three scan an empty `src/` at P0.** Each is therefore proven by its bad fixture, never by
its scan target — which is exactly the case DEC-0016 was written for.

## S0.5 — Test discipline gates
**Task:** T-0007 — gates 15, 16
Test balance per module (40–60% unit/integration) and determinism (suite runs twice with varied
seeds, results must agree). Both measured against `tools/`' own tests, which exist by now.

## Done when
`make verify` exits 0, reports nine registered gates, and every one of the nine has a committed
test proving it exits non-zero on a deliberately bad input.
