# Definition of done

Extends the global rule in `~/.claude/CLAUDE.md`. Both apply; where they overlap, the
stricter reading governs.

## The premise

**A task is not done because the diff looks complete or the tests pass.**

This is not general caution. It is the specific failure mode of this domain, appearing in our
own repository. `prd.md` §2: a wrong seismic factor, a stair 15 cm too narrow — none of these
produce an error; the model opens fine and the drawing looks correct. Our test suite has the
same property. It can be green over a system that has never run.

So "done" is defined by **evidence produced**, not by state believed.

## The six conditions

Every one, every task. A completion report states each explicitly.

### 1. `make verify` passes clean
All sixteen gates. Not "passes except for X". A skipped gate is a failed gate.

### 2. The real path executed once
Start the actual entry point — CLI, API route, worker task, recipe — over real input, and
show the output in the completion report.

A unit test is not this. An integration test is not this either, because a test harness can
supply what production does not. The claim being evidenced is *"this works when actually
invoked"*, and only actually invoking it evidences that.

### 3. Wiring shown
A handler, recipe, route, rule, task or migration counts only when it is **registered where
it runs**. Quote the registration line in the report:

| Thing | Registration to quote |
| --- | --- |
| An `ifcpatch` derivation recipe | its entry in the recipe registry |
| A rule | its compiled `.ids` present, and the pack manifest listing it |
| An API route | the router include line |
| A Celery task | the task registration / beat entry |
| A migration | `alembic heads` showing it |
| A build guard | its line in the Makefile's verify target |

An unregistered component is the exact defect `/adversarial-review` hunts: code that has
never run, in a repository where everything looks finished.

### 4. No placeholders
No `TODO`, no `FIXME`, no `pass  # stub`, no `"placeholder"` return value, no silently
defaulted parameter standing in for a real one. Gate 6 scans for these.

An unavoidable stub **raises `NotImplementedError`** and is listed as **NOT DONE** in the
report, by name. A silent placeholder is worse than a missing feature, because a missing
feature is visible.

### 5. `readme.ai.md` written or updated
All nine sections, conforming, in the same task. Its "How to run it" is the command from
condition 2.

### 6. Decisions recorded
Any decision the task took is in `decisions/` before the task is reported done. A decision
reached and not written did not happen, and will be re-litigated differently by an agent that
cannot see this session.

## The completion report

Every task ends with one. Fixed shape, because it is read by the Lead and by Review, not by a
person browsing.

```markdown
## T-<id> completion

Verify:        make verify — PASS
Real path:     <exact command>
               <actual output, quoted>
Wiring:        <file:line> — <the registration line, quoted>
Tests:         <n> unit, <n> integration — all pass
               Mocking: none / <boundary, justified>
Docs:          <path>/readme.ai.md updated
Decisions:     DEC-XXXX / none

NOT DONE:      <name it, or "nothing">
Notes:         <anything the Lead needs to know before integrating>
```

## Honesty rules

**"Partially fixed" must list exactly what remains.** Not "some edge cases", not "mostly
working". Name them.

**A failing test is reported with its output.** Not worked around, not marked skip, not
narrowed until it passes. If a test fails and the cause is in a prerequisite, that is a
prerequisite report, not a test change.

**Never mark a roadmap or plan item complete without the runtime evidence beside it.** The
roadmap records evidence, not confidence.

**Say what you did not do.** A task that delivered four of five things and reports five is
worse than one that delivered three and reports three, because the fifth will be discovered
by whatever depends on it — later, and by then several things will.
