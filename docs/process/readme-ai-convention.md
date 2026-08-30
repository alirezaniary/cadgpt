# readme.ai.md convention

Every module directory carries one. It is the module's **contract**, written for the next
agent — who will read it *instead of* the code, because reading the code costs context the
task needs for the work.

This is the mechanism that lets sessions stay short. A task touching module A while
depending on module B reads B's `readme.ai.md`, not B's source. If that is not enough to
work against B, B's contract is inadequate and that is a defect in B.

Presence and conformance are checked by `make verify` gate 7.

## Fixed sections

Fixed so a machine can check them and an agent can rely on their being there. All nine,
in this order, always.

```markdown
# readme.ai.md — <module path>

## Purpose
One paragraph. What this module is responsible for, and — as important — what it is not.

## Context
Which bounded context (docs/ddd/03-bounded-contexts.md) and which subdomain
(core / supporting / generic).

## Contract
The public surface. Every exported name, typed, with what it does and what it raises.
This section is what other modules are permitted to depend on. Anything not listed here
is internal and may change without notice.

## Invariants enforced here
Which invariants from docs/ddd/04-aggregates-and-invariants.md this module owns, and
where in the code each is enforced. An invariant listed here is enforced HERE and is not
re-checked by callers.

## Depends on
Modules and libraries, with why each. An entry here must be permitted by the import
contracts (docs/ddd/05) and by this distribution's dependency set.

## Must not depend on
The forbidden edges that apply specifically to this module, and the reason each exists.

## Tests
Where they are, what behaviours they prove, the unit/integration split, and any mocking
with its justification.

## How to run it
The real path. An exact command with real input and its expected output — not a
description. This is what a Task session executes to satisfy CLAUDE.md §9.2.

## Open questions
Known gaps, deferred decisions, and things the next agent should not assume are settled.
Empty is a valid answer and must be written as "None."
```

## Rules

**Written in the same task as the code, by the same agent.** A documentation pass afterwards
documents what the code appears to do, which is exactly the information the reader already
has. The contract must be written by whoever knew the intent.

**The Contract section is normative.** Code disagreeing with it is a bug in the code. A
module's public surface is what this section lists — `__all__` should match it, and anything
absent is internal regardless of whether Python can reach it.

**Say what it is not.** The most useful line in most of these files is the one ruling
something out, because it stops the next agent adding a responsibility that belongs elsewhere.

**"How to run it" is a command that works.** Not `python -m module --help`. A real invocation
over real input showing real output. This section is load-bearing for the definition of done.

**Open questions is honest or it is worthless.** "None." when there are none. Never a
reassurance.

## Why this and not docstrings

Docstrings describe functions. This describes a *boundary* — the invariants it owns, the
edges it must not cross, and what it refuses to be responsible for. That information has no
function to attach to, and it is the information a bounded session actually needs.

Docstrings are still written where a signature is not self-evident. They are not a substitute
for this file, and this file is not a substitute for them.
