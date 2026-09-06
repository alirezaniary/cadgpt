import type { Meta, StoryObj } from "@storybook/react-vite";
import { userEvent, waitFor } from "storybook/test";

import { session } from "@/mocks/handlers";
import { AppAt } from "@/mocks/preview-app";

/**
 * Sign-in and registration are branches of `App`, not routes, so the route below is
 * irrelevant to them -- what selects these screens is `/auth/refresh/` failing.
 */
const meta = {
  title: "Screens/Sign in",
} satisfies Meta;

export default meta;
type Story = StoryObj<typeof meta>;

/** Throws rather than returning null, so `waitFor` retries instead of a `play` step
 * silently doing nothing and leaving the story on the screen before it. */
function required<T extends Element>(root: HTMLElement, selector: string): T {
  const found = root.querySelector<T>(selector);
  if (!found) throw new Error(`not rendered yet: ${selector}`);
  return found;
}

/** No refresh cookie. This is what a first visit looks like. */
export const Idle: Story = {
  parameters: { msw: session({ authenticated: false }) },
  render: () => <AppAt route="/projects" />,
};

/**
 * Credentials rejected. The mock login refuses a password under four characters, and the
 * server's own `detail` is what `.error` renders -- the wording is never composed here.
 *
 * The `play` step fills and submits the form on load, because otherwise this state would
 * exist only for someone who happened to type the wrong thing. Selectors are ids and a
 * submit type rather than visible text, so the story survives the language toolbar.
 */
export const CredentialsRejected: Story = {
  parameters: { msw: session({ authenticated: false }) },
  render: () => <AppAt route="/projects" />,
  play: async ({ canvasElement }) => {
    // `App` renders a blank frame until `/auth/refresh/` settles, so the form does not
    // exist yet when `play` first runs -- every step here waits for it rather than
    // assuming it.
    const email = await waitFor(() => required<HTMLInputElement>(canvasElement, "#email"));
    const password = required<HTMLInputElement>(canvasElement, "#password");
    const submit = required<HTMLButtonElement>(canvasElement, 'button[type="submit"]');
    await userEvent.type(email, "s.hosseini@parsdesign.ir");
    await userEvent.type(password, "x");
    await userEvent.click(submit);
  },
};

/**
 * Account creation. This is a branch of `SignInPage`'s own state, not a route -- there is
 * no URL for it -- so the `play` step clicks through to it. That is the honest way to make
 * it addressable: the state is reached the way a person reaches it.
 *
 * Registering does not itself sign anyone in; the page calls `signIn` straight afterwards,
 * so a successful submit here lands on the first-workspace screen.
 */
export const Register: Story = {
  parameters: { msw: session({ authenticated: false, tenants: [] }) },
  render: () => <AppAt route="/projects" />,
  play: async ({ canvasElement }) => {
    const toRegister = await waitFor(() =>
      required<HTMLButtonElement>(canvasElement, ".link-button"),
    );
    await userEvent.click(toRegister);
  },
};
