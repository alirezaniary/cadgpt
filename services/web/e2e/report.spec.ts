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

  // T-0034: three_doors.ifc has 2 non-passing findings, nowhere near
  // `DEFAULT_ENTITY_LIMIT` (500) -- the engine capped nothing on this real run, so the
  // report-wide omission notice must not appear. Reaching the cap itself through this
  // real stack would need a fixture of 500+ failing entities in one requirement, which is
  // unreasonable to ship as a fixture; that path is exercised instead by a component test
  // (`ReportView.stories.tsx`, `FilteredWithOmissionsAndAPartialRequirement`) built on a
  // real engine-shaped payload. This assertion is the real-path half: it proves the new
  // notice does not fire on a real run that never hit the cap.
  await expect(report.locator('[data-testid="filter-omitted-total"]')).toHaveCount(0);

  // T-0074: the run appears in this review's own run-history table beneath the picker.
  const runHistory = page.locator("section.card", {
    has: page.getByRole("heading", { name: "تاریخچهٔ اجراها" }),
  });
  await expect(runHistory.locator("tbody tr")).toHaveCount(1);
});

test("a requirement that evaluated nothing explains why, in words, beside its status", async ({
  page,
  account,
}) => {
  // T-0037: the case the T-0028 review reproduced. `window_prohibited.ids` ("No windows
  // permitted", seeded by `manage.py seed_rule_packs`) prohibits IfcWindow
  // (minOccurs=maxOccurs=0), and IFC_FILE (three_doors.ifc) contains no IfcWindow at all
  // -- the applicability itself matches zero subjects. The specification legitimately
  // reaches PASS (NO_SUBJECTS_AND_PROHIBITED: none present, which is what a prohibition
  // asks for), while its lone requirement evaluated no entities and reads INDETERMINATE,
  // passed == failed == indeterminate == 0. Before this task, the requirement row carried
  // only its bare description with no status and no explanation, so a PASS specification
  // sitting over a bare "shall not be provided" line read as an unexplained, possibly
  // contradictory report. This test is the real assertion the task's Scope calls for --
  // not a trivial always-true check -- and it fails for the right reason if the StatusPill
  // or the reason paragraph is removed (see the task's Evidence for the mutation proof).
  await page.goto("/");

  await page.getByLabel("رایانامه").fill(account.email);
  await page.getByLabel("گذرواژه").fill(account.password);
  await page.getByRole("button", { name: "ورود" }).click();

  await expect(page.locator(".avatar-trigger")).toBeVisible({ timeout: 15_000 });
  await page.locator(".avatar-trigger").click();
  await expect(page.locator(".user-menu-header strong")).toHaveText(account.tenantName);
  await page.keyboard.press("Escape");

  await expect(page.getByRole("heading", { name: "پروژه‌ها" })).toBeVisible();

  const projectName = `window-prohibited-project-${Date.now()}`;
  await page.getByRole("link", { name: "افزودن پروژه" }).click();
  await page.getByLabel("نام").fill(projectName);
  await page.getByRole("button", { name: "ایجاد پروژه" }).click();
  await expect(page.getByRole("heading", { name: projectName })).toBeVisible({ timeout: 10_000 });

  const reviewName = `window-prohibited-${Date.now()}`;
  await page.getByRole("link", { name: "افزودن بررسی" }).click();
  await expect(page.getByRole("heading", { name: "افزودن بررسی" })).toBeVisible();
  await page.getByLabel("نام").fill(reviewName);
  await page.locator('input[type="file"]').setInputFiles(IFC_FILE);
  await page.getByRole("button", { name: "ایجاد بررسی" }).click();
  await expect(page.getByRole("heading", { name: reviewName })).toBeVisible({ timeout: 10_000 });

  const picker = page.getByTestId("catalogue-picker");
  await expect(picker).toBeVisible();
  const windowProhibitedPack = picker
    .locator("li", { hasText: "No windows permitted" })
    .filter({ hasText: "v0.1" });
  await expect(windowProhibitedPack).toBeVisible({ timeout: 10_000 });
  await windowProhibitedPack.getByRole("checkbox").check();
  await picker.getByRole("button", { name: "اجرای بررسی با بسته‌های انتخاب‌شده" }).click();

  const report = page.locator("section.report");
  await expect(report).toBeVisible({ timeout: 30_000 });

  // The specification genuinely, legitimately reaches PASS: nothing prohibited is present.
  const spec = report.locator("li.spec").first();
  await expect(spec.locator(".spec__head .pill")).toHaveText("قبول"); // status.PASS

  // The requirement row beneath it, the actual subject of this task: a StatusPill
  // showing INDETERMINATE sits beside the requirement's own description -- rendered,
  // not merely present in the API JSON -- and the reason is the human sentence from the
  // server's gettext catalogue, never the bare reason code.
  const requirement = report.locator(".requirement").first();
  await expect(requirement.locator('[data-testid="requirement-text"]')).toHaveText(
    "The Name shall not be provided.",
  );
  const requirementPill = requirement.locator(".requirement__head .pill");
  await expect(requirementPill).toHaveText("نامشخص"); // status.INDETERMINATE, Persian UI chrome
  await expect(requirementPill).toHaveClass(/pill--indeterminate/);

  const requirementReason = requirement.locator('[data-testid="requirement-reason"]');
  await expect(requirementReason).toBeVisible();
  await expect(requirementReason).toHaveText(
    "This rule prohibits such elements and the model contains none.",
  );
  // The reason must never be the bare machine code -- that is the exact failure this
  // task exists to close (a bare INDETERMINATE with nothing beside it to explain it).
  await expect(requirementReason).not.toContainText("NO_SUBJECTS_AND_PROHIBITED");

  // No entities are itemised: the requirement matched nothing, so there is nothing to
  // list, and the table must not render for this row.
  await expect(requirement.locator("table.entities")).toHaveCount(0);

  await page.screenshot({
    path: path.resolve(__dirname, "screenshots/requirement-reason.png"),
    fullPage: true,
  });
});

