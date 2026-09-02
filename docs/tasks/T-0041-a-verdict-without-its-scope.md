# T-0041 — A verdict is reachable without the statement of what was checked

**Phase:** 3 — What the first real user needs   **Status:** open
**Touches invariants:** I7. **Reviewer-gated.**

## Why

Found by the T-0029 review, one level up from where that task was looking.

T-0029 put the I7 disclosure at the top of the report: this checked the model, not the drawing
set your office submits. But the report is not the only place a verdict appears. The reviews
list renders the outcome before anyone opens anything:

```
three-doors-1788369893695
three_doors.ifc
                                    Complete   [Fail]   [Run check]   [Summary]
1 / 1 / 1
```

A status pill and three counts, with no statement of what was checked. On a clean run that row
is a compliance-shaped signal — a green pill and a row of numbers — and it is the surface a
reader most plausibly screenshots into an email or pastes into a message to a colleague. The
disclosure two clicks away does not travel with it.

`prd.md` §5.7 is not scoped to the report view: *every report names the model it checked*, and
I7 forbids letting "the model complies" be read as "the submission complies". A verdict that
travels without its scope is the same failure the disclosure exists to close, and it travels
more easily than the report does.

## Scope

This task is **a decision followed by a small change**, and the decision is the substance: what
is the minimum that has to accompany a verdict wherever a verdict appears?

**Changes**

- `services/web/src/pages/ReviewsPage.tsx` (and any other surface rendering a run's outcome
  outside the report) — the verdict does not appear without at least naming the artifact it
  describes. The row already names the model file; what is missing is that the outcome is
  *about the model*.
- Both catalogues — but note `docs/decisions.md`, *"Report prose belongs to the server, not to
  the frontend catalogue"*: if what you add is report prose it belongs on the server beside the
  disclosure. If it is a UI label on a list row, it is UI chrome and belongs in the frontend
  catalogues. Decide which this is and say why in the evidence.

**Explicitly not this task:** re-stating the whole disclosure paragraph on every row. A wall of
qualification on a list is dismissed as boilerplate and makes the real disclosure weaker, not
stronger. The question is the *minimum* that keeps the verdict honest in transit.

**Does not change:** the engine, the counts, the three-valued discipline, or the report view's
own disclosure (T-0029 owns that).

## How to prove it ran

`make verify`, `make up` with containers rebuilt, `make e2e`, and a screenshot of the reviews
list you have opened — with the verdict row visible — quoted in the evidence so the wording is
on the record. An assertion that the verdict and the scope statement appear together, and a
mutation proof that removing the scope statement fails it.

## Evidence

<!-- the builder writes this -->

## Review
