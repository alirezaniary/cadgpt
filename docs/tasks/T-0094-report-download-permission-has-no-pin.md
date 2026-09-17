# T-0094 — nothing pins the report download to `IsTenantMember`

**Phase:** 3   **Status:** open
**Touches invariants:** tenancy — the role half, same as T-0060, but in the direction of
"stays permissive," not "must be gated."

## Why

Found by T-0060's review. `CheckRunViewSet.report_file` (the GET half of the same
hand-wired route `generate_report`'s POST shares) was confirmed live to still return 200
for a VIEWER — correct, a VIEWER may read the tenant's work. But nothing in the test suite
pins this: T-0060's new `get_permissions` override branches only on
`self.action == "generate_report"`, falling through to `super().get_permissions()`
(`IsTenantMember`) for everything else including `report_file`, and no test asserts that a
VIEWER can still download a report. A future widening of that branch — someone changing
the condition to also cover reads, or a copy-paste that flips which action gets the raised
floor — would silently lock VIEWERs out of their own reports with nothing in `make verify`
noticing.

## Scope

- A short regression test: a VIEWER-role member can `GET` a succeeded run's `report_file`
  (200, real file content), on the same fixtures T-0060's own tests already set up.

## How to prove it ran

`make verify` with the new test included, and a mutation check: change the `get_permissions`
override to also gate `report_file`, show the new test fail, revert, show it pass.

## Evidence

## Review
