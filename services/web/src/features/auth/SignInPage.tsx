import { Link } from "@tanstack/react-router";
import { useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";

import { ApiError } from "@/api/client";
import { useSession } from "@/app/session-context";

/** Submitting does not navigate. Setting the user is what moves the URL: `/login` sits
 * under a guard that refuses a signed-in visitor, so the session change redirects to
 * `/projects` on its own (`router.tsx`). */
export function SignInPage() {
  const { t } = useTranslation();
  const { signIn } = useSession();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await signIn(email, password);
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : t("error.generic"));
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="centered">
      <form className="card" onSubmit={onSubmit}>
        <img src="/cadgpt-logo.png" alt="" className="brand-mark brand-mark-lg" />
        <h1>{t("app.name")}</h1>
        <p className="muted">{t("app.tagline")}</p>

        <div className="field">
          <label htmlFor="email">{t("auth.email")}</label>
          <input
            id="email"
            type="email"
            className="ltr"
            autoComplete="email"
            required
            value={email}
            onChange={(event) => setEmail(event.target.value)}
          />
        </div>

        <div className="field">
          <label htmlFor="password">{t("auth.password")}</label>
          <input
            id="password"
            type="password"
            className="ltr"
            autoComplete="current-password"
            required
            value={password}
            onChange={(event) => setPassword(event.target.value)}
          />
        </div>

        {error && <p className="error">{error}</p>}

        <button type="submit" disabled={busy}>
          {busy ? t("auth.signingIn") : t("auth.signIn")}
        </button>

        <p className="muted">
          {t("auth.registerPrompt")}{" "}
          <Link to="/register" className="link-button">
            {t("auth.register")}
          </Link>
        </p>
      </form>
    </main>
  );
}
