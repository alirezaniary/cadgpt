/**
 * T-0033: the upload ceiling is named before the user picks a file.
 *
 * `ReviewAddPage` (T-0074's split of the old `ReviewsPage`) states
 * `MAX_MODEL_UPLOAD_BYTES` (`src/lib/limits.ts`) next to the model file input itself,
 * before any file is chosen -- this proves that text actually renders in the real
 * browser, in the real built image. Reaching that page now goes through a project first
 * (create one, open its detail page, follow "افزودن بررسی") since the hint no longer
 * lives on a single dashboard.
 *
 * Previously asserted the same hint in both English and Persian by flipping a topbar
 * language `<select>` mid-test. That control is gone -- the frontend now hardcodes a
 * single language (`src/i18n/index.ts`) rather than exposing a per-user switch -- so there
 * is only one locale left to prove this against.
 */

import { expect, test } from "./fixtures";

test("the model size ceiling is stated at upload time", async ({ page, account }) => {
  await page.goto("/");

  await page.getByLabel("رایانامه").fill(account.email);
  await page.getByLabel("گذرواژه").fill(account.password);
  await page.getByRole("button", { name: "ورود" }).click();

  await expect(page.locator(".avatar-trigger")).toBeVisible({ timeout: 15_000 });
  await page.locator(".avatar-trigger").click();
  await expect(page.locator(".user-menu-header strong")).toHaveText(account.tenantName);
  await page.keyboard.press("Escape");

  const projectName = `upload-limit-project-${Date.now()}`;
  await page.getByRole("link", { name: "افزودن پروژه" }).click();
  await page.getByLabel("نام").fill(projectName);
  await page.getByRole("button", { name: "ایجاد پروژه" }).click();
  await expect(page.getByRole("heading", { name: projectName })).toBeVisible({ timeout: 10_000 });

  await page.getByRole("link", { name: "افزودن بررسی" }).click();

  const limitHint = page.getByTestId("model-size-limit");
  await expect(limitHint).toBeVisible();
  await expect(limitHint).toHaveText("حداکثر 126.0 MB برای هر مدل.");
  await expect(page.locator("html")).toHaveAttribute("dir", "rtl");
});
