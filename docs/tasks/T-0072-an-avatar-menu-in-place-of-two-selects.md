# T-0072 — an avatar menu in place of two selects

**Phase:** 3   **Status:** done
**Touches invariants:** none — visual/UX only, plus a single build-time i18n decision.

## Why

The product owner rejected T-0071's own fix outright: styling the native `<select>` was
the wrong move regardless of how well it matched the theme — "no ugly dropdown, who would
design such ugly dropdown?" The correct pattern is an avatar the user clicks, opening a
menu that carries the organization name, the signed-in email, workspace switching, and
sign-out — never a bare `<select>` in the topbar.

Raised in the same conversation: the language switcher is gone too, not restyled. Explicit
product decision — this is a single-language product, "no change is allowed, one hard
coded, I decide what, if I want I change it not the user." Persian was chosen as that
hardcoded language: it is what the whole visual identity (T-0070/T-0071, modeled on
zohal.io) was already built around.

## Scope

**`services/web/src/app/App.tsx`** — the topbar's workspace `<select>` and language
`<select>` are replaced by one `.user-menu`: an `.avatar-trigger` button (the tenant's or
email's first letter, on the accent color) that opens `.user-menu-panel`, a popover
carrying the tenant name, the user's email, a workspace-switch list (only rendered when
there is more than one workspace to switch to), and sign-out. The panel closes on an
outside pointerdown, on Escape, or after a menu action — a native `<select>` gets this for
free from the platform; a custom popover has to implement it.

**`services/web/src/i18n/index.ts`** — language is now `const ACTIVE_LANGUAGE = "fa"` at
init time, not `localStorage.getItem("language") ?? "en"`. The `languageChanged` listener
that persisted a user's runtime choice is removed — there is no longer a control that could
fire it. `en.json` stays loaded, `fallbackLng` only, for any key not yet translated.

**`services/web/src/features/tenancy/CreateWorkspacePage.tsx`** — the tenant-creation
payload's `language` field, previously `i18n.language === "fa" ? "fa" : "en"`, is now the
literal `"fa"` — the ternary was reading a value that can now only ever be `"fa"`.

**`services/web/src/i18n/fa.json`** — `auth.registerTitle` changed from
`"ساخت حساب کاربری"` to `"ثبت‌نام در کدجی‌پی‌تی"`. It was byte-identical to
`auth.register` (the button beside it) — invisible in English, where `registerTitle`
("Create an account") and `register` ("Create account") happen to differ, but a real
duplicate-text UX problem once Persian is the only thing rendered, and one this task's own
e2e pass needed distinct text to tell apart. `workspace.none` (the select's empty-state
`<option>`) is deleted from both locale files — nothing renders an empty option anymore.

**`services/web/src/styles.css`** — `.topbar select` rules removed (no select left in the
topbar; `ReviewsPage`'s rule-set picker still uses the base `select` styling from T-0071,
untouched). New rules for `.user-menu`, `.avatar-trigger`, `.avatar`, `.user-menu-panel`,
`.user-menu-header`, `.user-menu-section`, `.user-menu-label`, and
`.user-menu-signout` — all built from the same token set T-0070/T-0071 established, no new
color or spacing values invented.

**Bug found and fixed in the same pass:** `App` never unmounts across a sign-out on the
same tab (`session-isolation.spec.ts` exercises exactly this — sign out, register a
different account, same tab, no reload). `menuOpen` state is component-local, so it
survived the sign-out; the outside-click handler couldn't catch it either, because its
`menuRef.current` guard is null while the panel isn't rendered (signed out). The next
person's first click on their own avatar then read as a toggle-closed of a menu they never
opened. Fixed with `useEffect(() => { if (!user) setMenuOpen(false); }, [user])`.

**What explicitly does not change**

- `ReviewsPage`'s rule-set `<select>` — a real multi-option picker, not the pattern the
  product owner rejected.
- The tenancy API (`TenantViewSet`, `MembershipViewSet`) — this task is frontend-only.
- `--pass`/`--fail`/`--indeterminate` and every other T-0070/T-0071 token — untouched.

## How to prove it ran

`make web-verify`, then the full Playwright e2e suite against the rebuilt real compose
stack (`docker compose -f deploy/compose.yaml up --build -d web`) — every spec drives the
account menu through the real browser, not just the new component in isolation.

## Evidence

### `make web-verify`

```
$ make web-verify
pnpm run lint       -> clean
pnpm run typecheck  -> clean
pnpm run build:
  dist/assets/index-BH1Ilh70.css   10.67 kB
  dist/assets/index-CwtPOops.js   315.96 kB
  ✓ built in 1.89s
```

### Real path — full e2e suite, rebuilt container

```
$ docker compose -f deploy/compose.yaml up --build -d web
$ npx playwright test --project=chromium --reporter=list --workers=1
PASS (6) FAIL (0)
Time: 38033ms
```

All six specs (`onboarding`, `report`, `report-recovery`, `session-isolation` ×2,
`upload-limit`) were themselves rewritten as part of this task: every locator that used to
target `#workspace`/`select#workspace` or English UI copy (`"Sign in"`, `"Create
workspace"`, `"CADGPT"`, the language `<select>`, …) now targets `.avatar-trigger` /
`.user-menu-header strong` and the Persian strings the hardcoded UI actually renders. Text
that is genuinely server-authored per-tenant (`report.disclosure_text`, `reason_label`,
`requirement_text`, IDS specification names) was left untouched — those fixtures seed
`language: "en"` through the API directly (`fixtures.ts`), independent of the frontend's
now-fixed language, and still render in English exactly as before.

`upload-limit.spec.ts` previously proved the size-limit hint rendered correctly in *both*
locales by flipping the (now-removed) language select mid-test; it now proves the single
remaining locale, dropping the flip.

The `session-isolation.spec.ts` failure the `App`-unmount bug produced, and the green rerun
after the fix, are both reproduced in this session's own transcript, not just asserted
here.

### Manual screenshot, menu open

Ad-hoc Playwright script (not committed, not part of the suite) signed in, opened the
menu, and screenshotted it: avatar circle (accent-colored, tenant initial) top-left,
`.user-menu-panel` beneath it showing tenant name, email, and a red "خروج" (sign out) —
matches the design described in the request and the existing dark-navy/orange identity
from T-0070/T-0071.

### Wiring

- `services/web/src/app/App.tsx`: `.user-menu` / `.avatar-trigger` / `.user-menu-panel`
  replace both `<select>` elements in the topbar's JSX tree.
- `services/web/src/i18n/index.ts`: `lng: ACTIVE_LANGUAGE` (`"fa"`), no
  `i18n.on("languageChanged", ...)` listener registered anywhere in the app.
- `services/web/src/styles.css`: `.avatar-trigger`, `.avatar`, `.user-menu-panel` rules
  present; `.topbar select` rule deleted.

### NOT DONE

Nothing from this task's own scope. Multi-language support is not deleted from the
codebase (`en.json`/`fa.json` both still exist, `fallbackLng` still points at `en`) — only
the runtime switch is gone, per the product owner's explicit call that they may revisit
multi-language later as a build-time decision, not a per-user one.

## Review

Not gated — touches no invariant, frontend-only, verified directly by the coordinator
against the real rebuilt stack and the full e2e suite rather than delegated to a fresh
reviewer.
