# Onboarding and workspace

Reconstructed on 2026-09-06 from the shipped screens (T-0067, T-0069, T-0072). Written
after the fact, not before — the acceptance criteria below are read off the code and the
e2e specs, so they describe what the app does, not what someone once intended. Anything
that reads as a decision rather than an observation is called out under Assumptions.

**As a** architect at a design office who has just been sent a link to CADGPT
**I want** to get from "I have an account" to "I can see somewhere to put a model" without
being asked anything I have no basis to answer yet
**So that** the first thing I evaluate about this product is whether it checks my model
correctly, not whether I can operate its sign-up form

## Acceptance criteria

- Given a first visit with no session, when the page loads, then the sign-in card is shown
  — not a marketing page, not a blank frame that resolves into one.
- Given an account I do not have yet, when I follow "Need an account?" and register, then I
  am signed in by the same act, without a second trip through the sign-in form.
- Given I am signed in and belong to no workspace, when the app resolves my tenants, then I
  am asked for one thing — a workspace name — and the slug is derived rather than requested.
- Given I belong to exactly one workspace, when I sign in, then it is selected for me and I
  never see a workspace picker.
- Given I belong to more than one, when I open the account menu, then I can switch, and
  switching returns me to `/projects` rather than leaving me on a URL scoped to the
  workspace I just left.
- **Given my tenant list has not arrived yet, when the app cannot tell "fetching" from "you
  have none", then it shows neither** — the shell is withheld until the two can be
  distinguished, so nobody is shown a create-workspace screen they do not need.
- Given credentials the server rejects, when I submit, then the server's own wording is
  shown, and the form stays filled.
- Given I sign out, when someone else signs in on the same tab, then none of my data is
  visible to them — the query cache is cleared, not selectively invalidated.

## Explicitly out of scope

- Password reset, email verification, OTP, and social sign-in. `RegisterSerializer` accepts
  email and password and nothing else.
- Inviting a colleague into a workspace, and any role UI. `role` is on the wire and unused.
- Choosing an interface language. It is a build-time decision (`src/i18n/index.ts`), and a
  runtime switcher was deliberately removed — it implied a per-user choice this product
  does not offer.

## Assumptions / open questions

- **The auth screens have no routes.** Sign-in, register, and create-workspace are branches
  of `App`, so none of them is linkable and none survives a reload as itself. That is fine
  today and would need revisiting the moment anything wants to deep-link (an invitation
  email, an expired-session bounce that returns you where you were).
- **A workspace name is not unique but its slug is**, so the slug carries a random suffix.
  Nobody has yet seen what that slug looks like to a user, because nothing displays it.
- Whether an architect arrives with an account already created for them by a colleague is
  unknown — it changes whether registration or invitation is the primary path.
