/**
 * T-0067: the path a person with no account and no invitation has to take to use the
 * product at all -- register, land on a first-workspace screen (not a broken empty
 * dropdown), create a workspace by typing a name, and reach `ReviewsPage` able to start a
 * review.
 *
 * Deliberately does not use `fixtures.ts`'s `account` fixture: that fixture seeds the
 * account and the tenant straight through the API specifically because, until this task,
 * the SPA had no screen for either. This spec is the one that now drives both through the
 * browser instead, against the real compose stack (`make up`), the same way
 * `report.spec.ts` drives everything after sign-in.
 */

import path from "node:path";
import { fileURLToPath } from "node:url";

import { expect, test } from "@playwright/test";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const FIXTURES_DIR = path.resolve(__dirname, "../../../packages/engine/tests/fixtures");
const IDS_FILE = path.join(FIXTURES_DIR, "door_width.ids");
const IFC_FILE = path.join(FIXTURES_DIR, "three_doors.ifc");

test("a brand-new person registers, creates a workspace and starts a review, entirely in the browser", async ({
  page,
}) => {
  const unique = `${Date.now()}-${Math.floor(Math.random() * 1_000_000)}`;
  const email = `onboarding-${unique}@cadgpt.test`;
  const password = "Onboard!2026-e2e";
  const workspaceName = `Onboarding Workspace ${unique}`;

  await page.goto("/");

  // Step 1: the sign-in screen is the only thing an unauthenticated visitor sees, and it
  // must offer a way to a registration screen -- that link is this task's first gap.
  await expect(page.getByRole("heading", { name: "CADGPT" })).toBeVisible();
  await page.getByRole("button", { name: "Create account" }).click();

  // Step 2: the registration screen. Email and password only. The heading stays
  // "CADGPT" -- the same card layout as sign-in, just as a subtitle names which screen
  // this is, the way `SignInPage`'s tagline does.
  await expect(page.getByText("Create an account", { exact: true })).toBeVisible();
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill(password);
  await page.screenshot({
    path: path.resolve(__dirname, "screenshots/onboarding-1-register.png"),
  });
  await page.getByRole("button", { name: "Create account" }).click();

  // Step 3: registration signs the new user in (via the same `signIn` path login uses)
  // and, because they have zero tenants, they land on the first-workspace screen -- not
  // the broken empty `<select>` `App.tsx` used to render.
  await expect(page.getByRole("heading", { name: "Create your first workspace" })).toBeVisible({
    timeout: 15_000,
  });
  await expect(page.locator("#workspace")).toHaveCount(0);
  await page.screenshot({
    path: path.resolve(__dirname, "screenshots/onboarding-2-first-workspace.png"),
  });

  // Step 4: create the workspace by typing a name -- no slug field, one input.
  await page.getByLabel("Workspace name").fill(workspaceName);
  await page.getByRole("button", { name: "Create workspace" }).click();

  // Step 5: the shell renders immediately, with no reload, and the new workspace is
  // already selected -- `chooseTenant` was called directly with the create response.
  await expect(page.locator("#workspace")).toBeVisible({ timeout: 15_000 });
  await expect(page.getByRole("heading", { name: "Reviews" })).toBeVisible();
  await expect(page.locator("select#workspace option")).toHaveText([workspaceName]);
  await page.screenshot({
    path: path.resolve(__dirname, "screenshots/onboarding-3-reviews-shell.png"),
  });

  // Step 6: able to start a review -- add a rule set, create a review against it, and run
  // a check to a terminal state, the same real IDS/IFC fixtures `report.spec.ts` uses.
  const ruleSetsCard = page.locator("section.card", {
    has: page.getByRole("heading", { name: "Rule sets" }),
  });
  const reviewsCard = page.locator("section.card", {
    has: page.getByRole("heading", { name: "Reviews" }),
  });

  const ruleSetName = `door-width-${unique}`;
  await ruleSetsCard.getByPlaceholder("Name").fill(ruleSetName);
  await ruleSetsCard.locator('input[type="file"]').setInputFiles(IDS_FILE);
  await ruleSetsCard.getByRole("button", { name: "Add rule set" }).click();
  await expect(ruleSetsCard.getByText(ruleSetName)).toBeVisible();

  const reviewName = `onboarding-review-${unique}`;
  await reviewsCard.getByPlaceholder("Name").fill(reviewName);
  await reviewsCard.locator('select[name="rule_set"]').selectOption({ label: ruleSetName });
  await reviewsCard.locator('input[type="file"]').setInputFiles(IFC_FILE);
  await reviewsCard.getByRole("button", { name: "Create review" }).click();

  const reviewRow = reviewsCard.locator("li.review", { hasText: reviewName });
  await expect(reviewRow).toBeVisible();
  await reviewRow.getByRole("button", { name: "Run check" }).click();

  const summaryButton = reviewRow.getByRole("button", { name: "Summary" });
  await expect(summaryButton).toBeVisible({ timeout: 30_000 });
  await summaryButton.click();

  const report = page.locator("section.report");
  await expect(report).toBeVisible();
  await expect(report.locator(".count--pass .count__value")).toHaveText("1");
  await expect(report.locator(".count--fail .count__value")).toHaveText("1");
  await expect(report.locator(".count--indeterminate .count__value")).toHaveText("1");

  await page.screenshot({
    path: path.resolve(__dirname, "screenshots/onboarding-4-report.png"),
    fullPage: true,
  });
});
