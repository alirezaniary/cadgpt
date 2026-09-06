import type { Meta, StoryObj } from "@storybook/react-vite";

import { scenario, session } from "@/mocks/handlers";
import { AppAt } from "@/mocks/preview-app";

const meta = {
  title: "Screens/Projects/Add",
} satisfies Meta;

export default meta;
type Story = StoryObj<typeof meta>;

/**
 * One field. Submitting really does create the project against the in-memory backend and
 * navigate to its own detail page -- "save and continue editing", because the next thing
 * anyone does after creating a project is add a review to it. The breadcrumb above the
 * card is live: "Projects / Add project".
 */
export const Idle: Story = {
  parameters: { msw: [...session(), ...scenario()] },
  render: () => <AppAt route="/projects/new" />,
};
