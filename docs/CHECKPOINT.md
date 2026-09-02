# Checkpoint — 2026-09-03, end of coordinator session 3

Session 2 settled scope and moved no code. **Session 3 ran the loop and closed four tasks with
their reviews** (T-0025, T-0028, T-0027, T-0029) and built a fifth (T-0030) whose review was
lost. Ended for context, not because anything is broken: `main` is green and every task file
carries its evidence. `docs/plan.md` is the route and `docs/tasks/` holds
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
| T-0028 — a requirement that evaluated nothing must not report PASS | done, reviewed | `6e64ce2` |
| T-0025 — report presentation | done, reviewed, fix-now applied | `ec9b761` |
| T-0027 — requirement as structured citation | done, reviewed, fix-now applied | `f66a136` |
| T-0029 — say what was checked | done, reviewed, fix-now applied | `3a87ef5` |
| T-0030 — the rule catalogue | **built, review lost with the session** | `9faf208` |
| T-0031 — rule selection on the run | open, **task file written** | — |
| T-0032 — the Markdown report file | open, **task file written** | — |
| T-0033 — the measured upload ceiling | open, task file not yet written | — |
| T-0034 … T-0041 | queued from reviews, behind the MVP tasks | — |

Numbering continues at **T-0042**.

`make verify` at last run: ruff clean, `mypy --strict` over 147 files, **5 import contracts
kept**, **199 tests passed**, frontend build green. `make e2e` green.

## The one unresolved thing

**T-0030's review was dispatched and lost when this session ended** — exactly what happened to
T-0025 twice. `docs/agents.md` forbids a *second* review; this task has not had a first one.
`docs/tasks/T-0030-the-rule-catalogue.md` records what the review was asked to hunt and what the
coordinator already verified independently, so the re-dispatch must not re-derive either. Short
version: **the seeder's idempotence is proven for a sequential re-run and not for a race or a
changed file on disk, `source_citation` is `prd.md` §5.7 attribution that may be a placeholder,
and the builder's `docs/decisions.md` entry was never read by the coordinator.**

T-0030 was committed rather than held back on the T-0025 precedent: it passes every gate and its
evidence was independently re-verified. It is **not done**, and Phase 3 must not be marked
complete until that review runs.

## What the reviews changed, so nobody re-derives it

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

## What every review this session actually found

The pattern is worth carrying forward, because it is not the one the hunt lists predicted. **The
builders' mechanisms were sound every time; the defects were all in claims about coverage and
honesty** — and none was caught by the suite.

- A coverage headline that was arithmetically incapable of saying anything but `N of N`.
- A `PASS` returned over zero evaluations.
- A citation that resolved to the **wrong rule**: `enumeration` joined with "and", so a choice of
  two values read as a demand for both.
- An unrecognised operator degrading to a confident sentence rather than a visibly unresolved one.
- A disclosure promising a single source that its consumer could never read.

Twice the review's own hunt list was pointed at the wrong surface — T-0025's filter came back
clean under all four undriven states while coverage, the thing the task existed to add, was wrong
twice. **Point reviews at what the task claims to establish, not at what looks most complex.**

## Do not take a builder's evidence on trust

Of the last ten evidence blocks: two contained tests that passed with their own fix reverted, and
**four contained a claim that was false** — a Python test asserted to exercise a TypeScript
function, a `StatusPill` rendering path that has never existed, a reassurance attached to exactly
the case that was broken, and a `NOT DONE: nothing` over a promise that could not be kept.

**Re-run the mutation yourself. Open the screenshot.** Every one this session reproduced exactly:
`3 of 3` where the fix renders `2 of 3`; `Status.PASS` over `0/0/0`; `and` where the fix renders
`or`; `KeyError: 'totalDigits'`; `Expected "disclosure" / Received "coverage"`; a gutted
disclosure caught by its new wording assertion; and four tests failing when `RulePack` was made
tenant-owned.

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
- A long-running builder killed by a session usage limit leaves its working tree **intact**.
  Resume the same agent by name rather than re-dispatching, so its context is not lost. This
  happened twice this session and both resumes worked cleanly.
