/**
 * T-0067: the path a person with no account and no invitation has to take to use the
 * product at all -- register, land on a first-workspace screen (not a broken empty
 * dropdown), create a workspace by typing a name, and reach the changelist able to start
 * a review. Extended by T-0074 to walk every one of the five routes the project/review
 * split introduced -- a list, an add form and a detail view for projects, and again for
 * reviews -- screenshotting each.
 *
 * Deliberately does not use `fixtures.ts`'s `account` fixture: that fixture seeds the
 * account and the tenant straight through the API specifically because, until T-0067,
 * the SPA had no screen for either. This spec is the one that drives both through the
 * browser instead, against the real compose stack (`make up`), the same way
 * `report.spec.ts` drives everything after sign-in.
 */

import path from "node:path";
import { fileURLToPath } from "node:url";

import { expect, test } from "@playwright/test";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const FIXTURES_DIR = path.resolve(__dirname, "../../../packages/engine/tests/fixtures");
const IFC_FILE = path.join(FIXTURES_DIR, "three_doors.ifc");

test("a brand-new person registers, creates a workspace and walks every project/review route, entirely in the browser", async ({
  page,
}) => {
  const unique = `${Date.now()}-${Math.floor(Math.random() * 1_000_000)}`;
  const email = `onboarding-${unique}@cadgpt.test`;
  const password = "Onboard!2026-e2e";
  const workspaceName = `Onboarding Workspace ${unique}`;

  await page.goto("/");

  // Step 1: the sign-in screen is the only thing an unauthenticated visitor sees, and it
  // must offer a way to a registration screen.
  await expect(page.getByRole("heading", { name: "کدجی‌پی‌تی" })).toBeVisible();
  await page.getByRole("button", { name: "ساخت حساب کاربری" }).click();

  // Step 2: the registration screen. Email and password only.
  await expect(page.getByText("ثبت‌نام در کدجی‌پی‌تی", { exact: true })).toBeVisible();
  await page.getByLabel("رایانامه").fill(email);
  await page.getByLabel("گذرواژه").fill(password);
  await page.screenshot({
    path: path.resolve(__dirname, "screenshots/onboarding-1-register.png"),
  });
  await page.getByRole("button", { name: "ساخت حساب کاربری" }).click();

  // Step 3: registration signs the new user in and, because they have zero tenants,
  // they land on the first-workspace screen.
  await expect(page.getByRole("heading", { name: "فضای کاری نخست خود را بسازید" })).toBeVisible({
    timeout: 15_000,
  });
  await expect(page.locator(".avatar-trigger")).toHaveCount(0);
  await page.screenshot({
    path: path.resolve(__dirname, "screenshots/onboarding-2-first-workspace.png"),
  });

  // Step 4: create the workspace by typing a name -- no slug field, one input.
  await page.getByLabel("نام فضای کاری").fill(workspaceName);
  await page.getByRole("button", { name: "ایجاد فضای کاری" }).click();

  // Step 5: the shell renders immediately, with no reload, the new workspace is already
  // selected, and "/" redirects to "/projects" -- route 1 of 5.
  await expect(page.locator(".avatar-trigger")).toBeVisible({ timeout: 15_000 });
  await expect(page.getByRole("heading", { name: "پروژه‌ها" })).toBeVisible();
  await page.locator(".avatar-trigger").click();
  await expect(page.locator(".user-menu-header strong")).toHaveText(workspaceName);
  await page.keyboard.press("Escape");
  await expect(page.getByText("هنوز پروژه‌ای نیست")).toBeVisible();
  await page.screenshot({
    path: path.resolve(__dirname, "screenshots/onboarding-3-projects-list.png"),
  });

  // Route 2 of 5: /projects/new, the add-project form.
  await page.getByRole("link", { name: "افزودن پروژه" }).click();
  await expect(page.getByRole("heading", { name: "افزودن پروژه" })).toBeVisible();
  const projectName = `onboarding-project-${unique}`;
  await page.getByLabel("نام").fill(projectName);
  await page.screenshot({
    path: path.resolve(__dirname, "screenshots/onboarding-4-project-add.png"),
  });
  await page.getByRole("button", { name: "ایجاد پروژه" }).click();

  // Route 3 of 5: /projects/:uuid, the project's own detail page -- "save and continue
  // editing" landed here, not back on the list.
  await expect(page.getByRole("heading", { name: projectName })).toBeVisible({ timeout: 10_000 });
  await expect(page.getByText("هنوز بررسی‌ای نیست")).toBeVisible();
  await page.screenshot({
    path: path.resolve(__dirname, "screenshots/onboarding-5-project-detail.png"),
  });

  // Route 4 of 5: /projects/:uuid/reviews/new -- name and model file only, no rule-set
  // picker (`docs/decisions.md`, 2026-09-04).
  await page.getByRole("link", { name: "افزودن بررسی" }).click();
  await expect(page.getByRole("heading", { name: "افزودن بررسی" })).toBeVisible();
  const reviewName = `onboarding-review-${unique}`;
  await page.getByLabel("نام").fill(reviewName);
  await page.locator('input[type="file"]').setInputFiles(IFC_FILE);
  await page.screenshot({
    path: path.resolve(__dirname, "screenshots/onboarding-6-review-add.png"),
  });
  await page.getByRole("button", { name: "ایجاد بررسی" }).click();

  // Route 5 of 5: /projects/:uuid/reviews/:uuid -- the review's own detail page: the
  // catalogue picker, "run check", the run history and the report, all inline here.
  await expect(page.getByRole("heading", { name: reviewName })).toBeVisible({ timeout: 10_000 });
  const picker = page.getByTestId("catalogue-picker");
  await expect(picker).toBeVisible();
  const doorWidthPack = picker
    .locator("li", { hasText: "Accessible door width" })
    .filter({ hasText: "v0.1" });
  await expect(doorWidthPack).toBeVisible({ timeout: 10_000 });
  await doorWidthPack.getByRole("checkbox").check();
  await picker.getByRole("button", { name: "اجرای بررسی با بسته‌های انتخاب‌شده" }).click();

  const report = page.locator("section.report");
  await expect(report).toBeVisible({ timeout: 30_000 });
  await expect(report.locator(".count--pass .count__value")).toHaveText("1");
  await expect(report.locator(".count--fail .count__value")).toHaveText("1");
  await expect(report.locator(".count--indeterminate .count__value")).toHaveText("1");

  await page.screenshot({
    path: path.resolve(__dirname, "screenshots/onboarding-7-review-detail-report.png"),
    fullPage: true,
  });
});
