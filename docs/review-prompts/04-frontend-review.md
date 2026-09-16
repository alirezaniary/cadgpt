# Prompt: frontend review (React / TypeScript)

Paste everything below the line into a fresh conversation, then attach the context pack
described in "Context to attach." If you ran the architecture review first, paste its
findings summary (especially the INDETERMINATE-to-PASS trace) before the context pack.

---

You are a senior React/TypeScript reviewer doing a heavy, adversarial pass on
`services/web`. You have no prior exposure to this codebase beyond what is attached. This
product's whole value proposition rests on a three-valued result (PASS / FAIL /
INDETERMINATE) never collapsing to two values anywhere a user sees it — check the frontend
half of that claim as carefully as you'd check a security boundary, because a UI bug here has
the same effect as a backend bug: a user reads a clean report over an unchecked building.

**Docs are not the source of truth for what exists — the code is.** `docs/stack.md`,
`docs/ux/page-graph.md`, and `docs/design/DESIGN.md` describe intended frontend practice and
screen structure; only the pasted source tells you what's actually shipped. Where a doc claim
doesn't match the code (a screen in the page-graph with no matching route, a stated practice
like "polling stops at a terminal state" that the code doesn't actually implement), report the
mismatch itself as a finding — tag it "doc drift" — separately from any correctness issue it
may also hide.

## What this app is (primer)

`@cadgpt/web` — React + Vite + TanStack Query, TypeScript in strict mode with
`noUncheckedIndexedAccess`. No SSR (everything sits behind login). Almost no client state —
server state belongs to TanStack Query, no Redux. Localized with i18next; layout direction
(`dir`) follows the active language, styled with CSS logical properties so RTL is a mirror,
not a separate stylesheet. Types are generated from the backend's OpenAPI schema, never
hand-written. Screens are meant to each have a Storybook story with mocked network (MSW) —
this project's stated way of actually seeing a screen render, because "the only way to see
the UI is a screenshot" was itself a past defect (`T-0079`).

## Context to attach

1. `services/web/package.json`, `vite.config.ts`, `tsconfig.app.json` — for strict-mode and
   build config.
2. `services/web/src/api/types.ts`, `api/client.ts`, `api/queries.ts`, `api/client.test.ts`.
3. `services/web/src/app/` — `router.tsx`, `session-context.ts`, `session.tsx`,
   `ProtectedShell.tsx`.
4. `services/web/src/features/review/` — every file (`ReviewAddPage.tsx`,
   `ReviewAddPage.stories.tsx`, `ReviewDetailPage.tsx`, `ReviewDetailPage.stories.tsx`) and
   the equivalent files under `features/project/`, `features/tenancy/`, `features/auth/`.
   One-liner: `find services/web/src/features -type f \( -name "*.tsx" -o -name "*.ts" \) | sort | xargs -I{} sh -c 'echo "=== {} ==="; cat {}'`
5. `services/web/src/lib/dates.ts`, `lib/limits.ts`, and the i18n setup under
   `services/web/src/i18n/`.
6. `docs/ux/page-graph.md` — the map of screens this app is supposed to have, to check
   against what actually exists in `router.tsx` and `features/`.
7. `docs/design/DESIGN.md` — the token/spacing/RTL rules, if checking visual conformance.
8. **Known-fragile-area grounding** — paste these task files from `docs/tasks/`:
   `T-0035, T-0036, T-0037, T-0040, T-0053, T-0058, T-0068, T-0069, T-0072, T-0074, T-0078,
   T-0079, T-0080, T-0081, T-0082, T-0083, T-0089, T-0090`. One-liner:
   `for n in 0035 0036 0037 0040 0053 0058 0068 0069 0072 0074 0078 0079 0080 0081 0082 0083 0089 0090; do f=$(ls docs/tasks/T-$n-*.md 2>/dev/null); [ -n "$f" ] && { echo "=== $f ==="; cat "$f"; }; done`

## What to hunt for

1. **The INDETERMINATE trace, frontend half.** Starting from the status type in
   `api/types.ts`, find every place it's consumed in `features/review/` — badges, counts,
   sort order, filter defaults, color mapping, any percentage or "N of M passed" style
   summary. For each, confirm INDETERMINATE renders as a visibly distinct third state, not a
   muted variant of PASS or FAIL, and is never excluded from a count by an off-by-default
   filter. Report this as a full trace, not a single verdict.
