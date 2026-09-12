import type { Meta, StoryObj } from "@storybook/react-vite";
import { expect, waitFor, within } from "storybook/test";

import i18n from "@/i18n";
import * as fx from "@/mocks/fixtures";
import { failing, paths, pending, scenario, session } from "@/mocks/handlers";
import { AppAt } from "@/mocks/preview-app";

const meta = {
  title: "Screens/Project/Detail",
} satisfies Meta;

export default meta;
type Story = StoryObj<typeof meta>;

const at = () => <AppAt route={`/projects/${fx.project.uuid}`} />;

/**
 * A project's reviews, one row each, with the latest run's status and three-valued
 * outcome. The list refetches itself every two seconds while any run is unfinished, which
 * the running review here keeps alive -- leave it open and watch the poll.
 *
 * T-0041: a status pill and three counts, with nothing stating that the verdict is about
 * the model rather than the drawing set an office submits, is exactly the surface a reader
 * screenshots into an email before ever opening the report underneath it (see this task's
 * `Why`). `play` proves the fix the same way it would fail without it: the row carrying
 * `fx.checkedReview`'s FAIL pill must also carry `review.outcomeScope`, in the *same* row
 * -- not merely somewhere on the page -- so a crop of that one row keeps both.
 */
export const Populated: Story = {
  parameters: { msw: [...session(), ...scenario()] },
  render: at,
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);

    const modelCell = await waitFor(() =>
      canvas.getByText(fx.checkedReview.model_file.original_name),
    );
    const row = modelCell.closest("tr");
    if (!row) throw new Error("reviews-table row not found for the checked review");
    const rowScope = within(row);

    // The verdict itself: FAIL, per `fx.checkedReview`'s `succeededRun` fixture.
    await expect(rowScope.getByText(i18n.t("status.FAIL"))).toBeInTheDocument();

    // The scope statement travels in the *same row* as the pill, not merely on the page --
    // a screenshot of this row alone must still carry it. Asserted against the literal
    // Persian string, not a second `i18n.t("review.outcomeScope")` lookup: the component
    // and a second catalogue read resolve through the very same JSON, so if the key were
    // deleted from both `en.json` and `fa.json`, i18next's `fallbackLng` would make both
    // sides render the bare key name and this assertion would still pass -- catching
    // nothing. The literal string only passes while the catalogue actually says this.
    await expect(
      rowScope.getByText("دربارهٔ مدل است، نه نقشه‌ها"),
    ).toBeInTheDocument();
  },
};

/** A project created a minute ago. The heading is the project's own name, from its own
 * request -- not read out of the changelist's cache, so this page stands up on a reload. */
export const NoReviews: Story = {
  parameters: {
    msw: [...session(), ...scenario({ reviews: { [fx.project.uuid]: [] }, runs: {} })],
  },
  render: at,
};

/** Both queries pending. The heading falls back to an ellipsis rather than rendering an
 * empty `h1`. */
export const Loading: Story = {
  parameters: {
    msw: [pending(paths.project), pending(paths.reviews), ...session(), ...scenario()],
  },
  render: at,
};

/** The reviews query failed. Same rule as the changelist: an error, never an empty state. */
export const Failed: Story = {
  parameters: { msw: [failing(paths.reviews), ...session(), ...scenario()] },
  render: at,
};
