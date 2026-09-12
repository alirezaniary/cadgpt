import type { Meta, StoryObj } from "@storybook/react-vite";
import { expect, waitFor, within } from "storybook/test";

import i18n from "@/i18n";
import { formatDate } from "@/lib/dates";
import * as fx from "@/mocks/fixtures";
import {
  failing,
  paths,
  pending,
  reportFileFailed,
  reportFileMissing,
  scenario,
  session,
} from "@/mocks/handlers";
import { AppAt } from "@/mocks/preview-app";

const meta = {
  title: "Screens/Review/Detail",
} satisfies Meta;

export default meta;
type Story = StoryObj<typeof meta>;

function at(reviewUuid: string) {
  return () => <AppAt route={`/projects/${fx.project.uuid}/reviews/${reviewUuid}`} />;
}

/**
 * A review that has never been checked: the catalogue picker, filtered by jurisdiction,
 * region and version, with the run button disabled until at least one pack is selected.
 *
 * **This is the story to click.** Select a pack and run the check: the mock advances the
 * run on a real clock -- Queued for two seconds, Running for five, then Complete with its
 * report rendered inline below. Everything in that sequence is the app's own polling
 * (1.5s on the open run, 2s on the history), not an animation.
 */
export const NeverChecked: Story = {
  parameters: {
    msw: [
      ...session(),
      ...scenario({
        reviews: { [fx.project.uuid]: [fx.neverRunReview] },
        runs: { [fx.neverRunReview.uuid]: [] },
      }),
    ],
  },
  render: at(fx.neverRunReview.uuid),
};

/**
 * A finished check, with the report open. Worth reading in this order, which is the order
 * the page puts it in: what was checked at all (the disclosure), how much of the rule set
 * was evaluated (coverage — four of six here, because two specifications established
 * nothing), then the findings, FAIL first and INDETERMINATE never under PASS.
 *
 * The filter offers FAIL and INDETERMINATE only. Turn one off and the banner states how
 * many rows are hidden rather than resolved, and the three counts do not move.
 *
 * T-0041: the run-history table above the report repeats the same pill-without-scope gap
 * the reviews changelist had -- a row here is `candidate.outcome` and three counts, with no
 * statement of what the outcome is about, and this table names its model once, above,
 * not per row. `play` proves the fix the same way `ProjectDetailPage.stories.tsx`'s own
 * `play` does: locate one real row (the succeeded run's, by its formatted date, which is
 * unique in this table) and assert the pill and the scope statement both live inside it,
 * not merely somewhere on the page.
 */
export const Checked: Story = {
  parameters: { msw: [...session(), ...scenario()] },
  render: at(fx.checkedReview.uuid),
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);

    const dateCell = await waitFor(() =>
      canvas.getByText(formatDate(fx.succeededRun.created_at)),
    );
    const row = dateCell.closest("tr");
    if (!row) throw new Error("run-history row not found for the succeeded run");
    const rowScope = within(row);

    // The verdict itself: FAIL, per `fx.succeededRun`'s fixture outcome.
    await expect(rowScope.getByText(i18n.t("status.FAIL"))).toBeInTheDocument();

    // The scope statement travels in the *same row* as the pill. Asserted against the
    // literal Persian string, not a second `i18n.t("review.outcomeScope")` lookup: the
    // component and a second catalogue read resolve through the very same JSON, so if the
    // key were deleted from both `en.json` and `fa.json`, i18next's `fallbackLng` would
    // make both sides render the bare key name and this assertion would still pass --
    // catching nothing. The literal string only passes while the catalogue actually says
    // this.
    await expect(
      rowScope.getByText("دربارهٔ مدل است، نه نقشه‌ها"),
    ).toBeInTheDocument();
  },
};

/** A check in flight. The button reads "Checking…" and is disabled, and both polls are
 * live -- this story never settles, on purpose. */
export const Running: Story = {
  parameters: { msw: [...session(), ...scenario()] },
  render: at(fx.runningReview.uuid),
};

/**
 * A run that failed. The report is absent because there is none -- the page never renders
 * a partial report for a run that did not finish -- and in its place is the reason the
 * server gave: `RESOURCE_EXHAUSTED`'s Persian `failure_detail`, rendered as the server sent
 * it (T-0081), not looked up from `failure_reason` in a frontend table.
 *
 * T-0048 fix-now (F1/F3): `fx.failedReview` uses a catalogue selection (its
 * `rule_pack_selection`, attached by `fx.detail`'s default), so the failure card must
 * also name what this run was dispatched to check -- under a heading that says
 * "selected", never "checked": this run never produced a report, so it never checked
 * anything.
 */
