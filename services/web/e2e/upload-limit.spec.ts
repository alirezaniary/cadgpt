/**
 * T-0033: the upload ceiling is named before the user picks a file, in both locales.
 *
 * A rejection message read only after a failed upload tells an architect the number too
 * late to act on it. `ReviewsPage` states `MAX_MODEL_UPLOAD_BYTES` (`src/lib/limits.ts`)
 * next to the model file input itself, before any file is chosen -- this proves that text
 * actually renders in the real browser, in the real built image, in English and in the
 * Persian the product's first tenants read.
 */

import { expect, test } from "./fixtures";

test("the model size ceiling is stated at upload time, in English and Persian", async ({
  page,
  account,
}) => {
  await page.goto("/");

  await page.getByLabel("Email").fill(account.email);
  await page.getByLabel("Password").fill(account.password);
  await page.getByRole("button", { name: "Sign in" }).click();

  await expect(page.locator("#workspace")).toHaveValue(account.tenantSlug);

  const limitHint = page.getByTestId("model-size-limit");
  await expect(limitHint).toBeVisible();
  await expect(limitHint).toHaveText("Up to 126.0 MB per model.");

  await page.getByLabel("language").selectOption("fa");
  await expect(limitHint).toHaveText("حداکثر 126.0 MB برای هر مدل.");
  await expect(page.locator("html")).toHaveAttribute("dir", "rtl");
});
