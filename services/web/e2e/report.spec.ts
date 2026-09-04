/**
 * The evidence instrument every later Phase 3 task uses -- rewritten for T-0074's
 * project/review/review-detail split (Django admin's shape: a changelist, an add form, a
 * detail view, one level deep for projects and again for reviews).
 *
 * Everything from sign-in onward happens through the browser against the real compose
 * stack (`make up`): sign in, create a project, create a review inside it (model file
 * only -- rule-set upload is gone from the UI per `docs/decisions.md`'s 2026-09-04
 * entry), pick a catalogue pack on the review's own detail page, run the check, open the
 * report, and read the three-valued counts and the reasons off the rendered DOM.
 *
 * The catalogue pack used here ("Accessible door width", jurisdiction "sample") is
 * `RulePackService.seed`'s own dev fixture -- `packages/engine/tests/fixtures/
 * door_width.ids` -- loaded by `python manage.py seed_rule_packs` (idempotent; the task
 * file's Evidence section shows it run against the real stack before this suite). It is
 * the same fixture Phase 2 ran end to end and `report.spec.ts` has always asserted
 * against: three doors, one 1000mm (PASS against a 900mm minimum), one 800mm (FAIL,
 * ATTRIBUTE_VALUE_MISMATCH), one with no width recorded at all (INDETERMINATE,
 * ATTRIBUTE_EMPTY).
 *
 * Only account and tenant creation are seeded through the API first (see fixtures.ts),
 * because the SPA has no screen for either.
 */

import path from "node:path";
import { fileURLToPath } from "node:url";

import { expect, test } from "./fixtures";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const FIXTURES_DIR = path.resolve(__dirname, "../../../packages/engine/tests/fixtures");
const IFC_FILE = path.join(FIXTURES_DIR, "three_doors.ifc");

