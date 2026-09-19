# Building this with agents

The build runs as a coordinator loop with two kinds of subagent under it. This file is the
contract between them. It exists because subagents start cold: nothing carries from one to
the next except what is written to disk, so the pattern is only as good as what it persists.

## The shape

**Coordinator — Opus, the session you are sitting in.** Owns `docs/plan.md` and the task
queue. Chooses what happens next among *already-approved* tasks, dispatches, judges the
builder's evidence, records it, commits. It writes no production code, ever. The moment the
coordinator starts editing `services/api` itself, its context fills with implementation
detail and it stops being able to see the route.

The coordinator does **not** create a task off its own observation. When it notices a
problem outside a dispatched review — a defect stumbled on while reading a diff, a
discrepancy between the plan and the repository, a concern raised in conversation — it
writes the observation down and reports it. It does not decide the observation is real or
worth a queue slot; see "The judge" below.

**Builder — Sonnet.** Takes exactly one task file, implements it, runs the gates, executes
the real path, and writes the evidence back into the task file. Returns two or three lines.

**Reviewer — Opus.** Gated, not per-task. Findings only; it never edits. It has no write
tools, so that constraint is structural rather than remembered.

**Judge — Opus 5.** Sits above the loop, not inside it. Reads the accumulated observations —
from the coordinator noticing something, from a reviewer's queued (not fix-now) findings,
from the user flagging a concern — and decides two things per observation: is it actually
valid (reproduced or clearly reasoned, not assumed), and how important is it relative to
everything else waiting. Only an observation the judge has approved gets written up as
`docs/tasks/T-NNNN-*.md` and placed in the queue. This is a deliberate separation: the
coordinator that found the problem is not the one weighing whether it deserves to jump the
queue ahead of what a product owner already prioritized.

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
2. **An observation for the judge** — everything else. The coordinator does not write this up
   as a task file itself; it records what the finding is, where, and why it might matter, and
   reports it. The judge weighs it against every other pending observation and decides whether
   and when it becomes `docs/tasks/T-NNNN-*.md`.

There is no third pile. One review round per task, maximum. A review of a fix is never
dispatched; if the fix is wrong, that surfaces as its own observation the next time something
touches that code. Throughput is the point — a build that stops to re-review its own
remediation never reaches the next phase.

## The loop

1. Read `docs/plan.md`. Pick the next task from the current phase — one the judge has already
   approved into the queue.
2. Write `docs/tasks/T-NNNN-<slug>.md` for the judge-approved task. If the task cannot be
   specified without a decision the plan does not contain, that decision is the task — ask,
   then write it to `docs/decisions.md` or `prd.md` §12 before continuing. Size it against the
   context budget below before writing — split rather than write one task a builder is expected
   to overrun on.
3. Dispatch the builder with the task file path. One builder at a time unless two tasks touch
   disjoint files.
4. On return, read the evidence block. Missing or unconvincing sends it straight back — that is
   not a review, it is the task not being finished.
5. Apply the review gate above. Dispatch the reviewer only if it fires.
6. Triage findings into the two piles. Update the task file with the verdict.
7. Update `docs/plan.md`: status, and anything learned that changes the route.
8. Commit to `main` — the task file, the code and the plan update in one commit, referencing
   T-NNNN. Then loop.

## Context budget: split before dispatch, hand off if one runs long anyway

A subagent's context window is not a soft limit. A builder or reviewer that fills it mid-task
doesn't degrade gracefully — it starts losing earlier tool output, and evidence written after
that point can't be trusted. This is enforced at two points:

**At task-writing time (loop step 2).** Before writing the task file, the coordinator sizes it:
how many files it touches, how much of each has to be read versus written, whether it's a
"heavy per-record text pass" (below — those never go to a builder inline regardless of size). A
task the coordinator expects to run a builder past roughly 180k-220k tokens before it reaches
the evidence block is not one task, it's several — split it into sequential task files with an
explicit dependency line ("T-NNNN+1 starts once T-NNNN's migration lands") rather than writing
one file and hoping the builder manages its own budget.

**Mid-task, if a builder is running long anyway.** The builder is the one who notices — the
coordinator never sees a builder's context fill from outside. Approaching the same 180k-220k
budget without having reached the evidence block, the builder stops rather than pushing on or
quietly narrowing what it tests to fit. It writes a handoff into the task file — what's done,
what's verified, what's left, and the exact next command — the same shape the coordinator
already uses on itself in `docs/CHECKPOINT.md` and `docs/inbr-*-handoff.md`. The coordinator
reads the handoff and dispatches a fresh builder session against the same task file: a new
context continuing the work, not a restart from the task description alone. Compacting the
builder's own session in place instead of a full handoff is fine only when the builder can say
what remains is small and none of it is the kind of state compaction loses — an exact command's
output, a quoted registration line; that is a judgment the builder states explicitly, not a
default.

## Heavy per-record text passes are Haiku work, not builder work

A task can require reading many similar records and producing one authored judgement per
record — a rule-extraction decision, a semantic mapping, a classification — where the record
count runs into the hundreds. This is not implementation work and it does not go to a Sonnet
builder to do inline, for two reasons proven the hard way on the INBR corpus: a single agent
grinding through hundreds of near-identical records degrades into templating (three sources
each stamped one hardcoded sentence onto 600-1,600 records rather than reading them), and it
is the most expensive possible way to spend a Sonnet or Opus context window on work that does
not require their judgement per record — only the validation does.

The pattern, proven in `docs/inbr-haiku-remediation-runbook.md`:

- **Workers are Haiku, one record or one small fixed batch per worker, 3-5 in flight at a
  time.** A worker gets exactly the record(s), the source text, the schema, and the job — never
  the whole corpus, so it cannot drift into skimming.
- **The coordinator (Sonnet or Opus, whichever is already running the task) is the validator,
  and never trusts a worker's self-reported "done."** It independently re-checks every result
  against the actual source text before accepting it: does the record's own text support the
  judgement, not just does the output parse.
- **Anti-templating is a mechanical check, run by the coordinator, every batch.** If a single
  reason string, mapping shape, or phrase repeats across more than 2-3 records in one batch,
  the batch is rejected and redone — that repetition is the exact signature templating leaves.
- **A nonzero "declined" or "no assertion" count is expected.** A worker that accepts 100% of
  its records did not do the job; batches without any refusals get the same scrutiny as a
  repeated string.
- The task file states this explicitly wherever it applies — see `docs/tasks/T-0108-the-ifc-mapping-table.md`
  for the current example — rather than leaving model choice to whoever picks up the task.

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
complete — a blocked part is finished around and named as blocked. Write a task file for a
problem it noticed itself, without the judge's sign-off — it observes and reports, it does not
self-approve its own findings into the queue.
