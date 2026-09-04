/**
 * T-0067 review round 1, both fix-now findings, re-verified live against the real
 * compose stack -- not re-litigating the two MEDIUM findings queued as T-0068/T-0069.
 *
 * 1. HIGH -- `signOut` cleared the user, the tenant and the access token but never the
 *    TanStack Query cache. Query keys (`keys.tenants`, `keys.ruleSets`, ...) are not
 *    user-scoped, so the next person to sign in on the same tab rendered off the
 *    previous user's cached tenant name and rule sets. Reproduced here exactly as the
 *    reviewer described it: user A signs in, creates a workspace, uploads a rule set,
 *    signs out; user B registers a brand-new account in the *same tab* (no new browser
 *    context -- that would sidestep the cache entirely and prove nothing) and must see
 *    none of A's data anywhere.
 *
 * 2. MEDIUM, falsified the evidence -- `App.tsx`'s guard fell through to the shell while
 *    `tenants.data` was still `undefined` (the fetch in flight), rendering
 *    `select#workspace` with zero options for that window on every fresh registration --
 *    the exact broken empty dropdown this task exists to remove. Reproduced by holding
 *    the tenant-list GET open for 1.5s after a fresh registration and asserting, for the
 *    whole delay, that no `<select id="workspace">` exists in the DOM at all -- the fixed
 *    code renders a loading screen instead, the same as the existing `!ready` state, not
 *    a shell with an empty control.
 */

import path from "node:path";
import { fileURLToPath } from "node:url";

import { expect, test } from "@playwright/test";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const IDS_FILE = path.join(__dirname, "../../../packages/engine/tests/fixtures/door_width.ids");

function unique(): string {
  return `${Date.now()}-${Math.floor(Math.random() * 1_000_000)}`;
}

test("signing out clears the previous user's cached tenant and rule-set data before the next person signs in on the same tab", async ({
  page,
}) => {
  const a = unique();
  const emailA = `isolation-a-${a}@cadgpt.test`;
  // Deliberately no lexical resemblance to the email local part -- see the note in the
  // second test below on why a too-similar password makes this whole spec pass vacuously.
  const passwordA = "Guarded#2026-HarnessA";
  const tenantA = `Tenant A ${a}`;
  const ruleSetA = `ruleset-a-${a}`;

  // --- User A: register, create a workspace, add a rule set that must not survive
  // into the next session on this tab. ---
  await page.goto("/");
  await page.getByRole("button", { name: "ساخت حساب کاربری" }).click();
  await page.getByLabel("رایانامه").fill(emailA);
  await page.getByLabel("گذرواژه").fill(passwordA);
  await page.getByRole("button", { name: "ساخت حساب کاربری" }).click();

  await expect(page.getByRole("heading", { name: "فضای کاری نخست خود را بسازید" })).toBeVisible({
    timeout: 15_000,
  });
  await page.getByLabel("نام فضای کاری").fill(tenantA);
  await page.getByRole("button", { name: "ایجاد فضای کاری" }).click();

  await expect(page.locator(".avatar-trigger")).toBeVisible({ timeout: 15_000 });
  await page.locator(".avatar-trigger").click();
  await expect(page.locator(".user-menu-header strong")).toHaveText(tenantA);
  await page.keyboard.press("Escape");

  const ruleSetsCard = page.locator("section.card", {
    has: page.getByRole("heading", { name: "مجموعه‌های قواعد" }),
  });
  await ruleSetsCard.getByPlaceholder("نام").fill(ruleSetA);
  // A real file is not the point of this spec -- any file the "IDS file" input accepts
  // proves the point, so the same fixture the other specs use is reused here.
  await ruleSetsCard.locator('input[type="file"]').setInputFiles(IDS_FILE);
  await ruleSetsCard.getByRole("button", { name: "افزودن مجموعه قواعد" }).click();
  await expect(ruleSetsCard.getByText(ruleSetA)).toBeVisible();
  await page.screenshot({
    path: path.resolve(__dirname, "screenshots/isolation-1-user-a-data.png"),
  });

  // --- Sign out. This is the fix under test: it must clear the query cache, not just
  // the session state. Sign-out now lives inside the account menu, not a bare topbar
  // button, so it has to be opened first. ---
  await page.locator(".avatar-trigger").click();
  await page.getByRole("menuitem", { name: "خروج" }).click();
  await expect(page.getByRole("heading", { name: "کدجی‌پی‌تی" })).toBeVisible();
  await expect(page.getByLabel("رایانامه")).toBeVisible();

  // --- User B: a different brand-new account, same tab, same page -- no reload. If the
  // query cache survived sign-out, B would render A's tenant name in the (stale, from
  // cache) workspace list and/or A's rule set in a (stale) rule-sets list. ---
  const b = unique();
  const emailB = `isolation-b-${b}@cadgpt.test`;
  const passwordB = "Guarded#2026-HarnessB";
  const tenantB = `Tenant B ${b}`;

  await page.getByRole("button", { name: "ساخت حساب کاربری" }).click();
  await page.getByLabel("رایانامه").fill(emailB);
  await page.getByLabel("گذرواژه").fill(passwordB);
  await page.getByRole("button", { name: "ساخت حساب کاربری" }).click();

  // B has zero tenants -- must land on the first-workspace screen, not a shell carrying
  // A's tenant selection from a stale cache.
  await expect(page.getByRole("heading", { name: "فضای کاری نخست خود را بسازید" })).toBeVisible({
    timeout: 15_000,
  });
  await page.getByLabel("نام فضای کاری").fill(tenantB);
  await page.getByRole("button", { name: "ایجاد فضای کاری" }).click();

  await expect(page.locator(".avatar-trigger")).toBeVisible({ timeout: 15_000 });
  // The account menu must show B's tenant, and only B's -- not A's, cached or otherwise.
  await page.locator(".avatar-trigger").click();
  await expect(page.locator(".user-menu-header strong")).toHaveText(tenantB);
  await expect(page.getByText(tenantA)).toHaveCount(0);
  await page.keyboard.press("Escape");

  // The rule-sets list must be B's (empty), not a stale render of A's list.
  await expect(page.getByText(ruleSetA)).toHaveCount(0);
  const emptyState = page.getByText(
    "هنوز بررسی‌ای نیست. برای شروع یک مدل و یک مجموعه قواعد بارگذاری کنید.",
  );
  await expect(emptyState).toBeVisible();
  await page.screenshot({
    path: path.resolve(__dirname, "screenshots/isolation-2-user-b-clean-slate.png"),
  });
});

