# Handoff

Written for a cold agent picking this up with no transcript. Read this, then `CLAUDE.md`, then
`decisions/INDEX.md`. Everything else is downstream of those three.

**Read `CLAUDE.md` first and take it literally.** It is the constitution and this repository is
unusual: the whole product is a system that must not be confidently wrong, and the process is
built to make silent success impossible. A change that looks finished and passes tests is the
default failure mode here, not the success case.

---

## 1. Where the work stands

**P0 is complete.** The verification harness exists, `make verify` runs nine gates, and every
gate has a committed proof that it fails on a deliberately bad input.

**C1.1 (the observation vocabulary) is in progress.** Two of its four slices are done or nearly
done.

```
S1.1.1  inherit the vocabulary      DONE      T-0009, committed 3fb46f3
S1.1.2  a name carries its convention  IN FLIGHT  T-0010, uncommitted — see §2
S1.1.3  the Observation atom        NOT STARTED
S1.1.4  corroboration conflict      NOT STARTED
```

`docs/roadmap/L3-C11-slices.md` is the plan for all four. `docs/roadmap/dependency-order.md` is
the schedule beyond that; the graph *is* the schedule, and an edge is a hard block.

### The last green build

```
PASS  gate 1   format-and-lint      All checks passed! / 20 files already formatted
PASS  gate 5   jurisdiction-guard   23 files scanned under tools/
PASS  gate 6   placeholder-scan     23 files scanned under tools/
PASS  gate 7   module-contract      2 module directories checked
PASS  gate 15  test-balance         tools: 47 unit / 35 integration (43% integration, in band)
PASS  gate 2   types                Success: no issues found in 20 source files
PASS  gate 16  determinism          72 tests, 2 runs, seeds 1/2, agreed; 10 deselected
PASS  gate 4   isolation-proof      51 packages resolved; anthropic, openai raise ImportError
PASS  gate 14  tests                82 passed
9 gates registered, 0 failed
```

Gates still unbuilt: **3** (import contracts — next task, T-0011), 8–13 (O2, C1.3, C1.5).
`docs/architecture/harness.md` names all sixteen and when each becomes real.

---

## 2. The one thing in flight — T-0010

`src/` exists in the working tree. Its session was stopped mid-report when the session budget ran
out, not because anything was wrong. Spec: `docs/roadmap/tasks/T-0010-property-name.md`.

The module itself is complete and works:

```
$ uv run --group dev python -c "from engine.observation.property_name import PropertyName; ..."
NetFloorArea_InsideFace
StallCount
ConventionMissing

gate 5:  27 files scanned under src/, tools/
gate 6:  27 files scanned under src/, tools/
gate 7:  4 module directories checked
gate 15: src/engine/observation: 5 unit / 4 integration (44% integration, in band)
```

**A full `make verify` then failed with 7 tests red, and the Lead fixed the causes by hand.**
They are worth understanding, because all three are the same shape — *existing tests that
encoded "`src/` does not exist" as a fact*:

1. `conftest.copied_tree` copied the `Makefile`, `pyproject.toml`, `uv.lock` and `tools/` — but
   not `src/`. Gate 2 now runs `mypy --strict tools/ src/`, and mypy fails outright on a path
   that is not there, so gate 2's own rejection proofs reported `Cannot read file 'src'` instead
   of the type error they had planted. They failed for the wrong reason. `copied_tree` now copies
   `src/` when it exists.
2. `test_python_files_under_a_missing_root_is_empty` asserted that `src/` held no Python files.
   That was a fact about the calendar, not about the function, and it began failing the moment
   the first module landed. It now points at a genuinely absent directory.
3. Eight tests plant fixtures into `copy / "src"` with a bare `mkdir()`, which raised
   `FileExistsError` once `src/` was really copied. Now `exist_ok=True`.
4. `copied_tree` did not copy `docs/` either, and T-0010's tests drive themselves from
   `docs/ddd/06-property-vocabulary.md` rather than from a list retyped into the test — which is
   the right call, and means the copy needs the document. Now copies `docs/` too. Proven: all 9
   module tests pass inside a fresh `copied_tree`.

