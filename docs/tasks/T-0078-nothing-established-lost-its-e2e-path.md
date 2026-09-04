# T-0078 — "nothing established" lost its e2e path

**Phase:** 3   **Status:** open
**Touches invariants:** none.

## Why

Flagged as NOT DONE by T-0074. `nothing_established.ids` exercised
`NO_SUBJECTS_NOTHING_CHECKED` vs. `NO_SUBJECTS_BUT_REQUIRED` — a real coverage-math
distinction the engine still enforces and the API pytest suite still covers (unchanged,
235 passing) — but the only way to reach it in the browser was uploading an arbitrary IDS
file at review-creation time, an affordance T-0074 removed per the 2026-09-04 decision.
None of the three catalogue-seeded packs (`door_width`, `door_name_recorded`,
`door_prohibited`) reproduce the scenario against `three_doors.ifc`, so the browser-level
(e2e) half of this regression's coverage is gone. T-0074 correctly declined to fix this
itself — its own scope states the backend does not change, and adding a pack to the seed
manifest is a backend change.

## Scope

- `services/api/cadgpt/apps/rulepack/management/commands/seed_rule_packs.py` (or wherever
  `SEED_MANIFEST` actually lives — confirm the path) — add `nothing_established.ids` as a
  seeded catalogue pack, named so it's identifiable in the catalogue picker (e.g. "Nothing
  established (sample)"), same treatment as the three packs already there.
- `services/web/e2e/report.spec.ts` — restore the F1/F2 assertions T-0074 dropped, now
  driven through the catalogue picker instead of an upload: select the new pack, run the
  check, assert `NO_SUBJECTS_NOTHING_CHECKED` vs. `NO_SUBJECTS_BUT_REQUIRED` render
  correctly in the report.

## How to prove it ran

`docker compose -f deploy/compose.yaml exec -T api python manage.py seed_rule_packs`
showing the new pack created, then the real e2e run showing the restored spec passing
against the rebuilt stack. `make verify` green.

## Evidence

## Review