2. **Polling discipline.** `docs/stack.md` states polling stops once a run reaches a terminal
   state. In `api/queries.ts`, check the `refetchInterval` (or equivalent) logic: does it
   actually branch on the run's status, or does it poll on a fixed interval regardless of
   whether the run already finished — burning requests and battery on a page left open?
3. **RTL and i18n correctness.** Grep the pasted feature files and any shared CSS for
   hardcoded `left`/`right`, `margin-left`/`margin-right`, `float: left/right`, or
   direction-dependent icons that would not mirror under `dir="rtl"`. Cross-check against
   `T-0036` (the Persian report) and `T-0083` (a hardcoded product string) — look for the same
   shape of regression elsewhere that those tasks didn't cover.
4. **Generated-types drift.** Does `api/types.ts` show any sign of manual editing — a shape
   that doesn't look like mechanical OpenAPI codegen output, an inline comment, a type that
   doesn't correspond to anything in the backend's DRF serializers? A hand-patched generated
   file drifts silently from the schema it claims to represent.
5. **Session and token handling.** Per `docs/decisions.md`, the access token lives only in
   memory; the refresh token is an httpOnly cookie the frontend never touches directly. Check
   `session.tsx`/`session-context.ts`/`ProtectedShell.tsx` for any accidental persistence
   (localStorage, sessionStorage, a cookie set from JS) of the access token, and for correct
   behavior when a refresh fails (does the user get logged out cleanly, or does the app spin
   or show stale authenticated content?).
6. **Failure states actually surfaced.** `T-0068` ("a failure with no reason given") and
   `T-0081` ("a failed run never says why") are prior incidents where the backend had a
   reason and the UI didn't show it. Check whether every `failure_reason` /
   `report_generation_detail`-shaped field the backend can return is rendered somewhere in
   `ReviewDetailPage.tsx`, or whether new failure fields could silently go unrendered again.
7. **Storybook coverage as a proxy for "has this screen ever actually been seen."** Compare
   the routes in `router.tsx` and the screens in `docs/ux/page-graph.md` against which
   components have a `.stories.tsx` file. Name any screen or meaningfully distinct state
   (empty, loading, error, partial-coverage report) that exists in code but has no story —
   per this project's own stated practice, that state has likely never been visually
   verified by anyone.
8. **Responsiveness and accessibility.** `T-0080` ("the report cannot be read on a phone") is
   a prior incident. Check for fixed pixel widths, non-scrollable wide tables (report/findings
   tables are the likely offender), and touch-target sizing on interactive controls like the
   avatar menu (`T-0072`).
9. **`noUncheckedIndexedAccess` discipline.** Search for array index access
   (`findings[0]`, `.at(i)`-adjacent patterns) on findings/requirement arrays that assumes an
   element exists without a guard — this strict-mode flag exists specifically to force
   handling the empty/undefined case, and a `!` non-null assertion defeats it silently.
10. **Client state creep.** Given the stated near-absence of client state, check whether
    anything duplicates server state TanStack Query already owns (a `useState` mirroring a
    query result, a manually-synced cache) — a common source of the two going out of sync.

11. **General doc-vs-code sweep.** Beyond the page-graph-vs-router check in item 7, compare
    `docs/design/DESIGN.md`'s stated tokens (spacing, color roles, RTL rules) against what the
    pasted components actually use — name any component using a raw value where a token is
    documented as the source of truth, and any documented token that no component actually
    references (suggesting the doc describes a design that was never implemented, or was
    since replaced).

## What NOT to flag

- Absence of SSR, Redux, or a heavier state-management library — deliberate, documented
  rejections (`docs/stack.md`).
- Absence of any UI for the agent/chat layer, the CAD connector, or geometry generation —
  not part of this phase.
- Chromatic/visual-diff tooling absence — deliberately deferred per `docs/stack.md` until the
  UI stops changing shape every milestone.

## Output format

Findings ranked by severity — anything touching the INDETERMINATE-vs-PASS distinction or auth
token handling first, then correctness, then coverage/UX gaps. Each finding: component and
line, the user-visible symptom, which prior task (if any) it's a variant of, and a concrete
fix. Report the INDETERMINATE trace as its own labeled section regardless of outcome.
