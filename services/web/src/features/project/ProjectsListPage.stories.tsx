import type { Meta, StoryObj } from "@storybook/react-vite";

import * as fx from "@/mocks/fixtures";
import { failing, paths, pending, scenario, session } from "@/mocks/handlers";
import { AppAt } from "@/mocks/preview-app";

const meta = {
  title: "Screens/Projects/Changelist",
} satisfies Meta;

export default meta;
type Story = StoryObj<typeof meta>;

const at = () => <AppAt route="/projects" />;

/** Every project the tenant owns, with the annotated review count. Rows are clickable in
 * full, and "Add project" is the only action. */
export const Populated: Story = {
  parameters: { msw: [...session(), ...scenario()] },
  render: at,
};

/** A tenant that has just created its workspace. The empty line is a sentence with a next
 * step in it, not a blank table. */
export const Empty: Story = {
  parameters: { msw: [...session(), ...scenario({ projects: [] })] },
  render: at,
};

/** The projects query never resolves. The card, its heading and the add action are all
 * present; only the table is missing -- there is no spinner in this app. */
export const Loading: Story = {
  parameters: { msw: [pending(paths.projects), ...session(), ...scenario()] },
  render: at,
};

/** The list failed. Note what the page does *not* do: it shows the error and no rows,
 * never an empty state, which would read as "you have no projects". */
export const Failed: Story = {
  parameters: { msw: [failing(paths.projects), ...session(), ...scenario()] },
  render: at,
};

/**
 * The same screen for a user in two workspaces. Open the avatar menu: the workspace
 * switcher only renders above one tenant, and switching navigates back to `/projects`
 * because a project uuid in the URL belongs to the tenant being left.
 */
export const TwoWorkspaces: Story = {
  parameters: { msw: [...session({ tenants: [fx.tenant, fx.secondTenant] }), ...scenario()] },
  render: at,
};
