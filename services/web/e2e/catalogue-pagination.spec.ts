/**
 * T-0045. Before this task, `useRulePacks` fetched `/v1/rule-packs/` with no `size`
 * parameter (`SimplePagination.page_size` is 20) and `ReviewDetailPage`'s picker
 * filtered that one page client-side with a substring match -- a pack sitting past
 * position 20 in the catalogue's own ordering could never be found or selected, no
 * matter how correctly it was typed, and the picker read "no packs match this
 * filter" for a filter that in fact matched something the client had simply never
 * asked for.
 *
 * The fix routes the picker's filter through the server's own `RulePackFilterSet`
 * and walks every page of the (filtered) result rather than stopping at the first.
 * `z-t0045-page2-12` is a pack seeded for this evidence at catalogue position 22 of
 * 25 (`docker exec cadgpt-api-1 python manage.py shell`, this task's Evidence
 * section carries the exact command) -- past the pre-fix page-1 boundary of 20 under
 * the server's own default ordering (jurisdiction, region, name, version), the same
 * ordering `RulePackViewSet.ordering` declares.
 */

import path from "node:path";
import { fileURLToPath } from "node:url";

import { expect, test } from "./fixtures";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const FIXTURES_DIR = path.resolve(__dirname, "../../../packages/engine/tests/fixtures");
const IFC_FILE = path.join(FIXTURES_DIR, "three_doors.ifc");

const PAGE_TWO_JURISDICTION = "z-t0045-page2-12";

test("a pack seeded past the catalogue's first page is found by a server-side filter, selected, and cited by a completed run", async ({
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

  const projectName = `catalogue-page2-project-${Date.now()}`;
  await page.getByRole("link", { name: "افزودن پروژه" }).click();
  await page.getByLabel("نام").fill(projectName);
  await page.getByRole("button", { name: "ایجاد پروژه" }).click();
  await expect(page.getByRole("heading", { name: projectName })).toBeVisible({ timeout: 10_000 });

  const reviewName = `catalogue-page2-${Date.now()}`;
  await page.getByRole("link", { name: "افزودن بررسی" }).click();
  await expect(page.getByRole("heading", { name: "افزودن بررسی" })).toBeVisible();
  await page.getByLabel("نام").fill(reviewName);
  await page.locator('input[type="file"]').setInputFiles(IFC_FILE);
  await page.getByRole("button", { name: "ایجاد بررسی" }).click();
  await expect(page.getByRole("heading", { name: reviewName })).toBeVisible({ timeout: 10_000 });

  const picker = page.getByTestId("catalogue-picker");
  await expect(picker).toBeVisible();

  await picker.getByLabel("حوزهٔ قضایی").fill(PAGE_TWO_JURISDICTION);

  // Debounced (300ms) before the server-side filter fires -- wait for the real row
  // rather than a fixed sleep. Before this task's fix, this pack (catalogue position
  // 22) was never on the one page the picker fetched, so this line is exactly what
  // used to time out.
  const pageTwoPack = picker.locator("li", { hasText: PAGE_TWO_JURISDICTION });
  await expect(pageTwoPack).toBeVisible({ timeout: 10_000 });
  await expect(picker.getByTestId("catalogue-empty")).toHaveCount(0);

  await pageTwoPack.getByRole("checkbox").check();
  await picker.getByRole("button", { name: "اجرای بررسی با بسته‌های انتخاب‌شده" }).click();

  const report = page.locator("section.report");
  await expect(report).toBeVisible({ timeout: 30_000 });

  // The completed run cites the page-2 pack by name -- T-0031's selection record,
  // never re-derived from the live catalogue.
  const selection = report.locator('[data-testid="rule-pack-selection"]');
  await expect(selection).toBeVisible();
  await expect(selection).toContainText(PAGE_TWO_JURISDICTION);

  await page.screenshot({
    path: path.resolve(__dirname, "screenshots/catalogue-page-two-selected.png"),
    fullPage: true,
  });
});

test("the picker distinguishes a filter matching nothing from the catalogue not having answered yet", async ({
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

  const projectName = `catalogue-empty-vs-loading-project-${Date.now()}`;
  await page.getByRole("link", { name: "افزودن پروژه" }).click();
  await page.getByLabel("نام").fill(projectName);
  await page.getByRole("button", { name: "ایجاد پروژه" }).click();
  await expect(page.getByRole("heading", { name: projectName })).toBeVisible({ timeout: 10_000 });

  const reviewName = `catalogue-empty-vs-loading-${Date.now()}`;

  // Delay every rule-pack response from here on, so the "has not answered yet"
  // branch is observable in the real DOM rather than racing past a fast local
  // response before an assertion could ever see it.
  await page.route("**/v1/rule-packs/**", async (route) => {
    await new Promise((resolve) => setTimeout(resolve, 1500));
    await route.continue();
  });

  await page.getByRole("link", { name: "افزودن بررسی" }).click();
  await expect(page.getByRole("heading", { name: "افزودن بررسی" })).toBeVisible();
  await page.getByLabel("نام").fill(reviewName);
  await page.locator('input[type="file"]').setInputFiles(IFC_FILE);
  await page.getByRole("button", { name: "ایجاد بررسی" }).click();
  await expect(page.getByRole("heading", { name: reviewName })).toBeVisible({ timeout: 10_000 });

  const picker = page.getByTestId("catalogue-picker");
  await expect(picker).toBeVisible();

  // "Has not answered yet": the delayed first fetch, before any filter was typed.
  await expect(picker.getByTestId("catalogue-loading")).toBeVisible();
  await expect(picker.getByTestId("catalogue-empty")).toHaveCount(0);
  await page.screenshot({
    path: path.resolve(__dirname, "screenshots/catalogue-loading.png"),
    fullPage: true,
  });

  await expect(picker.getByTestId("catalogue-loading")).toHaveCount(0, { timeout: 10_000 });

  // "No packs match this filter": once the catalogue has genuinely answered, a
  // filter guaranteed to match nothing in the seeded catalogue.
  await picker.getByLabel("حوزهٔ قضایی").fill("no-such-jurisdiction-xyz");
  await expect(picker.getByTestId("catalogue-empty")).toBeVisible({ timeout: 10_000 });
  await expect(picker.getByTestId("catalogue-loading")).toHaveCount(0);
  await page.screenshot({
    path: path.resolve(__dirname, "screenshots/catalogue-empty.png"),
    fullPage: true,
  });
});
