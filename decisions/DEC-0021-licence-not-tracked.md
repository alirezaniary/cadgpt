# DEC-0021 — Licence and legal questions are out of engineering scope

**Status:** DECIDED
**Date:** 2026-08-30
**Decided by:** Stakeholder
**Affects:** `docs/architecture/test-assets.md`, `docs/process/testing-strategy.md`, every task

## Problem
`prd.md` §6 already settles this for inherited components: *"Component selection is on technical
merit alone. Open source licence terms are not a selection criterion and are not tracked in this
document."*

I extended that tracking to **test data** on my own initiative, on the reasoning that a fixture
is committed to the repository and therefore travels with it in a way a server-side dependency
does not. Having raised it, the stakeholder has directed that it not be tracked at all.

## Constraints
- Stakeholder direction, 2026-08-30: ignore all legal and licence issues.
- `prd.md` §6 already establishes the same position for components, so this is consistent with a
  settled decision rather than a new exception to one.
- Licence exposure is a business matter borne by the stakeholder, not a technical property of
  the system. It is not something engineering judgement improves.
- Every hour spent on licence provenance is an hour not spent on the custom surface, which is
  the only thing here nobody else has built.

## Decision
Licence and legal considerations are **out of scope for this repository**. Specifically:

- Not a selection criterion for any dependency, sample model, sample rule set, or fixture.
- Not tracked, catalogued or annotated in any document here.
- **Not a build gate.** No harness gate checks it, and none is added.
- Not a reason for a task to stop, escalate, or raise a decision record.

Components, models and rule sets are chosen on technical merit and nothing else.

## Expected result
No task spends time on provenance research. `docs/architecture/test-assets.md` inventories what
is technically useful and says nothing about terms. The harness stays at sixteen gates.

## Reopens if
The stakeholder reopens it. Their own two conditions are already recorded in `prd.md` §6 —
raising or selling into a market where acquirer diligence makes the copyleft boundary live, and
connector distribution, since that component ships to user machines. Neither is engineering's
call to make and neither is monitored from here.

## Consequences accepted
Licence exposure is unmeasured and will stay unmeasured. That is the intended trade: it is a
business risk the stakeholder has chosen to carry directly rather than have the engineering
process carry on their behalf, and it buys focus on the small custom surface that is the only
thing in this repository nobody else could have written.
