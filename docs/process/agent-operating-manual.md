# Agent operating manual

How work is actually executed here. The premise: **context length is a defect, not a
resource.** A long session accumulates unverifiable assumptions, silently drops earlier
constraints, and produces code whose justification nobody — including the agent — can
reconstruct. Many short sessions with written contracts between them do not.

## The session types

| Session | Holds | Produces | Ends when |
| --- | --- | --- | --- |
| **Lead** (this one) | The plan, the decisions, the boundaries | Decisions, decompositions, task specs, integration review | A level is settled or an outcome is reached |
| **Task** | One task spec | Code, tests, `readme.ai.md`, a completion report | Acceptance passes or a prerequisite is missing |
| **Review** | One completed task's diff + its spec | A verdict against the spec | Verdict given |

A Task session never sees another Task session's conversation. The interface between them is
files: a spec in, code plus a `readme.ai.md` out.

## The loop

```
  Lead decomposes one level
        │
        ▼
  Stakeholder chooses  ── only at L1 ──┐
        │                              │
        ▼                              │
  Lead writes task specs in            │
  prerequisite order                   │
        │                              │
        ▼                              │
  ┌──▶ Task session (bounded)          │
  │     │                              │
  │     ▼                              │
  │   make verify + real path          │
  │     │                              │
  │     ├── fails ──▶ Lead re-specs ───┘   (never: agent improvises)
  │     │
  │     ▼
  │   Review session against the spec
  │     │
  │     ▼
  │   Lead integrates, updates the log
  └─────┘
```

## Why a separate Review session

The agent that wrote the code is the worst judge of whether it meets the spec, for the same
reason a rule's author is the worst author of its fixtures (`prd.md` §8: *"A rule and its
proof of correctness may not come from the same generator."*). That constraint applies to
our own code as directly as to the corpus.

The Review session reads the spec and the diff. It does not read the Task session's
reasoning, because the reasoning is exactly what would persuade it.

Review answers three questions, in order:
1. Does the code do what the spec's acceptance command claims it does — was the real path run?
2. Does it uphold every invariant the spec named?
3. Is there anything here that was not asked for? Scaffolding, an unused abstraction, a
   configuration nothing reads, a dependency, a "helpful" extra.

Question 3 catches the most common failure of generated code, and it is the one a
harness cannot see.

## What is minimized, and what is not

**Minimized: the model's influence on what runs.** Every guarantee the product makes is
produced by deterministic code. A model drafts clause records that a human ratifies and a
deterministic compiler compiles. A model explains findings it did not produce. A model
writes implementation code that a harness of sixteen mechanical gates admits or rejects.

**Not minimized: the model's share of the typing.** Volume of generated code is fine. What is
not fine is generated *judgement* — a decision no human recorded, an interface nobody
specified, an invariant nobody named.

The distinction is the whole method. Generate freely inside a written contract; never let
generation produce the contract.

## Escalation

A Task session that meets something unresolved does not resolve it.

```
decisions/DEC-XXXX.md   Status: OPEN
  Problem      what was hit
  Constraints  what the code, the PRD and CLAUDE.md permit
  Options      what could be done, with consequences
  (no Decision line)
```

Then it stops and reports. The Lead resolves it, or — if two answers give two materially
different products — asks the stakeholder.

A guess costs more than a stop. A stopped task is one file to read; a guess is a wrong
assumption propagating into every task that follows it, discovered later and more expensively.

## Anti-patterns

| Anti-pattern | Why it is fatal here |
| --- | --- |
| One long session building several modules | Constraints from the first module silently stop being applied by the third. Nobody can tell which. |
| "Let me also fix / improve / clean up X" | Unreviewed, unspecified, unlogged change. The diff stops matching the spec, and Review can no longer function. |
| Stubbing a prerequisite to unblock | Produces code written against an assumption that will be wrong, and the wrongness surfaces after several dependents exist. Violates prerequisite order. |
| Mocking our own code to make a test pass | Proves the mock. This workspace has already shipped a green suite over a broken system this way. |
| Adding an abstraction "for later" | Scaffolding. There is no second implementation, so the abstraction encodes a guess about a future nobody has specified. |
| Deciding quietly and moving on | The decision will be re-litigated, differently, by an agent that cannot see this session. |
