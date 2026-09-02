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

// T-0025 fix-now round: the coverage sentence and `establishedNothing()` were both wrong,
// and neither defect was reachable from the fixture above -- it has one specification that
// matches everything. This fixture matches nothing on purpose, against the same IFC:
//   "Door name recorded"       -- applies to the 3 doors, all pass. A real evaluation.
//   "Wall fire rating recorded" -- optional cardinality, matches 0 walls (there are none).
//                                   DOES_NOT_APPLY / INDETERMINATE / NO_SUBJECTS_NOTHING_CHECKED:
//                                   this is the one specification that genuinely established
//                                   nothing.
//   "Wall count required"      -- required cardinality, also matches 0 walls, but an absent
//                                   required element is a real finding, not an absence of
//                                   evidence: APPLIES / FAIL / NO_SUBJECTS_BUT_REQUIRED. It
//                                   must never be named alongside the specification above.
const NOTHING_ESTABLISHED_IDS_FILE = path.join(__dirname, "fixtures", "nothing_established.ids");

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

  // T-0026: the requirement line is the rule in words, from ifctester's own `to_string`,
  // never the CPython object repr `str(facet)` produced before this fix.
  const requirementDescription = report.locator(".requirement__description");
  await expect(requirementDescription).toHaveText(
    "The OverallWidth shall be {'minInclusive': '900'}",
  );
  await expect(requirementDescription).not.toContainText("object at 0x");

  // T-0025.1: coverage is presented before findings — assert document order, not just
  // presence. A coverage line rendered underneath the specification list would satisfy a
  // simple visibility check while failing the actual requirement.
  const coverageThenSpec = report.locator('[data-testid="coverage"], li.spec');
  await expect(coverageThenSpec.first()).toHaveAttribute("data-testid", "coverage");

  // T-0025.2: severity ordering. FAIL sorts before INDETERMINATE, in the DOM, never the
  // reverse — sorting INDETERMINATE last would bury it under a pass-shaped read.
  const entityRows = report.locator('[data-testid="entity-row"]');
  await expect(entityRows).toHaveCount(2);
  await expect(entityRows.nth(0)).toHaveAttribute("data-status", "FAIL");
  await expect(entityRows.nth(1)).toHaveAttribute("data-status", "INDETERMINATE");

  // Screenshot of the unfiltered report, before the filter control below changes the DOM.
  await page.screenshot({
    path: path.resolve(__dirname, "screenshots/report.png"),
    fullPage: true,
  });

  // T-0025.3: the status filter. This is the assertion the reviewer looks for first —
  // filtering to FAIL only must not touch the indeterminate count in the summary, and the
  // view must say that rows are being withheld rather than looking identical to the
  // unfiltered report.
  await report.getByRole("checkbox", { name: "Indeterminate" }).uncheck();

  await expect(entityRows).toHaveCount(1);
  await expect(entityRows.first()).toHaveAttribute("data-status", "FAIL");

  // The count band is a count of the run, not of the view: it must still read 1, not 0.
  await expect(report.locator(".count--indeterminate .count__value")).toHaveText("1");
  await expect(report.locator(".count--fail .count__value")).toHaveText("1");
  await expect(report.locator(".count--pass .count__value")).toHaveText("1");

  await expect(report.locator('[data-testid="filter-banner"]')).toContainText(
    "Showing 1 of 2",
  );

  // T-0025 fix-now: a second rule set that has a specification matching nothing, run
  // against the same model, in the same session -- this is the branch F1 and F2 shipped
  // broken on because nothing in this spec previously reached it.
  const nothingRuleSetName = `nothing-established-${Date.now()}`;
  await ruleSetsCard.getByPlaceholder("Name").fill(nothingRuleSetName);
  await ruleSetsCard.locator('input[type="file"]').setInputFiles(NOTHING_ESTABLISHED_IDS_FILE);
  await ruleSetsCard.getByRole("button", { name: "Add rule set" }).click();
  await expect(ruleSetsCard.getByText(nothingRuleSetName)).toBeVisible();

  const nothingReviewName = `three-doors-nothing-${Date.now()}`;
  await reviewsCard.getByPlaceholder("Name").fill(nothingReviewName);
  await reviewsCard
    .locator('select[name="rule_set"]')
    .selectOption({ label: nothingRuleSetName });
  await reviewsCard.locator('input[type="file"]').setInputFiles(IFC_FILE);
  await reviewsCard.getByRole("button", { name: "Create review" }).click();

  const nothingReviewRow = reviewsCard.locator("li.review", { hasText: nothingReviewName });
  await expect(nothingReviewRow).toBeVisible();
  await nothingReviewRow.getByRole("button", { name: "Run check" }).click();

  const nothingSummaryButton = nothingReviewRow.getByRole("button", { name: "Summary" });
  await expect(nothingSummaryButton).toBeVisible({ timeout: 30_000 });
  await nothingSummaryButton.click();

  // F1: 1 of the 3 specifications established nothing, so the sentence must read "2 of 3",
  // never "3 of 3" -- the bug was that the old numerator was arithmetically identical to
  // the denominator for every report the engine can produce.
  const coverageSentence = report.locator('[data-testid="coverage"] > p').first();
  await expect(coverageSentence).toHaveText(
    "2 of 3 specifications in this rule set were evaluated.",
  );

  // The "established nothing" block names exactly the one specification that matched
  // nothing under optional cardinality -- never the one the engine judged FAIL.
  const nothingEstablishedBlock = report.locator('[data-testid="coverage-nothing-established"]');
  await expect(nothingEstablishedBlock).toBeVisible();
  const nothingEstablishedItems = nothingEstablishedBlock.locator("li");
  await expect(nothingEstablishedItems).toHaveCount(1);
  await expect(nothingEstablishedItems.first()).toHaveText("Wall fire rating recorded");

  // F2: the specification the engine judged FAIL (a required element is absent) is a real
  // finding, not an absence of evidence -- it must not be named here.
  await expect(nothingEstablishedBlock).not.toContainText("Wall count required");

  // That FAIL specification is genuinely rendered as a finding, with its own pill, so F2's
  // fix is not merely hiding the specification -- it appears in the findings list below.
  const wallCountRequiredSpec = report.locator("li.spec", { hasText: "Wall count required" });
  await expect(wallCountRequiredSpec).toBeVisible();
  await expect(wallCountRequiredSpec.locator(".pill--fail")).toHaveText("Fail");
});
