import type { Meta, StoryObj } from "@storybook/react-vite";

import { scenario, session } from "@/mocks/handlers";
import { AppAt } from "@/mocks/preview-app";

const meta = {
  title: "Screens/Workspace",
} satisfies Meta;

export default meta;
type Story = StoryObj<typeof meta>;

/**
 * Signed in, zero tenants. `App` withholds the shell entirely here rather than rendering
 * an account menu with no workspace to name. Submitting creates one and drops straight
 * into the projects changelist -- the slug is derived from the name, never asked for.
 */
export const FirstWorkspace: Story = {
  parameters: { msw: [...session({ tenants: [] }), ...scenario({ projects: [] })] },
  render: () => <AppAt route="/projects" />,
};