test("a requirement that genuinely evaluated real entities still carries a caveat when its own specification's applicability was never established", async ({
  page,
  account,
}) => {
  // T-0037 review round 2, finding F1. `door_schema_mismatch.ids` ("Door name recorded
  // (wrong schema)", seeded by `manage.py seed_rule_packs`) names Name recorded on
  // IFCDOOR -- identical to door_name_recorded.ids -- except it declares
  // ifcVersion="IFC2X3" only. IFC_FILE (three_doors.ifc) is IFC4, so the specification's
  // own applicability could not be established (SCHEMA_MISMATCH,
  // UNDETERMINED_APPLICABILITY), and the specification itself reads INDETERMINATE.
  // ifctester still genuinely matches and evaluates all three real doors against the
  // Name facet, so the requirement beneath it is a real PASS with real non-zero counts
  // -- not the "evaluated nothing" case the test above covers. Before this fix, that PASS
  // rendered with no caveat at all, directly beneath a specification pill saying
  // applicability could not be established: an unqualified compliance claim this run
  // never established (CLAUDE.md, "Never assert compliance we did not establish"). This
  // test is the real assertion for that fix -- not a trivial always-true check -- and it
  // fails for the right reason if the caveat paragraph is removed (see the task's
  // Evidence, Round 2, for the mutation proof).
  await page.goto("/");

  await page.getByLabel("رایانامه").fill(account.email);
  await page.getByLabel("گذرواژه").fill(account.password);
  await page.getByRole("button", { name: "ورود" }).click();

  await expect(page.locator(".avatar-trigger")).toBeVisible({ timeout: 15_000 });
  await page.locator(".avatar-trigger").click();
  await expect(page.locator(".user-menu-header strong")).toHaveText(account.tenantName);
  await page.keyboard.press("Escape");

  await expect(page.getByRole("heading", { name: "پروژه‌ها" })).toBeVisible();

  const projectName = `schema-mismatch-project-${Date.now()}`;
  await page.getByRole("link", { name: "افزودن پروژه" }).click();
  await page.getByLabel("نام").fill(projectName);
  await page.getByRole("button", { name: "ایجاد پروژه" }).click();
  await expect(page.getByRole("heading", { name: projectName })).toBeVisible({ timeout: 10_000 });

  const reviewName = `schema-mismatch-${Date.now()}`;
  await page.getByRole("link", { name: "افزودن بررسی" }).click();
  await expect(page.getByRole("heading", { name: "افزودن بررسی" })).toBeVisible();
  await page.getByLabel("نام").fill(reviewName);
  await page.locator('input[type="file"]').setInputFiles(IFC_FILE);
  await page.getByRole("button", { name: "ایجاد بررسی" }).click();
  await expect(page.getByRole("heading", { name: reviewName })).toBeVisible({ timeout: 10_000 });

  const picker = page.getByTestId("catalogue-picker");
  await expect(picker).toBeVisible();
  const schemaMismatchPack = picker
    .locator("li", { hasText: "Door name recorded (wrong schema)" })
    .filter({ hasText: "v0.1" });
  await expect(schemaMismatchPack).toBeVisible({ timeout: 10_000 });
  await schemaMismatchPack.getByRole("checkbox").check();
  await picker.getByRole("button", { name: "اجرای بررسی با بسته‌های انتخاب‌شده" }).click();

  const report = page.locator("section.report");
  await expect(report).toBeVisible({ timeout: 30_000 });

  // The specification itself reads INDETERMINATE: its own applicability was never
  // established, a genuinely different question from whether its requirement passed.
  const spec = report.locator("li.spec").first();
  await expect(spec.locator(".spec__head .pill")).toHaveText("نامشخص"); // status.INDETERMINATE

  // The requirement row: a real PASS, rendered as PASS -- the measured evidence (three
  // real doors, each genuinely carrying a Name) is not suppressed or altered -- but with
  // a caveat beside it, not a bare, unqualified green pill.
  const requirement = report.locator(".requirement").first();
  const requirementPill = requirement.locator(".requirement__head .pill");
  await expect(requirementPill).toHaveText("قبول"); // status.PASS, Persian UI chrome
  await expect(requirementPill).toHaveClass(/pill--pass/);

  // No "evaluated nothing" reason: this requirement evaluated real entities.
  await expect(requirement.locator('[data-testid="requirement-reason"]')).toHaveCount(0);

  const caveat = requirement.locator('[data-testid="requirement-applicability-caveat"]');
  await expect(caveat).toBeVisible();
  await expect(caveat).toHaveText(
    "This rule is written for a different IFC schema than the model uses, so whether it applies could not be established.",
  );
  // Never the bare machine code.
  await expect(caveat).not.toContainText("SCHEMA_MISMATCH");

  await page.screenshot({
    path: path.resolve(__dirname, "screenshots/requirement-applicability-caveat.png"),
    fullPage: true,
  });
});

