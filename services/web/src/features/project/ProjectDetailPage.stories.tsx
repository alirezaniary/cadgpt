import type { Meta, StoryObj } from "@storybook/react-vite";

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
 */
export const Populated: Story = {
  parameters: { msw: [...session(), ...scenario()] },
  render: at,
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