test("the workspace dropdown never renders with zero options while the tenant list is still loading", async ({
  page,
}) => {
  const u = unique();
  // Deliberately no lexical resemblance between the local part and the password --
  // Django's `UserAttributeSimilarityValidator` (`AUTH_PASSWORD_VALIDATORS`,
  // `services/api/cadgpt/config/settings/base.py`) rejects a password too similar to the
  // account's own email, which an early draft of this spec tripped over silently: the
  // register call 400'd, `user` never became truthy, and every assertion below passed
  // vacuously because the app never left `RegisterPage` -- a false green that "proved"
  // this fix regardless of whether the guard it targets was even present. The explicit
  // registration-succeeded assertion right after submit exists so that failure mode is
  // loud, not silent, if it is ever reintroduced.
  const email = `flash-check-${u}@cadgpt.test`;
  const password = "Guarded#2026-Harness";
  const tenantName = `No Flash Tenant ${u}`;

  // Hold the tenant-list GET open for 1.5s after registration -- long enough for a human
  // eye, and Playwright's polling, to catch a shell rendered underneath a still-pending
  // fetch, if the guard regressed.
  let delayed = false;
  await page.route("**/api/v1/tenants/", async (route) => {
    if (route.request().method() === "GET" && !delayed) {
      delayed = true;
      await new Promise((resolve) => setTimeout(resolve, 1500));
    }
    await route.continue();
  });

  await page.goto("/");
  await page.getByRole("button", { name: "ساخت حساب کاربری" }).click();
  await page.getByLabel("رایانامه").fill(email);
  await page.getByLabel("گذرواژه").fill(password);
  await page.getByRole("button", { name: "ساخت حساب کاربری" }).click();

  // Registration must actually have succeeded before the loop below means anything --
  // otherwise an absent `select#workspace` proves nothing (see the comment above).
  await expect(page.getByText("ثبت‌نام در کدجی‌پی‌تی", { exact: true })).toHaveCount(0, {
    timeout: 10_000,
  });
  await expect(page.locator(".error")).toHaveCount(0);

  // Immediately after registration's `signIn` resolves, the tenant list fetch is in
  // flight (delayed 1.5s above). For that entire window there must be no account-menu
  // avatar in the DOM at all -- the original bug rendered a `<select id="workspace">`
  // with zero `<option>` children during exactly this window, and this asserts against
  // the same class of gap surfacing again on whatever control replaced it.
  //
  // Deliberately `expect(await locator.count()).toBe(0)`, never `expect(locator).
  // toHaveCount(0)`: the latter is a retrying web-first assertion, and it would still
  // pass here even with the bug reproduced -- it polls until the count *becomes* 0,
  // which it eventually does regardless, once the delayed fetch resolves and the app
  // moves on to `CreateWorkspacePage` (which also renders no avatar). That retry
  // silently walks straight past the buggy intermediate window this test exists to
  // catch. `.count()` is a plain, non-retrying read of the DOM at the instant it is
  // called, which is what a point-in-time "never during this window" check needs.
  for (let i = 0; i < 5; i += 1) {
    const count = await page.locator(".avatar-trigger").count();
    expect(count, `.avatar-trigger must not exist while the tenant list is still loading (iteration ${i})`).toBe(0);
    await page.waitForTimeout(200);
  }

  // Once the delayed fetch resolves, the real branch (zero tenants) takes over and the
  // first-workspace screen appears -- proving the loading window was a loading window,
  // not a stuck state.
  await expect(page.getByRole("heading", { name: "فضای کاری نخست خود را بسازید" })).toBeVisible({
    timeout: 15_000,
  });
  await page.getByLabel("نام فضای کاری").fill(tenantName);
  await page.getByRole("button", { name: "ایجاد فضای کاری" }).click();
  await expect(page.locator(".avatar-trigger")).toBeVisible({ timeout: 15_000 });
  await page.locator(".avatar-trigger").click();
  await expect(page.locator(".user-menu-header strong")).toHaveText(tenantName);
});
