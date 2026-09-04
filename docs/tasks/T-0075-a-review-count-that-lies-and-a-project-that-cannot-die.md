# T-0075 — a review count that lies, and a project that can never die

**Phase:** 3   **Status:** open
**Touches invariants:** none — a correctness bug in denormalized counting and an API
error path, not the tenancy boundary itself.

## Why

Found by T-0073's review, reproduced live against the running stack:

```
DELETE /api/v1/reviews/<uuid>/            -> 204
GET    /api/v1/reviews/?project=<uuid>    -> count 0
GET    /api/v1/projects/                  -> review_count: 1      <-- lies
DELETE /api/v1/projects/<uuid>/           -> 409 "This project has reviews and cannot be deleted."
```

`Review.delete()` is a soft delete (`SoftDeleteModelMixin`) — the row survives with
`project_id` intact. `ProjectViewSet.get_queryset`'s `Count("reviews")` annotation
(`cadgpt/apps/project/api/v1/views.py:44`) joins the raw `review_review` table, uncorrelated
with `Review.objects`'s default `alive()` filtering
(`cadgpt/apps/review/repositories/custom_managers.py:14-16`), so a deleted review still
counts. Same bug in `ProjectSerializer`'s fallback (`obj.reviews.count()`,
`cadgpt/apps/project/api/v1/serializers.py:27`). Because `Review.project` is
`on_delete=models.PROTECT`, a project that once had any review — deleted or not — can
never be deleted through the API: `perform_destroy`'s `ProtectedError` handler
(added in T-0073, `views.py:58-70`) now surfaces as a *permanent* 409 with no way out,
since nothing clears `project_id` off a soft-deleted review.

## Scope

- `cadgpt/apps/project/api/v1/views.py` — the `Count("reviews")` annotation must count
  only alive reviews: `Count("reviews", filter=Q(reviews__deleted_at__isnull=True))` or
  the equivalent through whatever `SoftDeleteModelMixin` actually names its liveness
  field — check `cadgpt/apps/base/models.py` for the exact field name rather than
  guessing `deleted_at`.
- `cadgpt/apps/project/api/v1/serializers.py` — the fallback `review_count` path (if the
  annotation isn't always present on the object passed to it) gets the same filter.
- The permanent-409 dead end: a project whose only reviews are all soft-deleted must be
  deletable. Two ways to close this, pick the one that matches how `RuleSet` (the other
  `PROTECT`-guarded, soft-deletable model) already handles the equivalent case — check
  whether `RuleSet`'s own deletion path has already solved this, and either reuse that
  pattern or, if `RuleSet` has never faced it either, change `Review.project`'s
  `on_delete` to only protect against *alive* reviews (a `SET_NULL`-on-delete post-soft-
  delete signal, or restructure the FK) — whichever is the smaller, more consistent
  change. Do not invent a third pattern this codebase doesn't already have a reason for.
- Add a regression test: soft-delete a review, assert its project's `review_count` is 0
  and that the project can then be deleted (or, if the chosen fix keeps `PROTECT` for a
  reason, assert deletion is possible via whatever path was chosen).

## How to prove it ran

Real path against the compose stack, reproducing the exact four-call sequence quoted
above and showing it now ends differently at steps 3 and 4:

```
DELETE /api/v1/reviews/<uuid>/            -> 204
GET    /api/v1/projects/                  -> review_count: 0
DELETE /api/v1/projects/<uuid>/           -> 204 (or whatever the chosen resolution returns)
```

Plus `make verify` with the new regression test included and passing.

## Evidence

## Review
