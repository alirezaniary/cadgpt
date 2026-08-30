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

## 2. The one thing in flight — T-0010, uncommitted

`src/` exists in the working tree and **is not committed**. Its session was stopped mid-report
when the session budget ran out, not because anything was wrong.

Spec: `docs/roadmap/tasks/T-0010-property-name.md`. Verified by hand before handoff:

```
$ uv run --group dev pytest src/engine/observation/tests/ -q
9 passed

$ uv run --group dev python -c "from engine.observation.property_name import PropertyName; ..."
NetFloorArea_InsideFace
StallCount
ConventionMissing

gate 5:  ok=True  27 files scanned under src/, tools/
gate 6:  ok=True  27 files scanned under src/, tools/
gate 7:  ok=True  4 module directories checked
gate 15: ok=True  src/engine/observation: 5 unit / 4 integration (44% integration, in band)
```

**What is NOT established:** a full `make verify` over the tree with `src/` present. Gate 2's
mypy paths, gate 1, gate 4, gate 14 and gate 16 have not been confirmed since `src/` appeared.

**Do this first:**

```
env -u CADGPT_NESTED_VERIFY -u CADGPT_VERIFY_DEPTH make verify
```

If it exits 0 with `9 gates registered, 0 failed`, commit `src/`, `pyproject.toml`,
`tools/gates/types.py`, `tools/readme.ai.md`, `tools/gates/readme.ai.md`. If it does not, fix what
it names — the spec's "Gates you must leave green" section lists exactly what changes when `src/`
first exists, and that list is the bulk of T-0010.

`.idea/cadgpt.iml` and `uv.lock` are also modified. `uv.lock` is real (packaging changed);
`.idea/` is editor noise and should not be committed.

---

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
