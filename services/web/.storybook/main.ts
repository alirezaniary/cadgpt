import type { StorybookConfig } from "@storybook/react-vite";

const config: StorybookConfig = {
  stories: ["../src/**/*.stories.@(ts|tsx)"],
  addons: ["@storybook/addon-a11y"],
  framework: { name: "@storybook/react-vite", options: {} },
  // This repository vendors its own fonts rather than depend on a font CDN, for tenants
  // who may run offline or behind a firewall. A build step that reports home would
  // contradict that for no benefit to anyone here.
  core: { disableTelemetry: true },
  // `mockServiceWorker.js` lives here. Without it MSW cannot install its worker and every
  // story would fall through to the real network.
  staticDirs: ["../public"],
};

export default config;
