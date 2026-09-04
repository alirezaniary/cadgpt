/**
 * The way out of a nested route: T-0074's workspace -> projects -> reviews shape shipped
 * with no breadcrumb trail, so a user on a review's detail page (three levels in) had no
 * standard navigation tool back out short of the browser's own back button. Proves the
 * trail renders at each depth and that every link in it actually navigates, against the
 * real compose stack -- not just that the component compiles.
 */

import path from "node:path";
import { fileURLToPath } from "node:url";

import { expect, test } from "./fixtures";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const FIXTURES_DIR = path.resolve(__dirname, "../../../packages/engine/tests/fixtures");
const IFC_FILE = path.join(FIXTURES_DIR, "three_doors.ifc");

test("the breadcrumb trail carries a review three levels deep back out to the changelist", async ({
  page,
  account,
}) => {
  await page.goto("/");
  await page.getByLabel("رایانامه").fill(account.email);
  await page.getByLabel("گذرواژه").fill(account.password);
  await page.getByRole("button", { name: "ورود" }).click();

  await expect(page.getByRole("heading", { name: "پروژه‌ها" })).toBeVisible({ timeout: 15_000 });

  // Nothing renders at the changelist root -- the heading already says "Projects".
  await expect(page.locator("nav.breadcrumbs")).toHaveCount(0);

  const projectName = `breadcrumb-project-${Date.now()}`;
  await page.getByRole("link", { name: "افزودن پروژه" }).click();
  await expect(page.locator("nav.breadcrumbs")).toContainText("پروژه‌ها");
  await expect(page.locator("nav.breadcrumbs")).toContainText("افزودن پروژه");

  await page.getByLabel("نام").fill(projectName);
  await page.getByRole("button", { name: "ایجاد پروژه" }).click();
  await expect(page.getByRole("heading", { name: projectName })).toBeVisible({ timeout: 10_000 });

  // One level in: Projects (link) / {project name} (current).
  const projectCrumb = page.locator("nav.breadcrumbs");
  await expect(projectCrumb).toContainText(projectName);
  await expect(projectCrumb.locator("[aria-current='page']")).toHaveText(projectName);

  const reviewName = `breadcrumb-review-${Date.now()}`;
  await page.getByRole("link", { name: "افزودن بررسی" }).click();
  await expect(page.locator("nav.breadcrumbs")).toContainText(projectName);
  await expect(page.locator("nav.breadcrumbs")).toContainText("افزودن بررسی");

  await page.getByLabel("نام").fill(reviewName);
  await page.locator('input[type="file"]').setInputFiles(IFC_FILE);
  await page.getByRole("button", { name: "ایجاد بررسی" }).click();
  await expect(page.getByRole("heading", { name: reviewName })).toBeVisible({ timeout: 10_000 });

  // Two levels in, the case the report describes: Projects / {project} / {review}, all
  // three present at once, the review as the current, non-clickable crumb.
  const reviewCrumb = page.locator("nav.breadcrumbs");
  await expect(reviewCrumb).toContainText("پروژه‌ها");
  await expect(reviewCrumb).toContainText(projectName);
  await expect(reviewCrumb.locator("[aria-current='page']")).toHaveText(reviewName);

  // The project crumb is a real link back one level, not just a label.
  await reviewCrumb.getByRole("link", { name: projectName }).click();
  await expect(page.getByRole("heading", { name: projectName })).toBeVisible();
  await expect(page).toHaveURL(/\/projects\/[^/]+$/);

  // And the root crumb reaches the changelist from one level in.
  await expect(page.locator("nav.breadcrumbs")).toContainText("پروژه‌ها");
  await page.locator("nav.breadcrumbs").getByRole("link", { name: "پروژه‌ها" }).click();
  await expect(page.getByRole("heading", { name: "پروژه‌ها" })).toBeVisible();
  await expect(page).toHaveURL(/\/projects$/);
});