test("a real check run reproduces 1 pass / 1 fail / 1 indeterminate in the browser", async ({
  page,
  account,
}) => {
  await page.goto("/");

  await page.getByLabel("رایانامه").fill(account.email);
  await page.getByLabel("گذرواژه").fill(account.password);
  await page.getByRole("button", { name: "ورود" }).click();

  // The seeded tenant is the user's only one, so App auto-selects it. Everything after
  // this needs the X-Tenant header the selection sets, so wait for it explicitly rather
  // than racing the mutation below against that effect.
  await expect(page.locator(".avatar-trigger")).toBeVisible({ timeout: 15_000 });
  await page.locator(".avatar-trigger").click();
  await expect(page.locator(".user-menu-header strong")).toHaveText(account.tenantName);
  await page.keyboard.press("Escape");

  // "/" redirects to "/projects" -- the changelist, T-0074's outermost level.
  await expect(page.getByRole("heading", { name: "پروژه‌ها" })).toBeVisible();

  const projectName = `three-doors-project-${Date.now()}`;
  await page.getByRole("link", { name: "افزودن پروژه" }).click();
  await page.getByLabel("نام").fill(projectName);
  await page.getByRole("button", { name: "ایجاد پروژه" }).click();

  // "save and continue editing": lands on the new project's own detail page.
  await expect(page.getByRole("heading", { name: projectName })).toBeVisible({ timeout: 10_000 });
  await expect(page.getByText("هنوز بررسی‌ای نیست")).toBeVisible();

  const reviewName = `three-doors-${Date.now()}`;
  await page.getByRole("link", { name: "افزودن بررسی" }).click();
  await expect(page.getByRole("heading", { name: "افزودن بررسی" })).toBeVisible();
  await page.getByLabel("نام").fill(reviewName);
  await page.locator('input[type="file"]').setInputFiles(IFC_FILE);
  await page.getByRole("button", { name: "ایجاد بررسی" }).click();

  // Lands on the new review's own detail page -- the heading is the review's name.
  await expect(page.getByRole("heading", { name: reviewName })).toBeVisible({ timeout: 10_000 });
  await expect(page.locator(".ltr", { hasText: "three_doors.ifc" })).toBeVisible();

  // The catalogue picker: this review has no `rule_set` of its own (upload is gone from
  // the UI), so every check against it selects packs here, per run.
  const picker = page.getByTestId("catalogue-picker");
  await expect(picker).toBeVisible();
  const doorWidthPack = picker
    .locator("li", { hasText: "Accessible door width" })
    .filter({ hasText: "v0.1" });
  await expect(doorWidthPack).toBeVisible({ timeout: 10_000 });
  await doorWidthPack.getByRole("checkbox").check();
  await picker.getByRole("button", { name: "اجرای بررسی با بسته‌های انتخاب‌شده" }).click();

  // The page polls the run itself, and opens it automatically once queued -- wait for
  // the report to render rather than sleeping a fixed interval.
  const report = page.locator("section.report");
  await expect(report).toBeVisible({ timeout: 30_000 });

  // T-0029: the I7 disclosure -- what was checked (the model, by the filename the
  // architect uploaded) and what was not (the drawing set) -- reads before coverage.
  const disclosure = report.locator('[data-testid="disclosure"]');
  await expect(disclosure).toBeVisible();
  await expect(disclosure).toContainText("three_doors.ifc");
  await expect(disclosure).toContainText("not the drawing set");

  const disclosureThenCoverage = report.locator('[data-testid="disclosure"], [data-testid="coverage"]');
  await expect(disclosureThenCoverage.first()).toHaveAttribute("data-testid", "disclosure");

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
  const requirementText = report.locator('[data-testid="requirement-text"]');
  await expect(requirementText).not.toContainText("object at 0x");

  // T-0027: the primary line is now the structured citation, rendered through gettext --
  // "at least 900" from operator/value data, never ifctester's own dict-repr sentence.
  await expect(requirementText).toHaveText("The OverallWidth shall be at least 900.");
  await expect(requirementText).not.toContainText("minInclusive");

  // T-0027: the subject line -- what the rule applies to.
  const applicability = report.locator('[data-testid="applicability"]').first();
  await expect(applicability).toHaveText("All IFCDOOR data");

  // T-0025.1: coverage is presented before findings -- assert document order.
  const coverageThenSpec = report.locator('[data-testid="coverage"], li.spec');
  await expect(coverageThenSpec.first()).toHaveAttribute("data-testid", "coverage");

  // T-0025.2: severity ordering. FAIL sorts before INDETERMINATE, in the DOM, never the
  // reverse.
  const entityRows = report.locator('[data-testid="entity-row"]');
  await expect(entityRows).toHaveCount(2);
  await expect(entityRows.nth(0)).toHaveAttribute("data-status", "FAIL");
  await expect(entityRows.nth(1)).toHaveAttribute("data-status", "INDETERMINATE");

  // T-0074: the disclosure paragraph gets its own bordered callout, not bare text --
  // `.disclosure` carries a visible inline-start border in the current design system.
  const disclosureBorder = await disclosure.evaluate(
    (el) => getComputedStyle(el).borderInlineStartWidth,
  );
  expect(disclosureBorder).toBe("3px");

  // T-0051: the report file (T-0032) is generated by a second, separately-dispatched
  // task -- `useCheckRun`'s polling keeps going past the run's own "succeeded" until it
  // shows up, so this waits for it rather than asserting immediately.
  const downloadButton = page.getByTestId("report-file-link");
  await expect(downloadButton).toBeVisible({ timeout: 15_000 });
  await expect(page.getByTestId("report-file-pending")).toHaveCount(0);
  await expect(page.getByTestId("report-file-failed")).toHaveCount(0);

  // Screenshot of the unfiltered report, before the filter control below changes the DOM.
  await page.screenshot({
    path: path.resolve(__dirname, "screenshots/report.png"),
    fullPage: true,
  });

  // T-0025.3: the status filter. Filtering to FAIL only must not touch the indeterminate
  // count in the summary, and the view must say that rows are being withheld rather than
  // looking identical to the unfiltered report.
  await report.getByRole("checkbox", { name: "نامشخص" }).uncheck();

  await expect(entityRows).toHaveCount(1);
  await expect(entityRows.first()).toHaveAttribute("data-status", "FAIL");

  // The count band is a count of the run, not of the view: it must still read 1, not 0.
  await expect(report.locator(".count--indeterminate .count__value")).toHaveText("1");
  await expect(report.locator(".count--fail .count__value")).toHaveText("1");
  await expect(report.locator(".count--pass .count__value")).toHaveText("1");

  await expect(report.locator('[data-testid="filter-banner"]')).toContainText(
    "نمایش 1 از 2",
  );

  // T-0074: the run appears in this review's own run-history table beneath the picker.
  const runHistory = page.locator("section.card", {
    has: page.getByRole("heading", { name: "تاریخچهٔ اجراها" }),
  });
  await expect(runHistory.locator("tbody tr")).toHaveCount(1);
});
