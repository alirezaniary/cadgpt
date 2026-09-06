import type { Meta, StoryObj } from "@storybook/react-vite";

import type { Report } from "@/api/types";
import { ReportView } from "@/components/ReportView";
import * as fx from "@/mocks/fixtures";

/**
 * The report on its own, outside the review page -- useful when the thing under review is
 * the document itself rather than the screen around it.
 */
const meta = {
  title: "Components/Report",
  component: ReportView,
  decorators: [
    (Story) => (
      <main className="page">
        <Story />
      </main>
    ),
  ],
} satisfies Meta<typeof ReportView>;

export default meta;
type Story = StoryObj<typeof meta>;

/** All three verdicts, an omitted-entities tail, and two specifications that established
 * nothing -- so the coverage line reads "4 of 6" rather than the "6 of 6" a naive sum
 * would always produce. */
export const Full: Story = {
  args: { report: fx.report, rulePackSelection: fx.detail(fx.succeededRun, fx.report).rule_pack_selection },
};

/** A run against an uploaded rule set carries no catalogue citation, so the "rule packs
 * checked" block is absent rather than empty. */
export const WithoutPackCitation: Story = {
  args: { report: fx.report, rulePackSelection: [] },
};

/**
 * Everything passed. The indeterminate count is still rendered, still in its own column,
 * still at the same weight -- a clean report is three zeros and a total, never two
 * columns.
 */
export const NothingToReport: Story = {
  args: {
    rulePackSelection: [],
    report: ((): Report => {
      const passing = fx.report.specifications.filter((spec) => spec.status === "PASS");
      return {
        ...fx.report,
        status: "PASS",
        specifications_passed: passing.length,
        specifications_failed: 0,
        specifications_indeterminate: 0,
        passed: 25,
        failed: 0,
        indeterminate: 0,
        specifications: passing,
      };
    })(),
  },
};
