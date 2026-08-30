# Task specification format

The contract between the Lead and one subagent session. A subagent receives exactly this
and nothing else — no conversation history, no accumulated context, no reference to what a
previous agent did.

Written to `docs/roadmap/tasks/T-<id>.md` before the session starts.

---

## Template

```markdown
# T-<id> — <imperative title>

Slice:        L3-<id>
Capability:   L2-<id>
Outcome:      L1-<id>

## Prerequisites
| Requires | Evidence it is complete |
| --- | --- |
| T-<id> | <command that passes / artefact that exists> |

STOP if any evidence is absent. Do not stub it. Report the missing prerequisite and end.

## Objective
One paragraph. What exists after this task that did not before.

## Context — read these and nothing else
- CLAUDE.md
- docs/ddd/02-ubiquitous-language.md
- <exhaustive list>

## Contract
```python
def <name>(...) -> ...: ...
```
Inputs, outputs, and every error case, typed. Do not redesign this signature.

## Invariants this task must uphold
- I<n>: <how it applies here concretely>
- <aggregate invariant from docs/ddd/04>

## Files
Create:  <exhaustive>
Modify:  <exhaustive>
Forbidden: everything else. No new dependencies. No new configuration.

## Tests
Unit (n):        <behaviours>
Integration (n): <behaviours, entering at the real outer entry point>
Fixtures:        <which generator script; create it if named here>
Mocking:         none permitted / <the one external boundary, named>

## Acceptance
```
make verify
<the specific command proving the real path ran, with its expected output>
```

## Deliverables
- Code
- Tests, ~50/50, passing
- readme.ai.md created or updated
- decisions/DEC-XXXX.md for any decision taken
- A completion report: what ran, the wiring line, anything NOT DONE

## If you hit an unresolved decision
Do not decide. Write decisions/DEC-XXXX.md with `Status: OPEN`, stating the problem,
the constraints, and the options you can see. Stop. Report it.
```

---

## Rules for whoever writes the spec

**The context list is a budget, not a suggestion.** Every file in it is read in full and
costs context that the task then cannot spend on the work. If the list exceeds roughly six
files, the task is too big or the module boundary is wrong.

**Never write "and anything else you need".** That phrase converts a bounded session into an
unbounded one and is the specific failure this whole process exists to prevent.

**The contract is given, not requested.** An agent asked to design a signature will design a
reasonable one that does not match its neighbour. Signatures are the Lead's job because they
are the integration surface.

**Acceptance must be falsifiable by a machine.** If you cannot write the command, you do not
yet know what the task produces, and the spec is not finished.

**A Files list that forbids the file the work requires is a defect, and it has cost two
sessions.** T-0007 was told to build a gate that spawns `pytest` while `tools/tests/conftest.py`
— which owns the only recursion-safety mechanism — was withheld; it stopped and reported,
correctly. T-0008 was told to add rejection proofs that spawn `make verify` while the same file
was withheld, and the omission was not caught until a full run took eleven minutes and failed.

Two concrete checks before dispatching, both cheap:

- **Does the task add a test that spawns `make verify` or `pytest`?** Then it must list
  `tools/tests/conftest.py`, because every such test has to be registered in
  `SPAWNS_A_RE_ENTERING_PROCESS`. An unregistered spawning test is run by the very gate it
  proves.
- **Does the task's own acceptance require a file the Files list omits?** Read the Contract and
  the Acceptance command back against the Files list, line by line. Both failures above were
  visible that way and neither was noticed.

The general form: the Files list is written from what the change *looks like*, and the omission
is always a file the change *depends on* rather than one it edits for its own sake.

**Name the invariants concretely.** "Uphold I4" is not actionable. "This module names
properties; every name must carry its measurement convention, and the jurisdiction guard will
reject a name containing a code reference" is.

## Rules for the subagent

- Read only the listed files. Needing a seventh means the spec is wrong — report that, do not compensate.
- Touch only the listed files. A necessary change elsewhere is a report, not an edit.
- Do not add a dependency. Ever. That is a decision record.
- Do not stub a prerequisite. Stop instead.
- Do not decide. Escalate as a file.
- Report honestly. Partial is reported as partial, with exactly what remains.
