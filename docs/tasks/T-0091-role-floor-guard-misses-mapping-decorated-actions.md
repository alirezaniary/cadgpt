# T-0091 — the role-floor structural guard can misattribute permissions under `@action.mapping`

**Phase:** 3   **Status:** open
**Touches invariants:** none — a latent gap in a test's own coverage, not a live defect
(the pattern it would miss is unused anywhere in this codebase today).

## Why

Found by T-0060's review. `services/api/cadgpt/tests/test_role_floor.py`'s
`_permissions_for_action` sets `view.action = action_func.__name__` when evaluating an
extra action's permissions. DRF actually resolves `self.action` from
`self.action_map.get(request.method)` at request time — which matters because
`@some_action.mapping.post` lets a second method name share one route with a different
HTTP verb under the *first* action's name. Example: `@report.mapping.post def
regenerate_report(...)` would still resolve to `get_extra_actions()` returning only
`report` (the `@action`-decorated one); the guard would evaluate `report`'s permissions
(the GET's) and silently never look at `regenerate_report`'s POST at all. An author who
widens `get_permissions()` for `"report"` but not `"regenerate_report"` would ship an
ungated POST that this guard reports clean.

Not reachable today — no action in this codebase uses `.mapping` — so this is a coverage
gap in a safety net, not a live vulnerability. Recorded because the guard's whole purpose
is to catch the next author's mistake, and this is a mistake shape it would currently miss.

## Scope

- `test_role_floor.py`'s action-discovery walk resolves the actual `{http_method:
  action_name}` mapping for a mapped action (the same information DRF's own
  `action.mapping` / `action_map` construction uses) rather than assuming one name per
  decorated method, so a `.mapping`-attached verb is evaluated under its own name, not its
  sibling's.
- A regression test: add a `.mapping`-decorated write verb, deliberately ungated, and show
  the guard catches it — the same mutation-proof shape T-0060's own structural test used for
  its other cases.

## How to prove it ran

`make verify`, then the mutation proof: a temporary `.mapping`-attached, deliberately
ungated write action, showing the guard now fails on it; reverted, showing it passes.

## Evidence

## Review
