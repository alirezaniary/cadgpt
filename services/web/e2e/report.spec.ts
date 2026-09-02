/**
 * The evidence instrument every later Phase 3 task uses.
 *
 * Everything from sign-in onward happens through the browser against the real compose
 * stack (`make up`): sign in, upload an IDS rule set, upload an IFC model, run the check,
 * open the report, and read the three-valued counts and the reasons off the rendered DOM.
 * Only account and tenant creation are seeded through the API first (see fixtures.ts),
 * because the SPA has no screen for either.
 *
 * The fixtures are the same ones Phase 2 ran end to end: three doors, one 1000mm (PASS
 * against a 900mm minimum), one 800mm (FAIL, ATTRIBUTE_VALUE_MISMATCH), one with no width
 * recorded at all (INDETERMINATE, ATTRIBUTE_EMPTY). This spec is correct when it
 * reproduces that from the browser.
 */

import path from "node:path";
import { fileURLToPath } from "node:url";

import { expect, test } from "./fixtures";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const FIXTURES_DIR = path.resolve(__dirname, "../../../packages/engine/tests/fixtures");
const IDS_FILE = path.join(FIXTURES_DIR, "door_width.ids");
const IFC_FILE = path.join(FIXTURES_DIR, "three_doors.ifc");

test("a real check run reproduces 1 pass / 1 fail / 1 indeterminate in the browser", async ({
  page,
  account,
}) => {
  await page.goto("/");

  await page.getByLabel("Email").fill(account.email);
  await page.getByLabel("Password").fill(account.password);
  await page.getByRole("button", { name: "Sign in" }).click();

  // The seeded tenant is the user's only one, so App auto-selects it. Everything after
  // this needs the X-Tenant header the selection sets, so wait for it explicitly rather
  // than racing the mutation below against that effect.
  await expect(page.locator("#workspace")).toHaveValue(account.tenantSlug);

  const ruleSetsCard = page.locator("section.card", {
    has: page.getByRole("heading", { name: "Rule sets" }),
  });
  const reviewsCard = page.locator("section.card", {
    has: page.getByRole("heading", { name: "Reviews" }),
  });

  const ruleSetName = `door-width-${Date.now()}`;
  await ruleSetsCard.getByPlaceholder("Name").fill(ruleSetName);
  await ruleSetsCard.locator('input[type="file"]').setInputFiles(IDS_FILE);
  await ruleSetsCard.getByRole("button", { name: "Add rule set" }).click();
  await expect(ruleSetsCard.getByText(ruleSetName)).toBeVisible();

  const reviewName = `three-doors-${Date.now()}`;
  await reviewsCard.getByPlaceholder("Name").fill(reviewName);
  await reviewsCard.locator('select[name="rule_set"]').selectOption({ label: ruleSetName });
  await reviewsCard.locator('input[type="file"]').setInputFiles(IFC_FILE);
  await reviewsCard.getByRole("button", { name: "Create review" }).click();

  const reviewRow = reviewsCard.locator("li.review", { hasText: reviewName });
  await expect(reviewRow).toBeVisible();
  await reviewRow.getByRole("button", { name: "Run check" }).click();

  // The page polls the run itself; wait for it to reach a terminal state rather than
  // sleeping a fixed interval.
  const summaryButton = reviewRow.getByRole("button", { name: "Summary" });
  await expect(summaryButton).toBeVisible({ timeout: 30_000 });
  await summaryButton.click();

  const report = page.locator("section.report");
  await expect(report).toBeVisible();

  await expect(report.locator(".count--pass .count__value")).toHaveText("1");
  await expect(report.locator(".count--fail .count__value")).toHaveText("1");
  await expect(report.locator(".count--indeterminate .count__value")).toHaveText("1");

  const failRow = report.locator('[data-testid="entity-row"][data-status="FAIL"]');
  await expect(failRow).toHaveCount(1);
  await expect(failRow.locator('[data-testid="reason"]')).toHaveAttribute(
    "data-reason-code",
    "ATTRIBUTE_VALUE_MISMATCH",
  );
  await expect(failRow.locator('[data-testid="detail"]')).toContainText("800");

  const indeterminateRow = report.locator(
    '[data-testid="entity-row"][data-status="INDETERMINATE"]',
  );
  await expect(indeterminateRow).toHaveCount(1);
  await expect(indeterminateRow.locator('[data-testid="reason"]')).toHaveAttribute(
    "data-reason-code",
    "ATTRIBUTE_EMPTY",
  );

  await page.screenshot({
    path: path.resolve(__dirname, "screenshots/report.png"),
    fullPage: true,
  });
});
