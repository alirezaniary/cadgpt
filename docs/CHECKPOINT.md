# Checkpoint — 2026-09-02, coordinator session 3

Session 2 settled scope and moved no code. **Session 3 is running the loop.** Two tasks closed
with their reviews, three commits on `main`. `docs/plan.md` is the route and `docs/tasks/` holds
the detail; this file only records where the loop is and what is unresolved.

## The MVP, settled in session 2 — do not re-litigate

> The user uploads a model, picks which rules to run it against, and gets back a report file.

Rules are a catalogue we ship, not a file the architect uploads (the catalogue is a **separate
model** from the tenant-owned `RuleSet`, so `for_tenant` stays total). The first iteration
**reports and does not act** — overlay, marked sheets and BCF are out by decision, which takes
gate 2 off the critical path. The deliverable is a generated **Markdown** report whose URL sits
on the job record. The upload ceiling is **measured against peak worker memory**, not chosen.
Full reasoning in `docs/decisions.md` and `prd.md` §12.

## Where the loop is

| Task | State | Commit |
|---|---|---|
| T-0024 — browser evidence harness | done | `c9d351f` |
| T-0026 — requirement description from `to_string` | done, reviewed | `b38b15a` |
| T-0028 — a requirement that evaluated nothing must not report PASS | **done, reviewed** | `6e64ce2` |
| T-0025 — report presentation | **done, reviewed, fix-now applied** | `ec9b761` |
| T-0027 — requirement as structured citation | **builder dispatched** | — |
| T-0029 … T-0033 | MVP queue, in `docs/plan.md` order | — |
| T-0034 … T-0038 | queued from the two reviews, behind the MVP tasks | — |

Numbering continues at **T-0039**.

## What the two reviews changed, so nobody re-derives it

**T-0025's review finally ran** — it had been lost with session 1 and pre-empted in session 2.
Worth recovering, and instructive about where to point a reviewer: the **filter**, which the
hunt list was written to distrust, came back clean under all four of its undriven states. Both
defects were in **coverage**, the thing the task existed to add. The headline sentence was a
constant — `specifications_passed + specifications_failed + specifications_indeterminate` is
identically `specifications.length` for every report the engine can produce — so it read "N of
N" always, claiming full coverage above a block naming the specifications that checked nothing.
And `establishedNothing()`'s `matched === 0` disjunct swallowed `NO_SUBJECTS_BUT_REQUIRED`,
labelling an established FAIL as unevaluated. Both now derive from **one predicate**, so they
cannot disagree on screen, and the predicate reads the reason code `judge()` already assigned
rather than holding a second copy of the engine's judgement in TypeScript.

**T-0028's review proved the dangerous direction by exhaustion, not sampling** — a requirement
can reach all-zero counts only via a prohibited specification or an empty applicable set, both
of which genuinely evaluated nothing, so no real PASS can become an unknown. It then found the
evidence block's claim that the flipped status "renders through the existing `StatusPill`"
to be false: `requirement.status` is read by **no component**. T-0028 is real in the API and
invisible in the browser until **T-0037**.

## Two decisions settled this session, in `docs/decisions.md`

- **A requirement that evaluated nothing is explained, never suppressed.** The tidy-up — hiding
  the row when the specification reached its verdict without evaluating requirements — is
  refused. Hiding a row that says "nothing was checked here" is the failure I7 exists to close.
- **A verdict-changing engine release bumps the engine version.** Schema version answers "can
  this be parsed"; engine version answers "would this be judged the same way today". Old runs
  are never re-run to match — a run is a record of what was said at the time.

## Do not take a builder's evidence on trust

Still the argument for the whole loop, and it kept earning its keep this session. Of the last
five evidence blocks: two contained tests that passed with their own fix reverted, and **three
contained a claim that was false** — most recently a Python test asserted to exercise a
TypeScript function, and a `StatusPill` rendering path that has never existed.

**Re-run the mutation yourself. Open the screenshot.** Both were done for T-0025 and T-0028 and
both reproduced exactly — `3 of 3` where the fix renders `2 of 3`, and `Status.PASS` over
`0/0/0` with the engine fix reverted.

## Environment notes that cost time to discover

- The `builder` and `reviewer` agent types in `.claude/agents/` are **not registered** as
  dispatchable types in this harness. Dispatch `general-purpose` and instruct it to read
  `.claude/agents/builder.md` or `reviewer.md` as its role contract. Builder on sonnet,
  reviewer on opus.
- **The engine CLI is `uv run cadgpt-check <model.ifc> <rules.ids> --json`.** T-0026, T-0027 and
  T-0028 all shipped a task file instructing the builder to run `cadgpt-engine check`, which
  does not exist. Fixed in all three; do not reintroduce it.
- A frontend change reaches the served page only after
  `docker compose -f deploy/compose.yaml up -d --build web`. That invocation also rebuilds and
  recreates `cadgpt-api-1`, so it picks up `services/api` and `packages/engine` too.
- `ruff format` no longer scans `docs/**`. It was rewriting quoted defects inside task files
  into different code, and a code quote in a task file is evidence.
- A long-running builder can be killed mid-task by a session usage limit. Its working tree
  survives intact; resume the same agent rather than re-dispatching, so its context is not lost.
- `make verify` at last full run: ruff clean, `mypy --strict` over 138 files, **5 import
  contracts kept**, **166 tests passed**, frontend build green.
