# readme.ai.md — docs/architecture

## Purpose
How the domain analysis becomes software: what we build on, where code lives, and how a
change is proved admissible.

## Contents
| File | Answers |
| --- | --- |
| `stack.md` | Every technology choice, which are forced by the PRD, which were decided here and why, and what was rejected |
| `module-map.md` | What the ten contexts become on disk; distributions and their dependency sets; where a new thing goes |
| `harness.md` | The sixteen gates behind `make verify`, and why each exists |
| `test-assets.md` | Inherited sample models and sample IDS rules; what they clear and what they cannot |

## Contract
`stack.md` is closed to task-level choices. A task does not add a dependency, swap a
library, or introduce a service — that is a decision record.

`module-map.md` describes intent. **No directory in it exists until a task needs it.**

## Invariants upheld here
- Engine distributions resolve no inference SDK (harness gate 4).
- Nothing is written that `prd.md` §6 already inherits.

## Open questions
- `ifc-gherkin-rules` as a host for computed rules is under evaluation upstream (`prd.md` §5.5). If it holds up, some rules currently needing a custom derivation stay declarative, and `engine/derivation` shrinks. Not a blocker; revisit when the derivation set is real.
