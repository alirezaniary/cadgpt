# CLAUDE.md — stable rules

The constitution of this repository. Rules here change only by a logged decision in
`decisions/`. Everything else — plans, tasks, module docs — is downstream of this file
and may change freely.

`prd.md` is the product source of truth. This file is the *engineering* source of truth:
how work is decided, decomposed, built, proved and recorded.

---

## 0. Roles

| Party | Owns |
| --- | --- |
| **Stakeholder** (the human) | Direction. Which outcome we pursue, what "worth building" means, real-world facts only they can obtain. |
| **Lead** (Claude, this session) | Product ownership and engineering. Every technical decision. Decomposition. Task specs. Review. |
| **Subagent** | One bounded task, one session, from a written spec. Decides nothing. |

The stakeholder is asked for **directions, never details**. A question to the stakeholder
is legitimate only if two different answers produce two materially different products.
Anything else the Lead decides and logs.

A subagent that meets an unresolved decision **does not decide**. It writes a decision
stub with `Status: OPEN` into `decisions/` and stops. Escalation is a file, not a guess.

---

## 1. Product invariants — never renegotiated

Verbatim in force from `prd.md` §3. A task that requires bending one of these is not a
task, it is a decision request.

- **I1** — The language model never evaluates a rule.
- **I2** — The language model never authors geometry freehand.
- **I3** — We do not build what the open ecosystem already ships.
- **I4** — The product is jurisdiction-agnostic.
- **I5** — Every finding cites a resolvable basis.
- **I6** — No relationship with the software vendors.
- **I7** — The system never asserts compliance it did not establish.

**I1 and I2 are machine-checked, not remembered.** They are enforced twice: by the
dependency graph (the engine distribution does not depend on any inference client, so
the import is not merely forbidden, it is unresolvable) and by declarative import
contracts in CI. See `docs/ddd/05-import-contracts.md`.

`prd.md` §12 is a **closed decision log**. Those decisions are settled. Do not re-open,
re-argue or "improve" one. If evidence genuinely contradicts one, that is a decision
request to the stakeholder citing the Reopens condition printed beside it — never a
quiet deviation.

---

## 2. Modelling law

These four are the rules most likely to be violated by a well-meaning agent, because
each violation looks locally reasonable.

**Physical kind, never code role.** The model records what a thing measurably *is*. A
designation a code confers — habitable, egress component, light well, occupancy class,
fire compartment — is assigned at check time by a selector inside a rule pack. Never a
field, never a property name, never read from the input file.
*Test:* if two authorities could disagree about it, it is a role.

**Every quantity names its measurement convention, in its name.** `NetFloorArea_InsideFace`,
not `Area`. A bare number is not a quantity and may not appear in the model, a rule, or
a finding. Quantities arriving in the input file are unverified *claims*; they enter as
evidence and are re-derived under an explicit convention before any rule reads them.

**Measure, never invent.** Computing a quantity from geometry the designer authored is
measurement and is safe. Synthesizing a semantic entity the designer did not author —
a space, a boundary, a classification — is invention and is forbidden. Missing input is
reported, never filled in.

**Three-valued, always.** Status is `PASS | FAIL | INDETERMINATE`. Applicability is
`APPLIES | DOES_NOT_APPLY | UNDETERMINED_APPLICABILITY`. `INDETERMINATE` is never mapped
to `PASS` anywhere — not in an aggregate, a count, a summary, a report, an overlay or an
API response. A check that did not run is visible as a check that did not run.

---

## 3. Build guards

Mechanical, in CI, failing the build. Not review checklists.

| Guard | Fails when |
| --- | --- |
| Jurisdiction guard | A rule, pack, derivation, module or property name contains a country, code, jurisdiction or clause reference (I4). |
| Import contracts | Any checking-engine module reaches an inference client, a model SDK, or the assistance layer (I1, I2). |
| Quote linter | An encoded parameter disagrees with the source quote stored beside it. |
| IDS audit | A compiled `.ids` fails buildingSMART IDS-Audit-tool. |
| Compile drift | Committed compiled output differs from what the compiler regenerates from source. |
| Fixture gate | A rule lacks both a passing and a failing fixture. |
| Derivation promotion | A derivation enters the shared set below 3 rules across 2 clauses. |
| Placeholder scan | `TODO`, `FIXME`, `pass  # stub`, `"placeholder"`, or an unraised `NotImplementedError`. |
| Module contract | A module directory lacks a conforming `readme.ai.md`. |

