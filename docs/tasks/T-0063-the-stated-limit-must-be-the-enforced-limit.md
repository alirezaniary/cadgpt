# T-0063 — Nothing asserts that the limit we state is the limit we enforce

**Phase:** 3   **Status:** open
**Touches invariants:** "never assert something we did not establish", applied to our own promise.

## Why

Found by the T-0033 review. The upload ceiling now exists in two places that can disagree silently:

- `services/web/src/lib/limits.ts:13` hardcodes `100 * 1024 * 1024`;
- `services/api/cadgpt/config/settings/base.py:167` is
  `env.int("MAX_UPLOAD_BYTES", default=100 * 1024 * 1024)` — **overridable at runtime**.

`e2e/upload-limit.spec.ts` asserts the *frontend* constant's rendering, so it passes at any server
value, and there is no API test for the model ceiling at all — `test_media_service.py:70` covers only
`IDS_RULESET`.

Concrete input: deploy with `MAX_UPLOAD_BYTES=20971520`. `make verify`, `make e2e` and the whole
suite stay green while the UI promises "Up to 100.0 MB per model" and the server rejects at 20MB. The
user is told a number we do not honour — which is the failure mode T-0033 existed to close, moved
from "the number was never measured" to "the number is no longer true".

## Scope

**Changes**

- The stated limit and the enforced limit come from one source, or a test fails when they diverge.
  The server already knows the number; the frontend should be told rather than duplicating it.
- An API-level test for the model ceiling, which does not exist today.

**What explicitly does not change**

- The value itself, or its derivation. That is T-0033's, and if this task changes the number it has
  gone wrong.
- `MAX_BYTES[IDS_RULESET]`.

## How to prove it ran

`make verify`, then the divergence made impossible: run the stack with `MAX_UPLOAD_BYTES` overridden
to a different value and show the UI stating **that** number, not the compiled-in one — and show the
guard failing when the two are forced apart. A test that passes at any server value is the defect,
so a test that cannot fail is not the fix.

## Evidence

## Review
