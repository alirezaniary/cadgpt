# T-0042 — The catalogue hands out a storage URL nothing authenticates

**Phase:** 3 — What the first real user needs   **Status:** open
**Touches invariants:** tenancy — by precedent rather than by breach today. **Reviewer-gated.**

## Why

Found by the T-0030 review. `services/api/cadgpt/apps/rulepack/api/v1/serializers.py:33`
serialises `source_file` — a `FileField` — straight to a URL. Against the running stack:

```
GET /api/v1/rule-packs/  ->  "source_file": "http://localhost:8000/media/rule-packs/sample/a0eeb46c-….ids"
curl <that URL>          ->  200, the IDS bytes, with no Authorization header at all
```

**This is not a tenancy leak today** — catalogue content is global by design, every tenant reads
the same packs, and the bytes are rules we publish. It is queued rather than fixed-now for
exactly that reason. Two things make it worth closing anyway.

**It sets a precedent this repository had deliberately avoided.** `MediaSerializer`
(`services/api/cadgpt/apps/media/api/v1/serializers.py:15-24`) omits `Media.file` on purpose: a
tenant's file URL is never handed out. T-0030 introduces the first "serialise a `FileField` to a
URL" in the codebase, and it becomes a real leak the first time someone copies the pattern onto
tenant data — which is precisely how the shape of a codebase turns into a defect.

**And in production the field is a lie.** With `USE_S3=False`, Django serves `MEDIA_URL` only
under `DEBUG` (`config/urls.py:26-27`), and `deploy/docker/nginx.conf` has no `/media/`
location — so `/media/rule-packs/…` falls through `try_files … /index.html` and the URL
advertises a download that returns the SPA's HTML.

## Scope

A decision and a small change. Either:

- **drop the field**, and let a pack be identified by its metadata, with the IDS reachable only
  through the check that uses it; or
- **route it through an authenticated download**, the way `Media` already is, so there is one
  way to get a file out of this system rather than two.

Prefer the second only if something actually needs to fetch the IDS; prefer the first if nothing
does. Do not leave a raw storage URL on the serializer.

- `services/api/cadgpt/apps/rulepack/api/v1/serializers.py`, and the view if a download route is
  added. Tests for whichever path is chosen.
- If a download route is added it is **read-only and authenticated**, and it must not become a
  way to enumerate storage keys.

**Does not change:** the catalogue's global readability, the model, the seeder, or `Media`.

## How to prove it ran

`make verify` with the 5 import contracts kept, then against the running stack: the list
response no longer carrying a raw storage URL, and — if a download route was added — a real
authenticated fetch returning the IDS bytes and an unauthenticated one refused. Paste both
responses and the `curl` that previously returned 200 now failing.

## Evidence

<!-- the builder writes this -->

## Review
