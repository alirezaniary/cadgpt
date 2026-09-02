/**
 * Drives the built container image, not a dev server.
 *
 * `make up` brings up the whole compose stack — postgres, redis, the API, a worker and
 * the `web` container serving the production build behind nginx on :8080. There is no
 * `webServer` block here on purpose: Playwright does not start anything, it only points
 * a real browser at what `make up` already started, so the thing under test is the same
 * image a deploy would ship.
 */

import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  retries: 0,
  reporter: [["list"]],
  use: {
    baseURL: "http://localhost:8080",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],
});
