/**
 * Workbench-wide setup: the app's own stylesheet, its i18n instance, a language toolbar,
 * and MSW.
 *
 * The language toolbar is the one affordance here the product does not have. Language is
 * a build-time decision in this app (`src/i18n/index.ts`) and there is deliberately no UI
 * for it -- but `en.json` is the fallback catalogue and someone has to be able to read the
 * interface while reviewing it, so the toolbar exists in the preview only. It changes no
 * production behaviour: nothing in `src/` can see it.
 */

import type { Decorator, Preview } from "@storybook/react-vite";
import { mswLoader } from "msw-storybook-addon/csf3";

import { setAccessToken, setTenant } from "@/api/client";
import { LAST_TENANT_KEY } from "@/app/session-context";
import i18n, { applyDirection } from "@/i18n";
import "@/styles.css";

// Storybook paints its own canvas background; the app paints `body` from `--bg`. Without
// this the dark navy identity would sit on a white page in the preview only.
const canvas = document.createElement("style");
canvas.textContent = ".sb-show-main.sb-main-padded { padding: 0; }\n.sb-show-main { background: var(--bg); }";
document.head.appendChild(canvas);

const withLocale: Decorator = (Story, context) => {
  const locale = String(context.globals["locale"] ?? "fa");
  if (i18n.language !== locale) {
    void i18n.changeLanguage(locale);
    applyDirection(locale);
  }
  return <Story />;
};

const preview: Preview = {
  loaders: [mswLoader()],
  decorators: [withLocale],

  // The API client keeps the access token and the active tenant in module scope, and
  // `session.tsx` remembers the last workspace in `localStorage`. Neither is React state,
  // so neither is torn down when a story unmounts -- without this reset, a story that
  // signed in would leave the next one already authenticated and the signed-out screens
  // would be unreachable after visiting any other story.
  async beforeEach() {
    setAccessToken(null);
    setTenant(null);
    localStorage.removeItem(LAST_TENANT_KEY);
  },

  parameters: {
    layout: "fullscreen",
    a11y: { test: "todo" },
    options: {
      storySort: {
        order: ["Screens", ["Sign in", "Workspace", "Projects", "Project", "Review"], "Components"],
      },
    },
  },

  initialGlobals: { locale: "fa" },

  globalTypes: {
    locale: {
      description: "Interface language and text direction",
      toolbar: {
        title: "Language",
        icon: "globe",
        dynamicTitle: true,
        items: [
          { value: "fa", title: "فارسی — RTL (shipped)" },
          { value: "en", title: "English — LTR (fallback)" },
        ],
      },
    },
  },
};

export default preview;
