# Building this with agents

The build runs as a coordinator loop with two kinds of subagent under it. This file is the
contract between them. It exists because subagents start cold: nothing carries from one to
the next except what is written to disk, so the pattern is only as good as what it persists.

## The shape

**Coordinator — Opus, the session you are sitting in.** Owns `docs/plan.md` and the task
queue. Chooses what happens next, writes the task file, dispatches, judges the result,
records it, commits. It writes no production code, ever. The moment the coordinator starts
editing `services/api` itself, its context fills with implementation detail and it stops
being able to see the route.

**Builder — Sonnet.** Takes exactly one task file, implements it, runs the gates, executes
the real path, and writes the evidence back into the task file. Returns two or three lines.

**Reviewer — Opus.** Gated, not per-task. Findings only; it never edits. It has no write
tools, so that constraint is structural rather than remembered.

## Why the models split this way

Planning and review are judgement under ambiguity — what the task actually is, whether an
invariant just quietly moved, whether the evidence proves what it claims. Implementing a task
that has already been specified is mostly typing. Opus where the decision is, Sonnet where
the typing is.

But the model tier is the smaller lever. The larger one is that the coordinator reads
`docs/plan.md` and one task file per iteration and never the repository, and a subagent's tool
output never enters the coordinator's context at all. A coordinator that re-derives the repo
on every loop costs more than the tier saves. If context is filling up with file contents, the
loop is wrong, not the model.

## The task file is the context

`docs/tasks/T-NNNN-<slug>.md`, continuing the numbering already in this repository's history —
the last is T-0023, so the next is T-0024. It is written *before* the builder is dispatched and
it carries everything the builder needs, because the builder cannot ask a follow-up question of
a conversation it was never in.

```markdown
# T-NNNN — <one line: the change, not the activity>

**Phase:** <from docs/plan.md>   **Status:** open | built | reviewed | done
**Touches invariants:** none | I1 | I2 | three-valued | tenancy | import contracts

## Why
One paragraph. What is broken or missing, and what becomes possible once this lands.

## Scope
What changes, file by file where it is known. What explicitly does not change.

## How to prove it ran
The exact command that exercises the real path, and what its output must show. Not
"tests pass" — the request, the message, the job, and the value that comes back.

## Evidence            <- the builder writes this, nobody else
`make verify`: <result>
Real path: <command, then its actual output pasted>
Wiring: <the registration line — route, task, migration head, DI — quoted from the file>

## Review              <- only if review was gated on, verdict then findings
```

## Done is runtime evidence, not a reviewer's approval

A reviewer reads a diff. A diff cannot show that the Celery task is registered on the beat
schedule, that the migration is at head, that the router carries the route. This repository
has a documented history of green suites over a broken system, and the last three defects here
were all found by running the stack. So the builder's exit condition is the evidence block, and
the coordinator rejects the task on a missing or unconvincing one *before* any reviewer is
involved. `make verify` is necessary and never sufficient.

An unavoidable stub raises `NotImplementedError` and is listed as **NOT DONE** in the task
file. There is no silent placeholder and no ✅ without the evidence beside it.

## Review is gated, and it never recurses

Reviewing every task is how a build becomes an audit. The reviewer runs when one of these is
true, and otherwise does not run:

- the task touched an invariant — I1, I2, three-valued results, tenancy, or an import contract;
- it is a milestone boundary, meaning a phase in `docs/plan.md` is about to be marked done;
- the evidence block is incomplete, or the coordinator cannot tell whether it proves the claim;
- the change is large enough that the coordinator did not read all of it.

Findings come back in exactly two piles, and the coordinator does the sorting:

1. **Fix now** — an invariant is violated, or the evidence block is false. Same task, same
   builder, no new review afterwards.
2. **A task in the queue** — everything else, written as a real task file with its own number.

There is no third pile. One review round per task, maximum. A review of a fix is never
dispatched; if the fix is wrong, that surfaces as its own task the next time something touches
that code. Throughput is the point — a build that stops to re-review its own remediation never
reaches the next phase.

## The loop

1. Read `docs/plan.md`. Pick the next task from the current phase.
2. Write `docs/tasks/T-NNNN-<slug>.md`. If the task cannot be specified without a decision the
   plan does not contain, that decision is the task — ask, then write it to `docs/decisions.md`
   or `prd.md` §12 before continuing.
3. Dispatch the builder with the task file path. One builder at a time unless two tasks touch
   disjoint files.
4. On return, read the evidence block. Missing or unconvincing sends it straight back — that is
   not a review, it is the task not being finished.
5. Apply the review gate above. Dispatch the reviewer only if it fires.
6. Triage findings into the two piles. Update the task file with the verdict.
7. Update `docs/plan.md`: status, and anything learned that changes the route.
8. Commit to `main` — the task file, the code and the plan update in one commit, referencing
   T-NNNN. Then loop.

## What is persisted, and where

```
docs/plan.md              the route and each phase's status
docs/tasks/T-NNNN-*.md    one per task: spec, evidence, review verdict
docs/reviews/M-NN-*.md    milestone reviews, kept whole rather than summarised
docs/decisions.md         engineering decisions, with the reasoning
prd.md §12                product decisions
```

A decision settled in conversation is written to a file in the same turn it is settled. The
history the coordinator needs on its next loop is the one on disk; anything that lives only in
a transcript is already lost.

## What the coordinator never does

Write production code. Mark anything done without an evidence block. Dispatch a reviewer on a
fix. Re-read the repository to re-derive context a task file should have carried. Run two
builders over overlapping files. Narrow a task's scope to make it finishable and report it as
complete — a blocked part is finished around and named as blocked.
