# T-0068 — Registration fails, and the form never says why

**Phase:** 3   **Status:** open
**Touches invariants:** none.

## Why

Found by the T-0067 review, on the signup form that task just built. `RegisterPage.tsx` catches
`ApiError` and renders only `caught.message` — the top-level `detail` string. The real reason
lives in `ApiError.fieldErrors`, already parsed off the API's problem-detail body, and is simply
discarded.

Live against the stack: a password under 12 characters returns
`{"detail":"The password is not acceptable.","errors":{"password":["This password is too short.
It must contain at least 12 characters.","This password is too common."]}}`. The form shows "The
password is not acceptable." — no length rule stated anywhere on the page, before or after the
failure. A duplicate email is the same shape: `detail` is a generic "The submitted data is not
valid." while `errors.email` holds the actual cause. A real new user has no way to fix either
without guessing.

The second half compounds it. `RegisterView` and `LoginView` share one DRF throttle scope,
`"auth"`, rated `10/min` per anonymous IP in production settings. `RegisterPage` makes two calls
per signup — register, then `signIn` with the same credentials — so a small office signing up a
few people in quick succession can have the second call of a pair 429 after the account was
already created. The user sees a failure, presses the button again, and now gets "email already
exists" with nothing telling them the account is real and pointing at "Sign in instead."
`onboarding.spec.ts` never exercises this because its one password is deliberately compliant.

## Scope

**Changes**

- `RegisterPage.tsx` renders the field-level reasons from `ApiError.fieldErrors` when present
  (the password rules, the duplicate-email case), not just the generic `detail`. Match whatever
  pattern this codebase already uses for field errors elsewhere in the frontend, if one exists —
  check `services/web/src` before inventing a new one.
- State the password policy on the form itself (12-character minimum, not-too-common), not only
  after a failed submission — so the common case never round-trips to the server to learn it.
- The 429 case specifically: if `signIn` fails immediately after a successful `register` call,
  tell the user their account was created and point them at sign-in, rather than showing a bare
  throttle error. Decide whether that requires distinguishing "register succeeded, signIn
  throttled" from "register itself was throttled" — say which in the evidence.

**What explicitly does not change**

- The throttle rates and scope themselves (`config/settings/base.py`) — this is a UX fix for the
  window they create, not a rate-limit policy change.
- No new backend validation. `RegisterSerializer`/`AccountService.register` already produce the
  `errors` the frontend is currently throwing away.

## How to prove it ran

`make verify`, then a real browser session against `make up`: submit a too-short password and
show the specific reason rendered (not the generic sentence); submit a duplicate email the same
way; and drive the throttle window (or mock the second call's failure at the network layer if
driving the real 10/min limit is impractical) to show the "account created, sign in instead" case
actually renders.

## Evidence

## Review