Running them is one command. See `docs/architecture/harness.md`.

---

## 4. How work is decided and decomposed

Five levels. `docs/process/decomposition.md` is the method.

```
L0  Goal          one sentence, never changes
L1  Outcome       a state of the world the stakeholder can judge
L2  Capability    a coherent observable ability
L3  Slice         one vertical behaviour, crossing every layer, with fixtures
L4  Task          one subagent session
```

Two hard rules:

**Expand one level at a time, on one branch.** Do not decompose a level until the level
above it is settled. Do not expand a branch the stakeholder has not chosen. Breadth
before depth, always.

**Prerequisite order is absolute.** No part is started while anything it depends on is
unbuilt. Every task spec names its prerequisites and the evidence each one is complete.
`docs/roadmap/dependency-order.md` is the graph; it is the schedule.

---

## 5. Subagent sessions

Work is done by many small sessions, never one long one. Context length is a defect.

A task is subagent-ready only when all of the following are true:

1. It fits one session with room to spare — roughly one module, under ~400 lines of new code.
2. Its input and output contracts are written down and typed.
3. Its context file list is **exhaustive** — the agent reads those files and no others.
4. Its acceptance is a command with an exit code, not a description.
5. Its prerequisites are all complete, with evidence.

If any is false, the task is not ready; decompose further or unblock the prerequisite.
`docs/process/task-spec.md` is the format.

---

## 6. Code standards

Domain-driven design and OOP as *analysis and boundary* discipline, not folder ceremony.
`docs/ddd/` is the analysis; `docs/architecture/module-map.md` is what it becomes on disk.

- Types at every boundary. `mypy --strict`. No `Any` crossing a module edge.
- Domain objects are immutable value objects unless they have a genuine lifecycle.
- An invariant is enforced in one place — the aggregate that owns it — never re-checked defensively.
- Ubiquitous language is binding: the name in `docs/ddd/02-ubiquitous-language.md` is the name in the code. A synonym is a bug.
- **No scaffolding.** No file exists in anticipation. No abstraction with one implementation and no second one planned. No configuration option nothing reads. If it is not needed by a current slice, it is not written.
- **Inherit before writing.** Before writing anything in `prd.md` §6's inventory, stop: that is a decision request. Replacing our code with an inherited component is always the preferred direction of change.

---

## 7. Tests

50/50 unit and integration by count, enforced per module and reported by the harness.

- **Minimum mocking.** Mock only at a genuine external boundary that cannot run locally — a paid API, a vendor application. Never mock our own code, a filesystem, a database or an IFC file. Run the real library over a small real model.
- **Behaviour crosses layers.** Every behaviour has at least one test that enters at the outermost real entry point and exits at the real output. A behaviour proven only inside one layer is not proven.
- **Fixtures are code.** Test models are generated by a committed deterministic script, never committed as opaque binaries — a fixture nobody can read in a diff cannot be reviewed.
- Deterministic. No network, no clock, no ordering luck, no randomness without a pinned seed.

`docs/process/testing-strategy.md` has the detail.

---

## 8. Documentation

**Every decision is written down, whoever made it.** A decision reached in conversation
and not written to `decisions/` did not happen and will be re-litigated.
`decisions/TEMPLATE.md`: Problem → Constraints → Decision → Expected result → Reopens if.

**Every module carries a `readme.ai.md`** — the module's contract, written for the next
agent, who will read it instead of the code. Fixed sections, machine-checkable.
`docs/process/readme-ai-convention.md`.

Documentation is written in the same task as the code, by the same agent, or the task is
not done.

---

## 9. Definition of done

Extends the global rule in `~/.claude/CLAUDE.md`; both apply.

A task is done when, and only when:

1. `make verify` passes clean.
2. The **real path executed once** — the actual entry point over real input, output shown. Not a unit test.
3. **Wiring shown** — a handler, recipe, route, rule or migration counts only when registered where it runs, and the registration line is quoted in the report.
4. No placeholders. An unavoidable stub raises `NotImplementedError` and is listed as **NOT DONE** in the report.
5. `readme.ai.md` written or updated.
6. Any decision taken is in `decisions/`.

"Tests pass" is not evidence. This repository's oracle problem is the product's own
subject matter: a suite can pass while the system is wrong. Report honestly — partial is
reported as partial, with exactly what remains.
