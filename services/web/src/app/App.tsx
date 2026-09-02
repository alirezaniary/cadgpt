import { useEffect } from "react";
import { useTranslation } from "react-i18next";

import { useTenants } from "@/api/queries";
import { LAST_TENANT_KEY, useSession } from "@/app/session-context";
import { SignInPage } from "@/features/auth/SignInPage";
import { ReviewsPage } from "@/features/review/ReviewsPage";

export function App() {
  const { t, i18n } = useTranslation();
  const { user, tenant, ready, signOut, chooseTenant } = useSession();
  const tenants = useTenants(Boolean(user));

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
  if (!user) return <SignInPage />;

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
