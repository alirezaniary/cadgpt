/**
 * Seeds an account and a tenant through the API, not the browser.
 *
 * The SPA has no registration or tenant-creation screen, and inventing one just to make
 * this harness convenient would be building a product feature for the harness's sake.
 * These three calls go straight to the API container on :8000 -- the seeding is
 * deliberately not routed through the `web` container's nginx proxy on :8080, because
 * the point of the seed step is to put rows in the database before the browser ever
 * opens a page, not to exercise the SPA.
 *
 * A fresh, unique email and tenant slug are generated per run so the harness stays
 * re-runnable against a stack whose volumes were not reset between runs.
 */

import { test as base } from "@playwright/test";

const API_ORIGIN = "http://localhost:8000";

export interface SeededAccount {
  email: string;
  password: string;
  tenantName: string;
  tenantSlug: string;
}

async function apiPost<T>(path: string, body: unknown, token?: string): Promise<T> {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (token) headers.Authorization = `Bearer ${token}`;
  const response = await fetch(`${API_ORIGIN}${path}`, {
    method: "POST",
    headers,
    body: JSON.stringify(body),
  });
  if (!response.ok) {
    const text = await response.text();
    throw new Error(`seeding ${path} returned ${response.status}: ${text}`);
  }
  return (await response.json()) as T;
}

interface Fixtures {
  account: SeededAccount;
}

export const test = base.extend<Fixtures>({
  // Playwright's fixture signature requires destructuring the fixtures object even when
  // this fixture depends on none of them.
  // eslint-disable-next-line no-empty-pattern
  account: async ({}, use) => {
    const unique = `${Date.now()}-${Math.floor(Math.random() * 1_000_000)}`;
    const email = `e2e-${unique}@cadgpt.test`;
    const password = "Harness!2026-e2e";
    const tenantName = `E2E Tenant ${unique}`;
    const tenantSlug = `e2e-${unique}`;

    await apiPost("/api/v1/auth/register/", {
      email,
      password,
      full_name: "E2E Harness",
    });

    const login = await apiPost<{ access: string }>("/api/v1/auth/login/", {
      email,
      password,
    });

    await apiPost(
      "/api/v1/tenants/",
      { name: tenantName, slug: tenantSlug, language: "en" },
      login.access,
    );

    await use({ email, password, tenantName, tenantSlug });
  },
});

export { expect } from "@playwright/test";
