import type { Meta, StoryObj } from "@storybook/react-vite";

import * as fx from "@/mocks/fixtures";
import { scenario, session, uploadTooLarge } from "@/mocks/handlers";
import { AppAt } from "@/mocks/preview-app";

const meta = {
  title: "Screens/Review/Add",
} satisfies Meta;

export default meta;
type Story = StoryObj<typeof meta>;

const at = () => <AppAt route={`/projects/${fx.project.uuid}/reviews/new`} />;

/**
 * Name and model file, and no rule-set picker: every review created here takes the
 * catalogue path, chosen per check on the review's own detail page
 * (`docs/decisions.md`, 2026-09-04). The stated ceiling under the file field is read from
 * `MAX_MODEL_UPLOAD_BYTES`, the same constant the server enforces.
 *
 * Pick any file and submit -- the mock accepts it and lands on the new review.
 */
export const Idle: Story = {
  parameters: { msw: [...session(), ...scenario()] },
  render: at,
};

/**
 * The upload rejected as too large. Submit any file to see it: the server's 413 `detail`
 * is what the form renders, not a message composed here -- so the number a person is told
 * is always the number that was actually enforced.
 */
export const ModelTooLarge: Story = {
  parameters: { msw: [uploadTooLarge(), ...session(), ...scenario()] },
  render: at,
};
