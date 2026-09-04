# T-0069 — Three onboarding edges T-0067's happy path never reaches

**Phase:** 3   **Status:** open
**Touches invariants:** none directly — all three are edges around the tenancy screens T-0067
added, not violations of the invariant itself.

## Why

Found by the T-0067 review; none severe enough to gate that task's fix-now round, all three real.

1. **Stuck after a last membership is revoked.** `App.tsx`'s first-workspace guard tests `!tenant
   && tenants.data && tenants.data.results.length === 0`. `tenant` is React state that only
   changes through `chooseTenant`, so a user whose sole membership is revoked mid-session keeps a
   non-null `tenant` pointing at a workspace their next request will 403 against, and never falls
   through to `CreateWorkspacePage`. Only a full page reload (which re-fetches `tenants.data`
   fresh) recovers. Same underlying shape as the cache-staleness fix T-0067's review just gated
   into that task — worth re-checking after that lands, in case it already covers this.
2. **`slugify`'s collision-avoidance argument weakens for non-Latin names.**
   `CreateWorkspacePage.tsx`'s `slugify()` collapses any name with no `[a-z0-9]` run — Persian,
   Arabic, CJK — to the single stem `"workspace"`, so every such tenant shares one stem and the
   random 6-character suffix becomes birthday-bound across all of them rather than scoped per
   name (~47k such tenants before even odds of a collision, per the review's estimate). Not
   exploitable — `TenantProvisioningService.create` 409s on a real collision and the frontend can
   retry — but this product ships to Persian-speaking offices first, so the case is not rare
   here the way it would be elsewhere.
3. **`RegisterPage` never sends `language`.** `CreateWorkspacePage` does. `RegisterSerializer`
   accepts and defaults it, so every registration silently becomes `"en"` regardless of what
   language the signup form itself was rendered in, and the account's stored error-localization
   language starts wrong for a Persian user from their very first screen.

## Scope

**Changes**

- Fix or explicitly justify not fixing each of the three above. They're independent — a partial
  landing (e.g. 3 fixed, 1 and 2 deferred with reasoning) is acceptable if said plainly in the
  evidence, per this project's own "partially fixed must list exactly what remains" rule.
- For (1): re-check against `session.tsx` once T-0067's fix-now round lands — the query-cache
  clear on sign-out may or may not also cover a mid-session revocation; state which.
- For (2): a name-derived stem for non-Latin input is the likely fix (e.g. transliterate, or fall
  back to a hash of the name rather than a constant string) — your call, justified in evidence.
- For (3): thread the current i18n language into the `POST /v1/auth/register/` call the same way
  `CreateWorkspacePage` already does for tenant creation.

**What explicitly does not change**

- No change to `TenantProvisioningService`, `AccountService`, or the uniqueness constraint on
  `Tenant.slug` — all three fixes are frontend-side.

## How to prove it ran

`make verify`, then for each fix landed: the specific real-path repro from the Why section, shown
before and after — a revoked membership no longer stranding the user without a reload; a
Persian-named workspace producing a slug that isn't the shared `"workspace"` stem; a Persian-UI
registration whose account ends up with `language: "fa"`, verified against the API response or DB
row, not just the request payload sent.

## Evidence

## Review
