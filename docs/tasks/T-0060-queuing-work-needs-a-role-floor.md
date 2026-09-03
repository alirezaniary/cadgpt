# T-0060 — A viewer can queue work on the shared check queue

**Phase:** 3   **Status:** open
**Touches invariants:** tenancy — the role half, not the isolation half. **Reviewer-gated.**

## Why

Found by the T-0051 review. `CheckRunViewSet.permission_classes = (IsTenantMember,)`
(`views.py:102`) with no `get_permissions` override, while the analogous work-queuing action
`ReviewViewSet.check` requires `IsTenantMemberOrAbove` (`views.py:62-65`).

`IsTenantMember` only asserts that a membership exists (`tenancy/permissions.py:18-30`). So a
**VIEWER — documented as "May read the tenant's work but change nothing" — can enqueue
`generate_report_file`.** With `throttle_classes=[]` (`views.py:151`) and no dedupe, a POST loop
floods the `checks` queue that real model checks run on.

**Tenant isolation itself is intact.** The reviewer confirmed `get_object()` goes through
`tenant_queryset()`, so nobody reaches another tenant's run. This is a role gate, not a leak — the
structural tenancy invariant is unaffected, and the queued task should not be read as a hole in it.

The asymmetry is the tell: the two work-queuing POSTs in the product disagree about who may queue
work, and the newer one is the permissive one. That is how a role model erodes — not by a decision,
but by a new endpoint not inheriting one.

## Scope

**Changes**

- Queuing work requires the same role floor wherever it happens. Bring `generate_report` in line
  with `ReviewViewSet.check`, or state why the two genuinely differ.
- Decide whether a work-queuing POST should carry a throttle. `throttle_classes=[]` was a deliberate
  choice on the check action; whether it is right for an action any member can press repeatedly is a
  separate question. Say which and why.
- A test that fails if a work-queuing endpoint is added without a role floor. The defect here is not
  one endpoint's permission tuple — it is that nothing noticed the new endpoint disagreeing with the
  old one.

**What explicitly does not change**

- Tenant isolation, which is intact and structurally tested.
- The role model itself, or what VIEWER means.

## How to prove it ran

`make verify`, then over real HTTP: a VIEWER refused on both work-queuing endpoints, a member above
that floor accepted on both, responses pasted. Then the structural test demonstrated failing against
a deliberately unguarded new endpoint — a test that only asserts today's tuple would not have caught
this and will not catch the next one.

## Evidence

## Review
