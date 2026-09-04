import { Outlet, useNavigate } from "@tanstack/react-router";
import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";

import { useTenants } from "@/api/queries";
import { LAST_TENANT_KEY, useSession } from "@/app/session-context";
import { Breadcrumbs } from "@/components/Breadcrumbs";
import { RegisterPage } from "@/features/auth/RegisterPage";
import { SignInPage } from "@/features/auth/SignInPage";
import { CreateWorkspacePage } from "@/features/tenancy/CreateWorkspacePage";

export function App() {
  const { t } = useTranslation();
  const { user, tenant, ready, signOut, chooseTenant } = useSession();
  const tenants = useTenants(Boolean(user));
  const navigate = useNavigate();
  const [authMode, setAuthMode] = useState<"signIn" | "register">("signIn");
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

  // `App` never unmounts across a sign-out on the same tab -- it only branches its own
  // JSX on `user` -- so `menuOpen` would otherwise survive into the next session and,
  // since the panel isn't rendered while signed out, the outside-click handler below
  // (guarded on `menuRef.current`, which is null with nothing mounted) can never catch
  // it either. The next person's first click on their own avatar would then read as a
  // toggle-closed of a menu they never opened.
  useEffect(() => {
    if (!user) setMenuOpen(false);
  }, [user]);

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

  if (!ready) return <main className="centered" />;
  if (!user) {
    return authMode === "signIn" ? (
      <SignInPage onRegister={() => setAuthMode("register")} />
    ) : (
      <RegisterPage onSignIn={() => setAuthMode("signIn")} />
    );
  }

  // A signed-in user with no chosen tenant yet is either mid-fetch of their tenant list,
  // or genuinely has none. Those must not render the same way: falling through to the
  // shell for the first case renders the account menu with nothing to name yet -- the
  // shell is withheld, the same as `!ready` above, until `tenants.data` has actually
  // arrived and the two cases can be told apart.
  const tenantList = tenants.data;
  if (!tenant && !tenantList) return <main className="centered" />;
  if (!tenant && tenantList && tenantList.results.length === 0) {
    return <CreateWorkspacePage />;
  }

  const initial = (tenant?.name ?? user.email).trim().charAt(0).toUpperCase();

  return (
    <div className="shell">
      <header className="topbar">
        <strong>{t("app.name")}</strong>

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
                  void signOut();
                  // Same reasoning as the workspace-switch handler above: the next
                  // person to sign in on this tab must not inherit a project/review
                  // route scoped to the account that just signed out.
                  void navigate({ to: "/" });
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
