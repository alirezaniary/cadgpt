# DEC-0024 — A harness whose own test suite invokes it must report what it did not run

**Status:** DECIDED
**Date:** 2026-08-30
**Decided by:** Lead
**Raised by:** Review of T-0002
**Affects:** `tools/gates/tests.py`, `tools/verify.py`, `tools/tests/`, `docs/architecture/harness.md`

## Problem
Gate 14 runs `pytest`. The test suite proves the gates work by running real `make verify`.
So `make verify` transitively runs itself, without bound, unless something stops the descent.

T-0002 stopped it with an environment marker: a test that spawns `make verify` sets
`CADGPT_NESTED_VERIFY=1` in the child, and tests that spawn processes skip when they see it.
The descent terminates one level down, and a plain `make verify` still runs the whole suite
(5.9 s, 13 tests) — verified.

The mechanism is sound. Its **reporting** is not:

```
$ env CADGPT_NESTED_VERIFY=1 make verify
python3 -m tools.verify
PASS  gate 1  format-and-lint
PASS  gate 2  types
PASS  gate 14  tests
3 gates registered, 0 failed          exit 0, in 0.98 s
```

That output is **byte-identical** to a full run, and every one of the seven failure proofs was
skipped. A CI job, a `.env`, or one developer who exports the variable once gets a green harness
that proved nothing. This is the "green suite over a broken system" failure `CLAUDE.md` §9 and
`docs/architecture/harness.md` name as this repository's central risk — reproduced inside the
harness itself, which is the worst possible place for it.

`run_gates` prints a gate's `detail` only on failure, so a passing gate 14 discards pytest's
`6 passed, 7 skipped` summary entirely. Nothing anywhere reports it.

## Constraints
- No production surface exists for injecting or excluding gates; T-0001a removed one deliberately
  and it must not come back through a test-support door.
- `harness.md`: "The runner prints how many gates are registered, so the harness's own coverage is
  visible rather than assumed." The same standard has to apply *inside* a gate.
- No env-based scheme is unspoofable. Anything that reads ambient state can be lied to.
- DEC-0016: every gate ships with a proof it fails. A guard is not exempt from being proven.

## Options
1. **Leave it.** The mechanism works at the depth people actually invoke it. Rejected: the failure
   is silent, and a silent green is the one outcome this repository is built to make impossible.
2. **Make the guard unspoofable.** There is no such scheme; any marker is an environment variable
   by another name, and a depth counter is spoofable at any depth.
3. **Accept that the guard is spoofable and make its effect visible**, so a run that skipped its
   proofs cannot be mistaken for one that ran them.

## Decision
**Option 3.** Three consequences, implemented in T-0002a:

1. `run_gates` prints a gate's `detail` whenever it is non-empty, on **PASS as well as FAIL**.
   A gate that has something to report about its own coverage reports it.
2. Gate 14 returns pytest's summary line as its `detail` on success. A run with skips is then
   visibly different from a full run, at the depth a person reads.
3. The guard is proven like a gate: one test asserts that with no marker present nothing is
   skipped, and the skip set is narrowed to exactly the tests that spawn a process which
   re-enters the harness.

`make verify` alone is therefore **not** sufficient evidence that the suite ran. Every task's
acceptance already runs `uv run --group dev pytest tools/tests/ -q` directly, and that is not
redundant with `make verify` — it is the check that the harness's own proofs executed. This is
now a stated reason, not an accident of how the specs were written.

## Expected result
A `make verify` whose gate 14 skipped tests says so, in its own output, at every depth. The
byte-identical-green case above becomes impossible.

## Reopens if
Gate 14 ever stops being able to report a summary — for instance if the suite is sharded across
processes and no single summary exists — at which point the skip count has to be surfaced some
other way, but it still has to be surfaced.

## Consequences accepted
`run_gates` now prints on PASS, so a chatty gate could make a clean run noisy. Accepted: a gate
that prints on success without needing to is a defect in that gate, and the fix is that gate
returning an empty detail, not the runner hiding it.
