# T-0058 — In the terminal-failure state, "Generate report" is a button that cannot change anything

**Phase:** 3   **Status:** open
**Touches invariants:** none, but it is the failure T-0051 existed to eliminate.

## Why

Found by the T-0051 review. `ReviewsPage.tsx:351-361` renders the same `report-file-generate` button
in the `reportGenerationError` branch, and `views.py:170` gates only on run status, so the POST
returns 202. The dispatched task re-renders the full report, `MediaService._validate` rejects it
identically, `generate` rewrites the identical error and returns.

The user sees the same red sentence with no feedback and no explanation, and each press costs a full
report render on the shared `checks` queue — the queue real model checks run on.

The code already disagrees with itself about this: `missing_report`'s own docstring says retrying
"would just restate the same rejection forever", which is why the queryset excludes these rows —
while the UI offers the retry anyway. T-0051's task file named "a button that silently does nothing"
as one of the two failures it existed to close, and this is that failure, in the state the task
itself introduced.

## Scope

**Changes**

- The terminal-failure state does not offer an action that cannot succeed. What it offers instead is
  the decision: nothing, an explanation of what would have to change, or a retry that is only
  enabled once something actually has (see T-0059, which is the operational half — after an operator
  raises the cap, these runs currently have no sweep at all). Decide, implement, and say why.
- Whatever is shown says what happened in terms of the run, not of the storage layer.

**What explicitly does not change**

- The `TOO_LARGE` decision itself — a run is not retro-failed because its rendering did not fit.
  That was settled in T-0051 and is in `docs/decisions.md`.
- The route's status gate.

## How to prove it ran

`make verify`, then a run driven into the terminal-failure state on the real stack, rendered in the
browser, showing what the user is now offered — and the absence of a request that cannot succeed.
`make e2e` drives real chromium and T-0051 added a spec that reaches this state.

## Evidence

## Review
