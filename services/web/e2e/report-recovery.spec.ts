/**
 * T-0051: the two silences a succeeded run's missing report can mean, rendered -- and
 * the recovery button's own POST actually driving the second one.
 *
 * `report.spec.ts` already proves the "available" state for real: a real check runs, a
 * real worker generates the file, and `report-file-link` appears with nothing else
 * shown alongside it. What it cannot reach without special setup is the other two --
 * "not generated yet" and "cannot be generated" both require a run stuck in a state a
 * healthy worker never leaves it in for long (the whole point of this task), and this
 * repository's fixtures have no file that clears `MediaService`'s real 8MB cap quickly
 * enough for a browser test. Both are proven for real against the live stack in the
 * task file's Evidence section instead; what only a browser can show is whether the
 * page renders them differently, and whether the recovery button's click is what moves
 * the run from one to the other rather than merely the page's own polling.
 *
 * The run itself is completely real: a real sign-in, a real review, a real check
 * against the real engine. Two routes are intercepted, each for a different reason:
 *
 * - The run-detail `GET` is held at "pending" (`report_file_url` and
 *   `report_generation_error` both blank -- the real shape a run with an in-flight or
 *   lost generation dispatch has) until `postSucceeded` below is set, and only then
 *   switched to the real shape a permanently-failed generation leaves
 *   (`report_generation_error: "too_large"`, the decision this task made, proven for
 *   real in the task file). Every other field is the real run's own.
 * - The recovery button's own `POST` to `.../report-file/` is allowed through to the
 *   real backend, and `postSucceeded` is set only if that real response is 2xx. This is
 *   the fix for the first review round's finding: that route previously went
 *   unintercepted and unobserved, so the GET override could (and did) flip to "failed"
 *   on a timer regardless of whether the button's click reached anything. Now it
 *   cannot: break the route the button posts to -- remove `CheckRunViewSet.
 *   generate_report`'s registration in `api/v1/urls.py`, or point the frontend at the
 *   wrong path -- and `postSucceeded` never becomes true, the GET override never
 *   advances past "pending", and the assertion below on `report-file-failed` times out
 *   rather than passing. Proved by doing exactly that; see the task file's Evidence.
 */

import path from "node:path";
import { fileURLToPath } from "node:url";

import { expect, test } from "./fixtures";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const FIXTURES_DIR = path.resolve(__dirname, "../../../packages/engine/tests/fixtures");
const IDS_FILE = path.join(FIXTURES_DIR, "door_width.ids");
const IFC_FILE = path.join(FIXTURES_DIR, "three_doors.ifc");

test("the recovery button's own POST is what moves a pending report to failed", async ({
  page,
  account,
}) => {
  await page.goto("/");
  await page.getByLabel("Email").fill(account.email);
  await page.getByLabel("Password").fill(account.password);
  await page.getByRole("button", { name: "Sign in" }).click();
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

  const reviewName = `recovery-${Date.now()}`;
  await reviewsCard.getByPlaceholder("Name").fill(reviewName);
  await reviewsCard.locator('select[name="rule_set"]').selectOption({ label: ruleSetName });
  await reviewsCard.locator('input[type="file"]').setInputFiles(IFC_FILE);
  await reviewsCard.getByRole("button", { name: "Create review" }).click();

  const reviewRow = reviewsCard.locator("li.review", { hasText: reviewName });
  await expect(reviewRow).toBeVisible();

  // Set before the GET route below reads it, so a request racing ahead of the click
  // (there is at least one poll before the button is ever pressed) sees `false`.
  let postSucceeded = false;

  // The recovery button's own POST. Passed through to the real backend for real; only
  // a genuine 2xx unlocks the "failed" state below. `**/report-file/` does not overlap
  // the run-detail pattern beneath it -- `*` does not cross `/` in a Playwright glob --
  // so this only ever sees the button's own request, never the run-detail poll.
  await page.route("**/api/v1/reviews/*/runs/*/report-file/", async (route) => {
    if (route.request().method() !== "POST") return route.fallback();
    const response = await route.fetch();
    if (response.ok()) postSucceeded = true;
    return route.fulfill({ response });
  });

  // The run-detail GET. Real in every field except the two this test needs to hold
  // still: blank ("pending") until the button's POST above has actually succeeded,
  // then the real too-large shape (the decision proven for real in the task file).
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

  await reviewRow.getByRole("button", { name: "Run check" }).click();
  const summaryButton = reviewRow.getByRole("button", { name: "Summary" });
  await expect(summaryButton).toBeVisible({ timeout: 30_000 });
  await summaryButton.click();

  const pending = page.getByTestId("report-file-pending");
  await expect(pending).toBeVisible();
  await expect(page.getByTestId("report-file-link")).toHaveCount(0);
  await expect(page.getByTestId("report-file-failed")).toHaveCount(0);
  const generateButton = page.getByTestId("report-file-generate");
  await expect(generateButton).toBeVisible();

  // Held here deliberately: while nothing has clicked the button yet, the run-detail
  // poll (every 2s, `useCheckRun`) must keep re-confirming "pending" on its own, not
  // drift toward "failed" on a timer. If this fails, the GET override above is wrong,
  // not the button.
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
