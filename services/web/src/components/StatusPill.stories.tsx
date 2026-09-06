import type { Meta, StoryObj } from "@storybook/react-vite";

import { StatusPill } from "@/components/StatusPill";

/**
 * The three-valued verdict. All three are shown together here because the point of this
 * component is comparative: INDETERMINATE must not read as a softer PASS, and colour
 * alone would not carry that -- the label is always rendered beside it.
 */
const meta = {
  title: "Components/Status pill",
  component: StatusPill,
  parameters: { layout: "centered" },
} satisfies Meta<typeof StatusPill>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Pass: Story = { args: { status: "PASS" } };
export const Fail: Story = { args: { status: "FAIL" } };
export const Indeterminate: Story = { args: { status: "INDETERMINATE" } };

export const AllThree: Story = {
  args: { status: "PASS" },
  render: () => (
    <div className="row">
      <StatusPill status="PASS" />
      <StatusPill status="FAIL" />
      <StatusPill status="INDETERMINATE" />
    </div>
  ),
};
