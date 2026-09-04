/**
 * Account creation. Email and password only -- no OTP, no email verification, no
 * password-confirmation field, matching what `RegisterSerializer` accepts and nothing
 * beyond it (`full_name` and `language` both default server-side).
 *
 * Registering does not itself sign anyone in: `POST /v1/auth/register/` returns the new
 * `User`, not a token pair (`RegisterView.post` -- 201 body is `UserSerializer`). Rather
 * than teach `session.tsx` a second way to plant an access token, this calls the existing
 * `useSession().signIn` with the same credentials right after -- one token-handling path,
 * used twice.
 */

import { useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";

import { api, ApiError } from "@/api/client";
import { useSession } from "@/app/session-context";

export function RegisterPage({ onSignIn }: { onSignIn: () => void }) {
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
      await api.post("/v1/auth/register/", { email, password });
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
        <h1>{t("app.name")}</h1>
        <p className="muted">{t("auth.registerTitle")}</p>

        <label htmlFor="register-email">{t("auth.email")}</label>
        <input
          id="register-email"
          type="email"
          className="ltr"
          autoComplete="email"
          required
          value={email}
          onChange={(event) => setEmail(event.target.value)}
        />

        <label htmlFor="register-password">{t("auth.password")}</label>
        <input
          id="register-password"
          type="password"
          className="ltr"
          autoComplete="new-password"
          required
          value={password}
          onChange={(event) => setPassword(event.target.value)}
        />

        {error && <p className="error">{error}</p>}

        <button type="submit" disabled={busy}>
          {busy ? t("auth.registering") : t("auth.register")}
        </button>

        <p className="muted">
          {t("auth.signInPrompt")}{" "}
          <button type="button" className="link-button" onClick={onSignIn}>
            {t("auth.backToSignIn")}
          </button>
        </p>
      </form>
    </main>
  );
}
