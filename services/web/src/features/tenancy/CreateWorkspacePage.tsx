/**
 * A signed-in user with zero tenants has nowhere to act -- every tenant-scoped request
 * needs an `X-Tenant` header, and `App.tsx`'s workspace `<select>` has nothing to offer
 * them. This is the screen that replaces that empty dropdown: one name field, calling
 * `POST /v1/tenants/` through `TenantCreateSerializer`.
 *
 * `TenantCreateSerializer` requires a `slug` field; nothing downstream depends on its
 * shape beyond `SlugField`'s own validation (lowercase letters, digits, single hyphens,
 * `unique=True` globally), so it is derived here instead of asking a brand-new user for a
 * second field they have no reason to think about yet. A random suffix is appended
 * because tenant names are not unique (two firms can both be called "Acme") and the slug
 * is -- a collision would otherwise surface as an opaque validation error on first use of
 * the product.
 */

import { useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";

import { ApiError } from "@/api/client";
import { useCreateTenant } from "@/api/queries";
import { useSession } from "@/app/session-context";

function slugify(name: string): string {
  const suffix = Math.random().toString(36).slice(2, 8);
  const cleaned = name
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
  const stem = (cleaned || "workspace").slice(0, 63 - suffix.length - 1).replace(/-+$/g, "");
  return `${stem || "workspace"}-${suffix}`;
}

export function CreateWorkspacePage() {
  const { t, i18n } = useTranslation();
  const { chooseTenant } = useSession();
  const createTenant = useCreateTenant();
  const [name, setName] = useState("");
  const [error, setError] = useState<string | null>(null);

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    try {
      const tenant = await createTenant.mutateAsync({
        name,
        slug: slugify(name),
        language: i18n.language === "fa" ? "fa" : "en",
      });
      chooseTenant(tenant);
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : t("error.generic"));
    }
  }

  return (
    <main className="centered">
      <form className="card" onSubmit={onSubmit}>
        <h1>{t("workspace.createTitle")}</h1>
        <p className="muted">{t("workspace.createHint")}</p>

        <div className="field">
          <label htmlFor="workspace-name">{t("workspace.name")}</label>
          <input
            id="workspace-name"
            required
            value={name}
            onChange={(event) => setName(event.target.value)}
          />
        </div>

        {error && <p className="error">{error}</p>}

        <button type="submit" disabled={createTenant.isPending}>
          {createTenant.isPending ? t("workspace.creating") : t("workspace.create")}
        </button>
      </form>
    </main>
  );
}
