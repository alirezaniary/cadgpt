# T-0077 — a review that doesn't say whose project it is

**Phase:** 3   **Status:** open
**Touches invariants:** none.

## Why

Found by T-0073's review. `Review.project` is now required, but `ReviewSerializer`
(`cadgpt/apps/review/api/v1/serializers.py`) never gained a `project` field — confirmed
live, the 201 body from a review creation carries `model_file`, `rule_set`, `latest_run`,
no `project`. The only way to learn which project a review belongs to is to already know
it, by having filtered `/api/v1/reviews/?project=<uuid>` to find it. T-0074's
`/projects/:uuid/reviews/:uuid` detail route can get away with trusting the URL's own
`:uuid` segment, but any other consumer of `GET /api/v1/reviews/<uuid>/` — a future admin
view, a script, a second frontend surface — cannot tell a review's project from the
resource itself.

## Scope

- `cadgpt/apps/review/api/v1/serializers.py`, `ReviewSerializer` — add a `project` field.
  Match the existing pattern for a related-object reference on this serializer (check
  whether `rule_set` is a bare uuid, a nested object, or a `SerializerMethodField` today,
  and follow that shape rather than inventing a new convention for one field).
- Confirm `ReviewFilterSet`'s existing `project` filter and this new output field agree on
  what they call the value (uuid vs nested), so a client can round-trip
  `?project=<value>` using the value it just read off a review.

## How to prove it ran

Real path: `GET /api/v1/reviews/<uuid>/` against the compose stack, showing the response
body now includes the review's project. `make verify` with any serializer test this
touches updated.

## Evidence

## Review