test("a restricted attribute name renders as its own sentence, never the dict repr, and a two-facet applicability joins in the reader's language", async ({
  page,
  account,
}) => {
  // T-0039. `door_name_restricted.ids` ("Restricted attribute name", seeded by `manage.py
  // seed_rule_packs`) wraps the requirement's own `<ids:name>` in an `xs:restriction`
  // (an enumeration of two acceptable attribute names) rather than a literal
  // `ids:simpleValue` -- exactly the shape that used to make `basis.name` come back
  // `null` and fall back to ifctester's own dict-repr sentence,
  // "The {'enumeration': [...]} shall be provided", as the report's primary line.
  //
  // `door_width_named_applicability.ids` ("Minimum door width, for named doors") is the
  // same door-width rule as door_width.ids, except its applicability is two facets (an
  // Entity facet and an Attribute facet), exercising the localized joiner between them
  // rather than the engine's own hardcoded " and ".
  await page.goto("/");

  await page.getByLabel("رایانامه").fill(account.email);
  await page.getByLabel("گذرواژه").fill(account.password);
  await page.getByRole("button", { name: "ورود" }).click();

  await expect(page.locator(".avatar-trigger")).toBeVisible({ timeout: 15_000 });
  await page.locator(".avatar-trigger").click();
  await expect(page.locator(".user-menu-header strong")).toHaveText(account.tenantName);
  await page.keyboard.press("Escape");

  await expect(page.getByRole("heading", { name: "پروژه‌ها" })).toBeVisible();

  const projectName = `restricted-name-project-${Date.now()}`;
  await page.getByRole("link", { name: "افزودن پروژه" }).click();
  await page.getByLabel("نام").fill(projectName);
  await page.getByRole("button", { name: "ایجاد پروژه" }).click();
  await expect(page.getByRole("heading", { name: projectName })).toBeVisible({ timeout: 10_000 });

  const reviewName = `restricted-name-${Date.now()}`;
  await page.getByRole("link", { name: "افزودن بررسی" }).click();
  await expect(page.getByRole("heading", { name: "افزودن بررسی" })).toBeVisible();
  await page.getByLabel("نام").fill(reviewName);
  await page.locator('input[type="file"]').setInputFiles(IFC_FILE);
  await page.getByRole("button", { name: "ایجاد بررسی" }).click();
  await expect(page.getByRole("heading", { name: reviewName })).toBeVisible({ timeout: 10_000 });

  const picker = page.getByTestId("catalogue-picker");
  await expect(picker).toBeVisible();
  const restrictedNamePack = picker
    .locator("li", { hasText: "Restricted attribute name" })
    .filter({ hasText: "v0.1" });
  await expect(restrictedNamePack).toBeVisible({ timeout: 10_000 });
  await restrictedNamePack.getByRole("checkbox").check();
  await picker.getByRole("button", { name: "اجرای بررسی با بسته‌های انتخاب‌شده" }).click();

  const report = page.locator("section.report");
  await expect(report).toBeVisible({ timeout: 30_000 });

  // T-0039: the requirement's primary line is the structured sentence, never the raw
  // Python dict repr the engine used to fall back to when the attribute name itself was
  // a restriction.
  const requirementText = report.locator('[data-testid="requirement-text"]').first();
  await expect(requirementText).toHaveText(
    "The OverallWidth or OverallHeight shall be provided.",
  );
  await expect(requirementText).not.toContainText("enumeration");
  await expect(requirementText).not.toContainText("{'");

  await page.screenshot({
    path: path.resolve(__dirname, "screenshots/restricted-attribute-name.png"),
    fullPage: true,
  });

  // Second review, second rule pack: the two-facet applicability.
  const secondProjectName = `named-applicability-project-${Date.now()}`;
  await page.goto("/projects");
  await page.getByRole("link", { name: "افزودن پروژه" }).click();
  await page.getByLabel("نام").fill(secondProjectName);
  await page.getByRole("button", { name: "ایجاد پروژه" }).click();
  await expect(page.getByRole("heading", { name: secondProjectName })).toBeVisible({
    timeout: 10_000,
  });

  const secondReviewName = `named-applicability-${Date.now()}`;
  await page.getByRole("link", { name: "افزودن بررسی" }).click();
  await expect(page.getByRole("heading", { name: "افزودن بررسی" })).toBeVisible();
  await page.getByLabel("نام").fill(secondReviewName);
  await page.locator('input[type="file"]').setInputFiles(IFC_FILE);
  await page.getByRole("button", { name: "ایجاد بررسی" }).click();
  await expect(page.getByRole("heading", { name: secondReviewName })).toBeVisible({
    timeout: 10_000,
  });

  const secondPicker = page.getByTestId("catalogue-picker");
  await expect(secondPicker).toBeVisible();
  const namedApplicabilityPack = secondPicker
    .locator("li", { hasText: "Minimum door width, for named doors" })
    .filter({ hasText: "v0.1" });
  await expect(namedApplicabilityPack).toBeVisible({ timeout: 10_000 });
  await namedApplicabilityPack.getByRole("checkbox").check();
  await secondPicker
    .getByRole("button", { name: "اجرای بررسی با بسته‌های انتخاب‌شده" })
    .click();

  const secondReport = page.locator("section.report");
  await expect(secondReport).toBeVisible({ timeout: 30_000 });

  // T-0039: two applicability facets -- an Entity facet ("All IFCDOOR data") and an
  // Attribute facet ("Data where the Name is provided") -- joined by the localized
  // joiner (English " and " here, since this harness's tenant language is English; the
  // task's Evidence section shows the same stored document rendered in Persian too).
  const applicability = secondReport.locator('[data-testid="applicability"]').first();
  await expect(applicability).toHaveText("All IFCDOOR data and Data where the Name is provided");

  await page.screenshot({
    path: path.resolve(__dirname, "screenshots/two-facet-applicability.png"),
    fullPage: true,
  });
});

