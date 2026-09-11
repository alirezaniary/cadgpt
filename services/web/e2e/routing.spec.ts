/**
 * The address bar is part of the product.
 *
 * The defect this spec exists for: "/" redirected to "/projects" unconditionally, with no
 * auth check at all, while a separate React state machine inside `App` decided what was
 * actually drawn. The two agreed by convention and nothing enforced it, so a signed-out
 * visitor sat at "/projects" looking at a sign-in form, and signing out left the URL on
 * "/projects" -- which reads exactly like a page cached past its logout.
 *
 * Every assertion here is on `page.url()` as much as on what rendered, because a screen
 * that is right at a URL that is wrong is the bug, and only a URL assertion can see it.
 */

import path from "node:path";
import { fileURLToPath } from "node:url";

import type { Page } from "@playwright/test";

import { expect, test } from "./fixtures";

const __dirname = path.dirname(fileURLToPath(import.meta.url));

const SIGN_IN = "ورود";
const SIGN_OUT = "خروج";
const PROJECTS_HEADING = "پروژه‌ها";
const EMAIL_LABEL = "رایانامه";
const PASSWORD_LABEL = "گذرواژه";

/** Signs in through the real form, the way a person does -- no token injection, no
 * storage priming, so whatever the app does with the URL on a real sign-in is what this
 * measures. */
async function signIn(page: Page, email: string, password: string): Promise<void> {
  await page.getByLabel(EMAIL_LABEL).fill(email);
  await page.getByLabel(PASSWORD_LABEL).fill(password);
  await page.getByRole("button", { name: SIGN_IN }).click();
}

test("a signed-out visitor is sent to /login from both / and a deep protected URL", async ({
  page,
}) => {
  // Symptom 1, verbatim from the report: opening the site root redirected to /projects.
  await page.goto("/");
  await expect(page).toHaveURL(/\/login$/);
  await expect(page.getByLabel(EMAIL_LABEL)).toBeVisible();

  // Symptom 2: a protected URL typed straight into the address bar. The old tree had no
  // guard anywhere, so this rendered the sign-in form while the URL still said /projects.
  await page.goto("/projects");
  await expect(page).toHaveURL(/\/login$/);
  await expect(page.getByLabel(EMAIL_LABEL)).toBeVisible();
  await page.screenshot({
    path: path.resolve(__dirname, "screenshots/routing-1b-direct-projects-redirected.png"),
  });

  // A deep route with params, to prove the guard is on the whole subtree and not a
  // special case bolted onto the list page.
  await page.goto("/projects/00000000-0000-0000-0000-000000000000/reviews/new");
  await expect(page).toHaveURL(/\/login$/);

  await page.screenshot({
    path: path.resolve(__dirname, "screenshots/routing-1-signed-out-at-login.png"),
  });
});

test("signing in leaves /login, a hard refresh stays put, and signing out leaves /projects", async ({
  page,
  account,
}) => {
  await page.goto("/");
  await expect(page).toHaveURL(/\/login$/);

  await signIn(page, account.email, account.password);

  // Sign-in itself navigates: the session change re-runs /login's guard, which refuses a
  // signed-in visitor. Nothing in `SignInPage` calls `navigate`.
  await expect(page).toHaveURL(/\/projects$/, { timeout: 15_000 });
  await expect(page.getByRole("heading", { name: PROJECTS_HEADING })).toBeVisible();
  await page.screenshot({
    path: path.resolve(__dirname, "screenshots/routing-2-signed-in-at-projects.png"),
  });

  // A signed-in user cannot sit on a signed-out URL either -- the guard runs both ways.
  await page.goto("/login");
  await expect(page).toHaveURL(/\/projects$/);
  await page.goto("/register");
  await expect(page).toHaveURL(/\/projects$/);

  // The async-session trap: on a hard refresh the router must wait for /v1/auth/refresh/
  // rather than read "not resolved yet" as "signed out". If it ever regresses, this lands
  // on /login. Asserted twice -- once immediately, once after the shell has painted --
  // because a redirect that happens and is then corrected would still end on /projects.
  // Hold `/auth/refresh/` open for 1.5s so the "session not resolved yet" window is wide
  // enough to actually observe. Without this the window is a few milliseconds and every
  // assertion below passes vacuously -- a retrying `toHaveURL` in particular would simply
  // absorb the whole flash and report the corrected URL, which is how an earlier draft of
  // this test "proved" the fix while a deliberately broken build was running underneath it.
  // Only the first call is held, and the handler is never unrouted: tearing a route down
  // while its handler is still sleeping makes the eventual `continue()` throw "Route is
  // already handled", and the access-token refresh can fire more than once per page life.
  let held = false;
  await page.route("**/api/v1/auth/refresh/", async (route) => {
    if (!held) {
      held = true;
      await new Promise((resolve) => setTimeout(resolve, 1500));
    }
    await route.continue();
  });

  await page.reload();

  // Deliberately plain, non-retrying reads, for the same reason `session-isolation.spec.ts`
  // spells its own window check out longhand: a web-first assertion polls until the
  // condition *becomes* true, which it does anyway once the session resolves and the app
  // corrects itself. Only a point-in-time read can catch a state that exists and then goes
  // away. Neither the URL nor the sign-in form may ever show "signed out" in this window.
  for (let i = 0; i < 12; i += 1) {
    expect(page.url(), `URL must never reach /login mid-refresh (iteration ${i})`).not.toMatch(
      /\/login/,
    );
    const signInFields = await page.getByLabel(EMAIL_LABEL).count();
    expect(signInFields, `sign-in form must never render mid-refresh (iteration ${i})`).toBe(0);
    await page.waitForTimeout(100);
  }

  await expect(page.locator(".avatar-trigger")).toBeVisible({ timeout: 15_000 });
  await expect(page).toHaveURL(/\/projects$/);
  await page.screenshot({
    path: path.resolve(__dirname, "screenshots/routing-2b-after-hard-refresh.png"),
  });

  // Symptom 3: signing out left the URL on /projects. It must now say signed out, and,
  // because the guard redirect replaces rather than pushes, the back button must not walk
  // back into the signed-in app.
  await page.locator(".avatar-trigger").click();
  await page.getByRole("menuitem", { name: SIGN_OUT }).click();
  await expect(page).toHaveURL(/\/login$/, { timeout: 15_000 });
  await expect(page.getByLabel(EMAIL_LABEL)).toBeVisible();
  await page.screenshot({
    path: path.resolve(__dirname, "screenshots/routing-3-signed-out-after-signout.png"),
  });

  await page.goBack();
  await expect(page).toHaveURL(/\/login$/);
  await expect(page.getByLabel(EMAIL_LABEL)).toBeVisible();
});
