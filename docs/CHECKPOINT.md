# Checkpoint — 2026-09-02, end of coordinator session 2

Session 2 was spent settling scope, not building. Four direction questions were put to the
product owner, answered, and written into `docs/decisions.md` and `prd.md` 12; `docs/plan.md`
Phase 3 was re-cut against the answers. Commit `7be0faf`. **No production code changed in this
session and no agent was dispatched.**

`docs/plan.md` is the route and `docs/tasks/` holds the detail. This file only records where
the loop is and what is unresolved.

## The MVP, now that it is settled

> The user uploads a model, picks which rules to run it against, and gets back a report file.

Four answers got it there. Full reasoning is in `docs/decisions.md` — do not re-litigate:

- **Rules are a catalogue we ship, not a file the architect uploads.** Seeded from existing
  public IDS sets so development never waits on authoring. The user selects by jurisdiction,
  region and version, and the selection is part of the job record. The product owner authors
  packs in a separate thread — Iranian building code first, then EU and US. **This loop builds
  the store, metadata, selection and seeding path, and no rule content.** User-uploaded rule
  sets already work, are not being removed, and are out of MVP scope as the primary path.
- **The first iteration reports and does not act.** Overlay, marked sheets and BCF export are
  out by decision. Acting on findings arrives with the agent layer and its permission levels
  (auto, edit, ask-first). This takes **gate 2 off the MVP's critical path**.
- **The deliverable is a generated Markdown report whose URL sits on the job record.** The
  in-app React view stays beside it, not under it.
- **The upload ceiling is measured against peak worker memory, not chosen.** Async removed the
  time constraint, not the memory one.

## Where the loop stopped

Phase 3 in progress. Unchanged from session 1 in code terms — session 2 moved the plan, not
the build.

| Task | State | Commit |
|---|---|---|
| T-0024 — browser evidence harness | **done** | `c9d351f` |
| T-0026 — requirement description from `to_string` | **done**, reviewed, fix-now applied | `b38b15a` |
| T-0025 — report presentation | **built, review still outstanding** | `aa03fb4` |
| T-0027 — requirement as structured citation | open, specified | — |
| T-0028 — a requirement that evaluated nothing must not report PASS | open, specified | — |
| T-0029 … T-0033 | named in `docs/plan.md` "Queued", task files **not yet written** | — |

Numbering continues at **T-0029**.

## The one unresolved thing, carried over unchanged

**T-0025's review has still never run.** It was dispatched in session 1 and lost when that
session ended; session 2 announced the re-dispatch and was redirected before it happened.
`docs/agents.md` forbids a *second* review of a task — this task has not had a first one.
`docs/tasks/T-0025-report-presentation.md` records exactly what the review was asked to hunt,
so the next dispatch must not re-derive it. Short version: **the filter is the dangerous
surface and the e2e spec drives exactly one of its states.**

T-0025 was committed rather than held back because it passes every gate and its evidence was
independently verified by the coordinator — but it is **not done**, and Phase 3 must not be
marked complete until that review runs.

## Order of work, and why

T-0027 and T-0028 were written before the scope was settled and both survive it. They lead the
queue ahead of all new surface, because they are defects in the report's honesty and the report
is now the entire product. T-0028 in particular is I7 inside the engine.

Then: T-0029 disclosure copy → T-0030 rule catalogue → T-0031 rule selection → T-0032 the
Markdown report file → T-0033 the measured ceiling.

## The structural consequence to honour when T-0030 is written

A rule pack we ship belongs to no tenant. Making `RuleSet.tenant` nullable to fit it would put
a nullable column at the centre of the one invariant this repository enforces structurally —
every tenant-owned row reads through `for_tenant`. The catalogue is therefore a **separate
model** from the tenant-owned `RuleSet`, so `for_tenant` stays total with no exception to
reason about. `RuleSet` today is at `services/api/cadgpt/apps/rulepack/models.py` and is
`TenantOwnedModel` + FK to `media.Media`.

## The correction recorded against the ceiling instruction

The instruction was "time is not the constraint, we use async jobs". Half of that holds.
Asynchronous execution removes the wall-clock constraint; it does **not** remove the memory
one. `ifcopenshell` loads the whole model into RAM, and `acks_late` redelivers the message that
killed its worker — so one oversized model is a poison message that takes the worker down
repeatedly and starves every other tenant's queue. T-0033 must **measure** peak resident memory
in the worker container across increasing model sizes, set the ceiling below the cliff, paste
the measurement as evidence, and make a resource-exceeded run fail with a named reason rather
than be redelivered forever.

## Do not take a builder's evidence on trust

The argument for the whole loop, from session 1, unchanged:

- T-0024's harness rendered its first report and the requirement line read
  `<ifctester.facet.Attribute object at 0x76f24ab599a0>` — in every report the product had ever
  produced. Became T-0026.
- T-0026's reviewer found the fix *introduced* a regression: a prohibited specification rendered
  "The requirement is not applicable" directly under a FAIL verdict.
- Two builders in a row wrote a test that passed with its own fix reverted, and one wrote an
  evidence claim that was impossible (`git stash` on an untracked file).

**Re-run the mutation yourself. Open the screenshot.**

## Environment notes that cost time to discover

- The `builder` and `reviewer` agent types in `.claude/agents/` are **not registered** as
  dispatchable types in this harness. Dispatch `general-purpose` and instruct it to read
  `.claude/agents/builder.md` or `reviewer.md` as its role contract. Builder on sonnet,
  reviewer on opus.
- The compose stack may still be **up** from session 1. `docker compose -f deploy/compose.yaml
  ps` to confirm; `make up` rebuilds, which is required for a frontend change to reach the
  served container.
- `ruff format` no longer scans `docs/**` (`pyproject.toml`). It was rewriting quoted defects
  inside task files into different code. A code quote in a task file is evidence.
- `make verify` at the last full run: ruff clean, `mypy --strict` over 138 source files,
  **5 import contracts kept**, **164 tests passed**.