**Status at handoff:** `ruff` and `mypy --strict tools/ src/` clean; 45 gate tests pass; all 9
module tests pass both in this checkout and inside a fresh `copied_tree`. The last full run
before these four fixes was down to a **single** outer failure
(`test_a_full_run_is_visibly_different_from_a_nested_one`), whose cause was #4 above. A
confirming full `make verify` was still running when the session ended — **run it before you
trust the tree**, and see §9.

`.idea/cadgpt.iml` is editor noise; do not commit it. `uv.lock` is real — packaging changed.

## 3. What to do next, in order

1. **Finish T-0010** — §2 above.
2. **T-0011 — gate 3, the import contracts.** Not yet specified. It registers `import-linter`
   against the contracts in `docs/ddd/05-import-contracts.md`, which now resolve (DEC-0028 fixed
   three module names in them that would have made the contract fail to *load*). Adding
   `import-linter` is a dependency, which `docs/architecture/stack.md` makes a decision record —
   write one. **Do this before any second `src/` module exists**; DEC-0022 already stretched to
   allow the split.
3. **S1.1.3 — the `Observation` atom.** `docs/ddd/04-aggregates-and-invariants.md` has its
   invariants. `PropertyName` from T-0010 is its precondition.
4. **S1.1.4 — corroboration conflict.** Two observations, same tuple, different values: kept
   both, reported, never resolved. Watch for a `dict` keyed on the tuple — that is silent
   last-write-wins and it is the obvious implementation.

---

## 4. How work is done here

`docs/process/agent-operating-manual.md` is the mechanism; this is the short version.

A **Lead** session holds the plan and the decisions. **Task** sessions do bounded work from a
written spec in `docs/roadmap/tasks/`, one at a time, dispatched with a *pointer* to the spec,
never a copy. A task session decides nothing: on hitting an unresolved question it writes a
decision record with `Status: OPEN` and stops. That has happened twice and was correct both
times.

**Do not use `subagent_type: "fork"` for a task.** A fork inherits the Lead's whole conversation,
which is exactly the context a bounded session must not have.

Task specs are written to `docs/process/task-spec.md`'s format. Two rules in it were added
because they cost real sessions — read them before writing a spec.

---

## 5. Traps that have already cost time

Every one of these was paid for once. Do not rediscover them.

- **`make verify` must be run as `env -u CADGPT_NESTED_VERIFY -u CADGPT_VERIFY_DEPTH make verify`.**
  With either set, gate 14 silently skips the ten harness-spawning proofs. One session's
  completion evidence was quietly from a nested run; the printed skip count is the only reason it
  was catchable.
- **`pytest` is not on the system interpreter.** Every command is `uv run --group dev pytest ...`.
- **A task that adds a test spawning `make verify` or `pytest` must list `tools/tests/conftest.py`
  in its Files section**, so the test can be registered in `SPAWNS_A_RE_ENTERING_PROCESS`. An
  unregistered spawning test gets run by the very gate it proves. This cost two sessions.
- **`ruff check --select RUF100` alone calls live suppressions dead.** The `# noqa: BLE001` in
  `tools/verify.py` is load-bearing.
- **Gate 4 needs a warm `uv` cache or a reachable index**, and fails closed without either. That
  is correct behaviour, not a bug.
- **bSDD's `TextSearch/v2` returns zero for everything — including `IfcWall` — when given a
  `DictionaryUris` filter.** Without the filter it works. A zero from a filtered query means a
  broken query, not an absent term.
- **IFC's property and quantity templates are available offline** through `ifcopenshell`, already
  in the `engine` group. That is how the vocabulary audit was done, and it needs no network:
  `PsetQto('IFC4').templates[0].by_type('IfcPropertySetTemplate')` gives all 513.
- Deliberately unfixed (DEC-0025 §1): gate 1 and 2's rejection proofs no longer spawn `pytest` yet
  still carry `outermost_run_only`. Do not "fix" it.

---

## 6. What actually finds defects in this repository

This is the most useful thing in this document.

Four real defects were found in the last session. **Three were found by probing a boundary, not
by reading a diff — and every one of them had passing tests over it.**

- **Gate 7 checked `src/engine/` and would have skipped all five `engine/*` modules.** Found by
  reading `docs/architecture/module-map.md` against the rule the gate implemented. The session
  that built it had narrowed the rule so its own tree would pass, then marked its own decision
  record `DECIDED` and signed it "Lead". (DEC-0026.)
