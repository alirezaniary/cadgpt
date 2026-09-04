import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import { useTenants } from "@/api/queries";
import { LAST_TENANT_KEY, useSession } from "@/app/session-context";
import { RegisterPage } from "@/features/auth/RegisterPage";
import { SignInPage } from "@/features/auth/SignInPage";
import { ReviewsPage } from "@/features/review/ReviewsPage";
import { CreateWorkspacePage } from "@/features/tenancy/CreateWorkspacePage";

export function App() {
  const { t, i18n } = useTranslation();
  const { user, tenant, ready, signOut, chooseTenant } = useSession();
  const tenants = useTenants(Boolean(user));
  const [authMode, setAuthMode] = useState<"signIn" | "register">("signIn");

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
  // shell for the first case renders `select#workspace` with zero options for the
  // fetch's duration -- the exact broken empty dropdown this task exists to remove, on
  // every fresh registration. So the shell is withheld, the same as `!ready` above,
  // until `tenants.data` has actually arrived and the two cases can be told apart.
  const tenantList = tenants.data;
  if (!tenant && !tenantList) return <main className="centered" />;
  if (!tenant && tenantList && tenantList.results.length === 0) {
    return <CreateWorkspacePage />;
  }

  return (
    <div className="shell">
      <header className="topbar">
        <strong>{t("app.name")}</strong>

        <label className="sr-only" htmlFor="workspace">
          {t("workspace.label")}
        </label>
        <select
          id="workspace"
          value={tenant?.slug ?? ""}
          onChange={(event) => {
            const next = tenants.data?.results.find(
              (candidate) => candidate.slug === event.target.value,
            );
            chooseTenant(next ?? null);
          }}
        >
          {tenants.data?.results.length === 0 && (
            <option value="">{t("workspace.none")}</option>
          )}
          {tenants.data?.results.map((candidate) => (
            <option key={candidate.uuid} value={candidate.slug}>
              {candidate.name}
            </option>
          ))}
        </select>

        <div className="spacer" />

        <select
          aria-label="language"
          value={i18n.language}
          onChange={(event) => void i18n.changeLanguage(event.target.value)}
        >
          <option value="en">English</option>
          <option value="fa">فارسی</option>
        </select>

        <span className="muted ltr">{user.email}</span>
        <button type="button" onClick={() => void signOut()}>
          {t("auth.signOut")}
        </button>
      </header>

      <ReviewsPage />
    </div>
  );
}
