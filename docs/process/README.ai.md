# readme.ai.md — docs/process

## Purpose
How work is decided, bounded, executed and proved. This is the operating system of the
repository; `docs/ddd/` is what it operates on.

## Contents
| File | Answers |
| --- | --- |
| `decomposition.md` | The five levels, breadth-before-depth, absolute prerequisite order, when the stakeholder is asked |
| `agent-operating-manual.md` | Session types, the loop, why Review is separate, escalation, anti-patterns |
| `task-spec.md` | The Lead↔subagent contract, with the template |
| `readme-ai-convention.md` | The nine fixed sections every module contract carries |
| `testing-strategy.md` | 50/50, near-zero mocking, cross-layer behaviour, fixtures as code, the five things every slice proves |
| `definition-of-done.md` | The six conditions and the completion report |

## Contract
Normative for every session. A Task session receives `CLAUDE.md`, its task spec, and
whichever of these its spec lists — never all of them.

## Invariants upheld here
- No session builds against an unbuilt prerequisite.
- No agent decides; agents escalate as files.
- The author of an implementation is not the judge of it.

## Open questions
- Review is specified as a separate session but not yet automated. Whether it becomes a
  standing subagent or a harness extension is a decision for when the first slice lands.