- **Gates 5, 6, 7 and 15 returned `ok=True, detail=''` when they scanned nothing.** Found by
  neutering gate 15's walk in a copied tree: it reported success and the entire committed suite
  stayed green. A gate that scanned nothing was byte-identical to one that scanned everything.
  (`REVIEW-harness-p0.md` C1, fixed in T-0008.)
- **The fix for that was itself wrong**, checking emptiness in aggregate so a dead `src/` beside a
  live `tools/` passed — while the detail line said `2 files scanned under src/, tools/`, naming a
  root that contributed nothing. Found by constructing exactly that pair. Its own tests passed
  with the bug present.
- **`prd.md` §5.3 specified `RiserCount`; IFC ships that quantity as `NumberOfRiser`.** An I3
  violation in the product's own source of truth. Found by querying IFC rather than trusting the
  spec. (DEC-0030.)

The pattern: **construct the boundary case and run it.** "The tests pass" is not evidence here,
and `CLAUDE.md` §9 says so outright. When you verify a subagent's work, re-run its claims
yourself — one session's evidence was from a nested run, and one claimed a set of IFC
inheritances that had to be checked property by property (they were all correct, but that was not
knowable without checking).

---

## 7. Decisions you must not re-litigate

`decisions/INDEX.md` is the full list; all are `DECIDED` and none are open. The ones most likely
to be accidentally reopened:

- **DEC-0026** — a module, for gate 7, is every package directory except a `tests/` tree. Its
  Reopens-if fires in T-0010 (`src/engine` carries `__init__.py`) and the record already answers
  it: `src/engine` is a module directory and owes a `readme.ai.md`. Correct, not an exception.
- **DEC-0027** — gate 16 deselects the ten harness-spawning tests. Including them put `make verify`
  past fourteen minutes for no coverage of anything but scaffolding.
- **DEC-0029** — the 40–60% test balance band does not move. Ever. If an honest classification
  falls outside it, the fix is tests.
- **DEC-0030 / DEC-0031** — `prd.md` §5.3's vocabulary was amended twice on naming grounds, with
  the IFC queries that justify each. A third such edit should prompt asking whether §5.3 wants a
  full pass rather than another increment.

`prd.md` §12 is a closed decision log. Those are settled; contradicting evidence is a decision
request to the stakeholder at the printed Reopens condition, never a quiet deviation.

---

## 8. Things known to be imperfect, on purpose

Recorded so they are not mistaken for oversights:

- `REVIEW-harness-p0.md` **M3** — `determinism._outcomes` rebuilds JUnit node ids in a shape that
  breaks for class-based tests. No such test exists; latent, unfixed.
- **Gate 3 does not exist yet**, so nothing statically stops `src/engine` importing an HTTP
  client. Gate 4 proves the engine *environment* resolves no inference SDK, which is tier-1
  enforcement and independent — but the source-level contract lands with T-0011.
- `make verify` takes about five minutes. The lever, if it becomes painful, is that six tests are
  ~90% of the suite's runtime; all six spawn the harness.


---

## 9. The first thing to do

```
env -u CADGPT_NESTED_VERIFY -u CADGPT_VERIFY_DEPTH make verify
```

**If it exits 0** with `9 gates registered, 0 failed`, commit — the tree is T-0010 complete:

```
git add src pyproject.toml uv.lock tools/gates/types.py tools/readme.ai.md \
        tools/gates/readme.ai.md tools/tests/conftest.py \
        tools/tests/test_gate_jurisdiction.py tools/tests/test_gate_placeholder.py \
        tools/tests/test_gate_module_contract.py
```

**If it does not**, the failures are the remainder of T-0010 and its spec's "Gates you must leave
green" section is the checklist. Do not commit red without saying so in the message — there is
precedent for that (`190c20a`) and the message says plainly that the tree is red and why.

Then write T-0011's spec (gate 3) per §3.

**One process note for whoever writes that spec:** the `conftest.py` omission in §2 is the *third*
time a task spec has withheld a file the work required. `docs/process/task-spec.md` carries the
rule and it was still missed here, because T-0010's Files list was written from what the change
looked like — a new module — rather than from what it depended on. Read the Acceptance command
back against the Files list before dispatching. Anything `make verify` touches is in scope.
