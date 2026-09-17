# T-0093 — a paste that shows one uuid where it claims two, and a docstring citing a throttle that never fires

**Phase:** 3   **Status:** open
**Touches invariants:** none — both are accuracy corrections, not code defects.

## Why

Found by T-0060's review, both small and both about a claim overstating what was actually
shown or is actually in force.

1. **The idempotence proof pastes one uuid, not two.** T-0060's evidence, section 5, asserts
   "the same `Media` uuid (`b7c66d0e...`) both times" for the automatic first
   `generate_report_file` dispatch and the manual second call — but only the second call's
   return value is pasted; the first is identified only by task id and duration. The claim
   that the two share a `Media` uuid is asserted, not demonstrated. The reasoning it
   supports (idempotence) has been proven a different way (the row-lock code was read and
   the second call's duration and outcome are consistent with a no-op), so nothing hinges
   on this, but the paste should either be completed (paste the first call's return value)
   or the claim narrowed to what was actually shown.

2. **`throttle_classes=[]` is not the operative mechanism on `generate_report`'s route.**
   Because `CheckRunViewSet.generate_report` is reached via a hand-wired
   `as_view({...})` route rather than router registration, an `@action` decorator's
   `throttle_classes` kwarg (if one were ever added there) would not actually apply the way
   it would on a router-registered action — the same routing quirk T-0060's structural-test
   fix (its own fail-now finding) had to account for on the permissions side. Today this is
   harmless: `CheckRunViewSet` sets no `throttle_scope`, so the global `ScopedRateThrottle`
   allows everything regardless. But the docstring's reasoning names `throttle_classes=[]`
   as if it were an active, deliberate choice on this route, when the mechanism it refers to
   isn't actually in force there.

## Scope

- Complete or narrow the idempotence paste in the task file's evidence (repository record,
  not urgent — a documentation-only fix to the historical record).
- Correct `generate_report`'s docstring to either state accurately that `throttle_classes`
  has no effect on a hand-wired route (and name what actually governs throttling there —
  the global `ScopedRateThrottle` with no `throttle_scope` set), or move any real throttle
  decision to a mechanism that does apply on this route, if T-0092 concludes one is needed.

## How to prove it ran

For (1): the corrected evidence section or the completed paste. For (2): the corrected
docstring text, with a one-line confirmation of what mechanism actually governs this route's
rate limiting today.

## Evidence

## Review