export const RunFailed: Story = {
  parameters: { msw: [...session(), ...scenario()] },
  render: at(fx.failedReview.uuid),
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    const card = await waitFor(() => canvas.getByTestId("run-failure"));
    const scope = within(card);

    // The honest heading (F1) -- never the "were checked" wording `ReportView` uses on
    // its own, genuinely-checked path.
    await expect(
      scope.getByText(i18n.t("report.selection.titleSelected")),
    ).toBeInTheDocument();
    await expect(
      scope.queryByText(i18n.t("report.selection.title")),
    ).not.toBeInTheDocument();

    // The selection itself (F3) -- the packs this run was dispatched against, visible on
    // its failed run for the first time. `fx.DEFAULT_SELECTION` carries two entries
    // (T-0049), both sharing this name prefix by design (`fx.rulePacks`'s own naming),
    // so both, not one, must be findable here.
    await expect(scope.getAllByText(/مقررات ملی ساختمان/)).toHaveLength(2);
  },
};

/**
 * A run that failed against an uploaded rule set rather than a catalogue selection
 * (T-0048 F3). `rule_pack_selection` is `[]` for every run of a review shaped this way --
 * `_resolve_selection` never populates it when `review.rule_set` is set -- so
 * `RulePackSelectionList` alone would render nothing here, the exact defect this task's
 * title names, unchanged for this selection shape. The failure card must name the
 * review's own `rule_set` instead.
 */
export const RunFailedRuleSet: Story = {
  parameters: {
    msw: [
      ...session(),
      ...scenario({
        reviews: { [fx.project.uuid]: [fx.failedReviewRuleSet] },
        runs: { [fx.failedReviewRuleSet.uuid]: [fx.failedRunRuleSet] },
      }),
    ],
  },
  render: at(fx.failedReviewRuleSet.uuid),
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    const card = await waitFor(() => canvas.getByTestId("run-failure"));
    const scope = within(card);

    await expect(scope.getByText(fx.uploadedRuleSet.name)).toBeInTheDocument();
    // Never the catalogue-pack list: there is no catalogue selection on this shape.
    await expect(scope.queryByTestId("rule-pack-selection")).not.toBeInTheDocument();
  },
};

/**
 * A run that failed with a blank `failure_detail` -- `INTERNAL_ERROR` wrapping an
 * exception with no message, still possible per `CheckRunExecutor.execute` even though
 * `failure_reason` itself is guaranteed non-blank by the database constraint. The status
 * word alone is never the whole story here either: a frontend-owned fallback sentence
 * fills the region instead of an empty block (T-0081).
 */
export const RunFailedNoDetail: Story = {
  parameters: {
    msw: [
      ...session(),
      ...scenario({
        reviews: { [fx.project.uuid]: [fx.failedReviewNoDetail] },
        runs: { [fx.failedReviewNoDetail.uuid]: [fx.failedRunNoDetail] },
      }),
    ],
  },
  render: at(fx.failedReviewNoDetail.uuid),
};

/**
 * The check succeeded but its report file was never generated -- the second, separately
 * dispatched task (T-0032) whose message can be lost. The page distinguishes this from
 * "cannot be generated" and offers the recovery button (T-0051). Press it: the mock
 * generates the file and the download button replaces this line.
 */
export const ReportFileNotGenerated: Story = {
  parameters: { msw: [reportFileMissing(), ...session(), ...scenario()] },
  render: at(fx.checkedReview.uuid),
};

/**
 * Generation failed for a reason a retry will not change -- the rendered report was too
 * large to store. Said in the server's own words, in `.error`, with the retry still
 * offered rather than hidden.
 */
export const ReportFileFailed: Story = {
  parameters: { msw: [reportFileFailed(), ...session(), ...scenario()] },
  render: at(fx.checkedReview.uuid),
};

/** The review and its runs still loading. The heading falls back to an ellipsis; nothing
 * below it is guessed at. */
export const Loading: Story = {
  parameters: {
    msw: [pending(paths.runs), pending(paths.rulePacks), ...session(), ...scenario()],
  },
  render: at(fx.checkedReview.uuid),
};

/** The catalogue itself is unreachable, so there are no packs to choose and no check can
 * be started. */
export const CatalogueFailed: Story = {
  parameters: {
    msw: [
      failing(paths.rulePacks),
      ...session(),
      ...scenario({
        reviews: { [fx.project.uuid]: [fx.neverRunReview] },
        runs: { [fx.neverRunReview.uuid]: [] },
      }),
    ],
  },
  render: at(fx.neverRunReview.uuid),
};
