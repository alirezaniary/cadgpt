# Adversarial review — the P0 harness

Scope: `tools/verify.py`, `tools/gates/` (nine registered gates), `tools/tests/`, at
`0c0843c`. Milestone gate before the first `src/` module.

`make verify` is green: 9 gates registered, 0 failed, 65 tests, none skipped, tree
byte-identical afterwards. Verified independently at depth 0. Everything below is what that
green run does **not** establish.

DEC-0025 §1's deferred item (gate 1 and 2 rejection proofs still carrying
`outermost_run_only`) is not re-flagged here.

---

## C1 — Four gates cannot tell "checked everything" from "checked nothing", and no test notices

**Evidence — a real run, not an argument.** In a `conftest.copied_tree` copy, gate 15's module
walk was made to find nothing (one `and False`, chosen so no import becomes unused and gate 1
stays quiet):

```
$ uv run --group dev python -c "from tools.gates import test_balance; print(repr(test_balance.run()))"
GateResult(ok=True, detail='')

$ uv run --group dev pytest tools/tests/ -q
59 passed, 6 skipped in 180.47s
```

The gate that exists to measure test balance measured nothing, said nothing, passed, and **the
entire committed suite stayed green.** `make verify` would print `PASS  gate 15  test-balance`
with no detail beneath it.

The shape is not unique to gate 15:

```
gate 5 jurisdiction:     ok=True detail=''
gate 6 placeholder:      ok=True detail=''
gate 7 module_contract:  ok=True detail=''
gate 15 test-balance:    ok=True detail=''      (with a real tree: the per-module table)
```

**Why it matters.** DEC-0024 exists for exactly this and was applied only to the gates that wrap
an external tool: `run_tools` reports each tool's summary line so a run that skipped work is not
byte-identical to one that did. The four scanning gates were exempted, and `tools/readme.ai.md`
states the reasoning explicitly — that an empty detail is "the honest report" because "there is
no partial-coverage question for a full-tree `ast`/filesystem scan the way there is for a
summarised external tool."

The probe disproves that sentence. There is a partial-coverage question — a walk that returns
`[]`, a `SCAN_ROOTS` that stops matching, a rename of `tools/tests/` — and today it is
invisible in the output and uncaught by the suite. This is the repository's founding failure
mode reproduced inside the harness built to prevent it.

**Smallest fix.** Each scanning gate reports what it scanned in its success detail — a file
count for gates 5 and 6, a module count for 7 and 15 — and fails closed when a scan root that
exists yields zero subjects. Gate 4 already fails closed on an unrunnable proof; this is the
same rule applied to an unrun scan. `tools/readme.ai.md`'s paragraph asserting the opposite must
go with it.

**Not disputable without a counter-run**: the probe is reproducible in
`scratchpad/probe2/repo`.

---

## H1 — Gates 15 and 16 have no proof they fail through the shipped registration path

**Evidence.**

```
$ grep -rn "FAIL  gate" tools/tests/*.py
test_gates_static.py        FAIL  gate 1   format-and-lint
test_gates_static.py        FAIL  gate 2   types
test_gate_isolation.py      FAIL  gate 4   isolation-proof
test_gate_jurisdiction.py   FAIL  gate 5   jurisdiction-guard
test_gate_placeholder.py    FAIL  gate 6   placeholder-scan
test_gate_module_contract.py FAIL gate 7   module-contract
test_gates_static.py        FAIL  gate 14  tests
test_verify.py              FAIL  gate 1   raising-gate
```

Seven of nine registered gates have a committed proof that a bad input makes `make verify` exit
non-zero *through* `REGISTRY` and `run_gates`. Gates 15 and 16 have none. Their rules are proven
by calling `verdict()` directly with constructed inputs, and their registration is proven only
by `--list` printing nine.

Those are different claims. `verdict()` returning `ok=False` does not establish that
`test_balance.run()` reaches it over a real tree, nor that a `False` from either gate propagates
to a non-zero exit — which is the whole of DEC-0016's "every guard ships with a proof it fails."

Gate 15 *was* observed failing through `make verify` at `190c20a` (`FAIL  gate 15
test-balance`, `tools: 65 unit / 0 integration`). That is evidence in a commit message, not a
proof in the repository, and it is no longer reproducible now the tree is in band.

**Smallest fix.** Two rejection proofs in the existing pattern: a copied tree with
`only_gate(15)` and a planted skewed module, and one with `only_gate(16)` and a planted
hash-seed-dependent test, each asserting `FAIL  gate N` in `make verify`'s stdout. Note C1's fix
would give gate 15 a second failure mode worth pinning at the same time.

---

## M1 — `_deselected_count` reports "0 deselected" when it means "could not parse"

**Evidence.**

```
$ _deselected_count('65 passed in 3s')            -> 0
$ _deselected_count('57 passed, 8 deselected in 9s') -> 8
```

`determinism._DESELECTED_RE` searches stdout for `(\d+) deselected` and returns 0 on no match.
DEC-0027 §4 makes that number the gate's honesty mechanism — the thing that says a run covered
part of the suite rather than all of it. A parse failure therefore renders as `0 deselected`,
which is the *strongest* claim the gate can make ("I ran everything"), when what happened is
"I do not know what I ran."

Wrong direction to fail. `pytest` changing its summary wording is enough to trigger it.

**Smallest fix.** `_deselected_count -> int | None`; `verdict` renders `unknown` and returns
`ok=False`, or the summary line is asserted to have matched at all.

---

## M2 — `harness.md`'s gate table does not mention that gate 16 deselects eight tests

Gate 16's row reads `pytest ×2, seeds varied` / "Two runs disagree". It runs the suite **minus
the eight `spawns_harness` tests**, per DEC-0027 §1. The decision record says so; the table a
reader consults to learn what the harness checks does not.

**Smallest fix.** One clause in the row.

---

## M3 — `_outcomes` rebuilds node ids in a shape that breaks for class-based tests

`determinism._outcomes` builds `f"{classname.replace('.', '/')}.py::{name}"`. For a test inside a
class, JUnit's `classname` is `tools.tests.test_x.TestFoo`, yielding
`tools/tests/test_x/TestFoo.py::test_bar` — a path that does not exist. Such a test would be
mis-keyed in both runs identically, so it would not produce a false failure; it would silently
weaken the comparison.

No class-based tests exist today. Latent, and flagged because the comment claims the shape
matches `test_verify.py`'s, which has the same assumption.

---

## What this review did not find

No unwired component: all nine `REGISTRY` entries were confirmed against `tools/verify.py:76-84`
and all nine appear in a real `make verify`. No placeholder, no `TODO`, no silent
`NotImplementedError` — gate 6 scans for exactly those and passes. No mocking anywhere in
`tools/tests/`. The `spawns_harness` hook is checked against `SPAWNS_A_RE_ENTERING_PROCESS`
rather than trusted, and gate 16's deselection is proven by a fixture test that *raises if it
runs* — behaviour, not a count.