test.describe("the applicability subject localizes with the browser's own language, not just the UI chrome", () => {
  // T-0039. `services/web` never sends `Accept-Language` itself (see `client.ts`) --
  // every other test in this file reads Latin/English report prose because a real
  // browser's own `Accept-Language` header (English, for this harness's Chromium) is what
  // `LocaleMiddleware` (`services/api/cadgpt/config/settings/base.py`) actually resolves
  // against. `applicability_text`'s `Entity` template is deliberately worded to read
  // byte-identical to ifctester's own English sentence (the module docstring says so), so
  // an English-only assertion cannot tell "rendered from `applicability_facets`" apart
  // from "the field this task's fix replaces" -- a swap back to
  // `applicability_description` would still read correctly in English and no assertion in
  // this file's other tests would catch it. This context's `locale: "fa-IR"` makes the
  // real browser send `Accept-Language: fa-IR`, which is what makes the two fields
  // actually diverge in the DOM.
  test.use({ locale: "fa-IR" });

  test("the two-facet applicability's Entity term reads in Persian, not the engine's English fallback", async ({
    page,
    account,
  }) => {
    await page.goto("/");

    await page.getByLabel("رایانامه").fill(account.email);
    await page.getByLabel("گذرواژه").fill(account.password);
    await page.getByRole("button", { name: "ورود" }).click();

    await expect(page.locator(".avatar-trigger")).toBeVisible({ timeout: 15_000 });
    await page.locator(".avatar-trigger").click();
    await expect(page.locator(".user-menu-header strong")).toHaveText(account.tenantName);
    await page.keyboard.press("Escape");

    await expect(page.getByRole("heading", { name: "پروژه‌ها" })).toBeVisible();

    const projectName = `named-applicability-fa-project-${Date.now()}`;
    await page.getByRole("link", { name: "افزودن پروژه" }).click();
    await page.getByLabel("نام").fill(projectName);
    await page.getByRole("button", { name: "ایجاد پروژه" }).click();
    await expect(page.getByRole("heading", { name: projectName })).toBeVisible({
      timeout: 10_000,
    });

    const reviewName = `named-applicability-fa-${Date.now()}`;
    await page.getByRole("link", { name: "افزودن بررسی" }).click();
    await expect(page.getByRole("heading", { name: "افزودن بررسی" })).toBeVisible();
    await page.getByLabel("نام").fill(reviewName);
    await page.locator('input[type="file"]').setInputFiles(IFC_FILE);
    await page.getByRole("button", { name: "ایجاد بررسی" }).click();
    await expect(page.getByRole("heading", { name: reviewName })).toBeVisible({
      timeout: 10_000,
    });

    const picker = page.getByTestId("catalogue-picker");
    await expect(picker).toBeVisible();
    const namedApplicabilityPack = picker
      .locator("li", { hasText: "Minimum door width, for named doors" })
      .filter({ hasText: "v0.1" });
    await expect(namedApplicabilityPack).toBeVisible({ timeout: 10_000 });
    await namedApplicabilityPack.getByRole("checkbox").check();
    await picker.getByRole("button", { name: "اجرای بررسی با بسته‌های انتخاب‌شده" }).click();

    const report = page.locator("section.report");
    await expect(report).toBeVisible({ timeout: 30_000 });

    // T-0039: the `Entity` term ("همهٔ داده‌های IFCDOOR") is localized; the `Attribute`
    // term ("Data where the Name is provided") is not this task's scope and falls back
    // to ifctester's own English sentence -- the same document, joined by the localized
    // joiner (" و "), exactly as the task's Evidence section shows from the raw API
    // response. This is the assertion that a field-name swap back to
    // `applicability_description` (English-joined, English "All IFCDOOR data") cannot
    // pass: neither the Persian entity term nor the Persian joiner would be there.
    const applicability = report.locator('[data-testid="applicability"]').first();
    await expect(applicability).toHaveText(
      "همهٔ داده‌های IFCDOOR و Data where the Name is provided",
    );
    await expect(applicability).not.toHaveText(
      "All IFCDOOR data and Data where the Name is provided",
    );

    await page.screenshot({
      path: path.resolve(__dirname, "screenshots/two-facet-applicability-fa.png"),
      fullPage: true,
    });
  });
});
