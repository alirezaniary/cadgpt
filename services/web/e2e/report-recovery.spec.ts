/**
 * T-0051: the two silences a succeeded run's missing report can mean, rendered -- and
 * the recovery button's own POST actually driving the second one. Rewritten for T-0074's
 * project/review split: the review now lives on its own detail page, created with a
 * catalogue-selected pack instead of an uploaded rule set (rule-set upload is gone from
 * the UI per `docs/decisions.md`'s 2026-09-04 entry).
 *
 * `report.spec.ts` already proves the "available" state for real: a real check runs, a
 * real worker generates the file, and `report-file-link` appears with nothing else shown
 * alongside it. What it cannot reach without special setup is the other two -- "not
 * generated yet" and "cannot be generated" both require a run stuck in a state a healthy
 * worker never leaves it in for long, and this repository's fixtures have no file that
 * clears `MediaService`'s real 8MB cap quickly enough for a browser test. Both are proven
 * for real against the live stack in the task file's Evidence section instead; what only
 * a browser can show is whether the page renders them differently, and whether the
 * recovery button's click is what moves the run from one to the other rather than merely
 * the page's own polling.
 *
 * The run itself is completely real: a real sign-in, a real project, a real review, a
 * real check against the real engine and the catalogue's seeded "Accessible door width"
 * pack. Two routes are intercepted, each for a different reason:
 *
 * - The run-detail `GET` is held at "pending" (`report_file_url` and
 *   `report_generation_error` both blank -- the real shape a run with an in-flight or
 *   lost generation dispatch has) until `postSucceeded` below is set, and only then
 *   switched to the real shape a permanently-failed generation leaves
 *   (`report_generation_error: "too_large"`, the decision this task made, proven for
 *   real in the task file). Every other field is the real run's own.
 * - The recovery button's own `POST` to `.../report-file/` is allowed through to the
 *   real backend, and `postSucceeded` is set only if that real response is 2xx.
 */

import path from "node:path";
import { fileURLToPath } from "node:url";

import { expect, test } from "./fixtures";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const FIXTURES_DIR = path.resolve(__dirname, "../../../packages/engine/tests/fixtures");
const IFC_FILE = path.join(FIXTURES_DIR, "three_doors.ifc");

test("the recovery button's own POST is what moves a pending report to failed", async ({
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

  const projectName = `recovery-project-${Date.now()}`;
  await page.getByRole("link", { name: "افزودن پروژه" }).click();
  await page.getByLabel("نام").fill(projectName);
  await page.getByRole("button", { name: "ایجاد پروژه" }).click();
  await expect(page.getByRole("heading", { name: projectName })).toBeVisible({ timeout: 10_000 });

  const reviewName = `recovery-${Date.now()}`;
  await page.getByRole("link", { name: "افزودن بررسی" }).click();
  await page.getByLabel("نام").fill(reviewName);
  await page.locator('input[type="file"]').setInputFiles(IFC_FILE);
  await page.getByRole("button", { name: "ایجاد بررسی" }).click();
  await expect(page.getByRole("heading", { name: reviewName })).toBeVisible({ timeout: 10_000 });

  const picker = page.getByTestId("catalogue-picker");
  const doorWidthPack = picker
    .locator("li", { hasText: "Accessible door width" })
    .filter({ hasText: "v0.1" });
  await expect(doorWidthPack).toBeVisible({ timeout: 10_000 });
  await doorWidthPack.getByRole("checkbox").check();

  // Set before the GET route below reads it, so a request racing ahead of the click
  // (there is at least one poll before the button is ever pressed) sees `false`.
  let postSucceeded = false;

  // The recovery button's own POST. Passed through to the real backend for real; only
  // a genuine 2xx unlocks the "failed" state below.
  await page.route("**/api/v1/reviews/*/runs/*/report-file/", async (route) => {
    if (route.request().method() !== "POST") return route.fallback();
    const response = await route.fetch();
    if (response.ok()) postSucceeded = true;
    return route.fulfill({ response });
  });

  // The run-detail GET. Real in every field except the two this test needs to hold
  // still: blank ("pending") until the button's POST above has actually succeeded,
  // then the real too-large shape.
  await page.route("**/api/v1/reviews/*/runs/*/", async (route) => {
    if (route.request().method() !== "GET") return route.fallback();
    const response = await route.fetch();
    const real = (await response.json()) as Record<string, unknown>;
    if (real.status !== "succeeded") return route.fulfill({ response });
    const override = postSucceeded
      ? { report_file_url: null, report_generation_error: "too_large" }
      : { report_file_url: null, report_generation_error: "" };
    return route.fulfill({ response, json: { ...real, ...override } });
  });

  await picker.getByRole("button", { name: "اجرای بررسی با بسته‌های انتخاب‌شده" }).click();

  const pending = page.getByTestId("report-file-pending");
  await expect(pending).toBeVisible({ timeout: 30_000 });
  await expect(page.getByTestId("report-file-link")).toHaveCount(0);
  await expect(page.getByTestId("report-file-failed")).toHaveCount(0);
  const generateButton = page.getByTestId("report-file-generate");
  await expect(generateButton).toBeVisible();

  // Held here deliberately: while nothing has clicked the button yet, the run-detail
  // poll must keep re-confirming "pending" on its own, not drift toward "failed" on a
  // timer. If this fails, the GET override above is wrong, not the button.
  await page.waitForTimeout(2_500);
  await expect(pending).toBeVisible();
  await expect(page.getByTestId("report-file-failed")).toHaveCount(0);

  await generateButton.click();

  const failed = page.getByTestId("report-file-failed");
  await expect(failed).toBeVisible();
  await expect(page.getByTestId("report-file-pending")).toHaveCount(0);
  await expect(page.getByTestId("report-file-link")).toHaveCount(0);
  await expect(page.getByTestId("report-file-generate")).toBeVisible();
});
