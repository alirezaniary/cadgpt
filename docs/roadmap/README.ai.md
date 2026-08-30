# readme.ai.md — docs/roadmap

## Purpose
The decomposition, from the goal down to whatever level is currently settled. This is a
living plan; `docs/ddd/` and `docs/architecture/` are not.

## Contents
| File | Level | State |
| --- | --- | --- |
| `L0-goal.md` | L0 | Settled. Does not change. |
| `L1-outcomes.md` | L1 | Fully enumerated. Awaiting stakeholder confirmation. |
| `dependency-order.md` | — | The graph, which is the schedule. Includes the fieldwork gates. |
| `L2-O1-capabilities.md` | L2 | Fully enumerated for O1 only. |
| `mvp.md` | — | What v0 is, what it is not, how it gets judged, and the named risks. |

`tasks/` appears when the first L3 slice is decomposed. It does not exist yet, on purpose.

## Contract
Expansion follows `docs/process/decomposition.md`:
- **Breadth before depth.** A level is fully enumerated before any node of it is expanded.
- **Prerequisite order is absolute.** Only a node with no unbuilt prerequisite may be started.

Currently startable: **P0, the harness.** Everything else is blocked by the rule, not by
priority.

## Invariants upheld here
- No node is marked complete without runtime evidence beside it (`docs/process/definition-of-done.md`).
- A missing dependency edge discovered mid-task stops the task and becomes a decision record.

## How to run it
Not runnable. Read `dependency-order.md` first — it is the only file that answers "what
happens next".

## Open questions
- **O1 cannot be judged without five real IFC models from five different offices** (Gate 3).
  This is the only external dependency O1 has, and it is not code.
- Gate 4 (parcel data obtainable?) blocks the setback and site-coverage checks in O3. Currently
  assumed, not known. Does not block O3's resolver, which is built against synthetic packs.
- Real regulatory content is loaded last, by decision (DEC-0015). Every outcome up to O5 is
  built and proven against sample and synthetic packs.
