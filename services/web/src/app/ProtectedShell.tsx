import { Outlet, getRouteApi, useNavigate } from "@tanstack/react-router";
import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";

import { useTenants } from "@/api/queries";
import { LAST_TENANT_KEY, useSession } from "@/app/session-context";
import { Breadcrumbs } from "@/components/Breadcrumbs";
import { CreateWorkspacePage } from "@/features/tenancy/CreateWorkspacePage";

/** The route this component *is*. Addressed by id rather than by importing `appRoute`
 * itself, which would make this module and `router.tsx` circular. What it gives back is
 * what `requireSignedIn` returned: a `User`, already narrowed, not a `User | null`. */
const appRoute = getRouteApi("/_app");

/**
 * The topbar/account-menu chrome around whichever protected route matched.
 *
 * `user` comes from the route context rather than `useSession()`, and it is not nullable:
 * `appRoute`'s `beforeLoad` (`router.tsx`) has already refused to match this subtree
 * without one. The old `App` had to branch on "signed out" itself and could only ever hope
 * the URL agreed with what it chose; this cannot render at a signed-out URL, so it does
 * not ask.
 *
 * It also no longer has to reset `menuOpen` on sign-out. `App` never unmounted across a
 * sign-out -- it only re-branched its own JSX -- so the open menu, and its outside-click
 * handler's now-null ref, leaked into the next session on the same tab. This component
 * lives under `appRoute`, and a cleared session redirects out of that subtree entirely,
 * so it unmounts and takes the state with it.
 */
export function ProtectedShell() {
  const { t } = useTranslation();
  const { user } = appRoute.useRouteContext();
  const { tenant, signOut, chooseTenant } = useSession();
  const tenants = useTenants();
  const navigate = useNavigate();
  const [menuOpen, setMenuOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);

  // Pick a workspace as soon as one is known. A user with exactly one should never have
  // to choose it, and every tenant-scoped request needs one before it can return anything.
  useEffect(() => {
    if (tenant || !tenants.data) return;
    const remembered = localStorage.getItem(LAST_TENANT_KEY);
    const match =
      tenants.data.results.find((candidate) => candidate.slug === remembered) ??
      tenants.data.results[0];
    if (match) chooseTenant(match);
  }, [tenant, tenants.data, chooseTenant]);

  // A native `<select>`'s option list closes itself; this popover has no such platform
  // help, so it needs its own outside-click and Escape handling or it would stay open
  // forever once opened.
  useEffect(() => {
    if (!menuOpen) return;
    function onPointerDown(event: PointerEvent) {
      if (menuRef.current && !menuRef.current.contains(event.target as Node)) {
        setMenuOpen(false);
      }
    }
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") setMenuOpen(false);
    }
    document.addEventListener("pointerdown", onPointerDown);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("pointerdown", onPointerDown);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [menuOpen]);

  // A signed-in user with no chosen tenant yet is either mid-fetch of their tenant list,
  // or genuinely has none. Those must not render the same way: falling through to the
  // shell for the first case renders the account menu with nothing to name yet -- the
  // shell is withheld until `tenants.data` has actually arrived and the two cases can be
  // told apart.
  const tenantList = tenants.data;
  if (!tenant && !tenantList) return <main className="centered" />;
  if (!tenant && tenantList && tenantList.results.length === 0) {
    return <CreateWorkspacePage />;
  }

  const initial = (tenant?.name ?? user.email).trim().charAt(0).toUpperCase();

  return (
    <div className="shell">
      <header className="topbar">
        {/* `alt=""` on purpose: the wordmark beside it is already the accessible name, and
            naming the image too would make a screen reader say the product twice. */}
        <span className="brand-lockup">
          <span className="brand-plaque">
            <img src="/cadgpt-mark.svg" alt="" className="brand-mark" />
          </span>
          <strong>{t("app.name")}</strong>
        </span>

        <div className="spacer" />

        <div className="user-menu" ref={menuRef}>
          <button
            type="button"
            className="avatar-trigger"
            aria-haspopup="menu"
            aria-expanded={menuOpen}
            onClick={() => setMenuOpen((open) => !open)}
          >
            <span className="avatar">{initial}</span>
          </button>

          {menuOpen && (
            <div className="user-menu-panel" role="menu">
              <div className="user-menu-header">
                <strong>{tenant?.name}</strong>
                <span className="muted ltr">{user.email}</span>
              </div>

              {tenantList && tenantList.results.length > 1 && (
                <div className="user-menu-section">
                  <span className="user-menu-label">{t("workspace.label")}</span>
                  {tenantList.results.map((candidate) => (
                    <button
                      key={candidate.uuid}
                      type="button"
                      role="menuitemradio"
                      aria-checked={candidate.slug === tenant?.slug}
                      className={candidate.slug === tenant?.slug ? "active" : ""}
                      onClick={() => {
                        chooseTenant(candidate);
                        setMenuOpen(false);
                        // A project or review uuid in the current URL belongs to the
                        // tenant being left -- carrying it into the new tenant's
                        // session would 404 (T-0074's own e2e run against the real
                        // stack caught this: the stale route rendered a project-detail
                        // page scoped to another tenant's now-inaccessible project).
                        // Unlike sign-out, no guard can catch this one: both tenants
                        // are the same signed-in user, so `requireSignedIn` is still
                        // satisfied and the route stays matched.
                        void navigate({ to: "/projects" });
                      }}
                    >
                      {candidate.name}
                    </button>
                  ))}
                </div>
              )}

              <button
                type="button"
                role="menuitem"
                className="user-menu-signout"
                onClick={() => {
                  // No navigation here on purpose. Clearing the session is itself what
                  // moves the URL: `appRoute`'s guard re-runs, finds no user, and
                  // redirects to `/login` (see `router.tsx`). Navigating by hand as
                  // well would race the state flush -- `/login` would be entered while
                  // `context.auth.user` still held the outgoing user, and its own guard
                  // would bounce it straight back to `/projects`.
                  void signOut();
                }}
              >
                {t("auth.signOut")}
              </button>
            </div>
          )}
        </div>
      </header>

      <Breadcrumbs />
      <Outlet />
    </div>
  );
}
