/**
 * T-0034 (F2). A Storybook `play` function is a regression test only if something runs it
 * on every `make verify` -- `storybook build` (already part of `verify`) never executes
 * `play`, so a broken assertion or a re-introduced bug passed silently until someone opened
 * the story by hand. `@storybook/addon-vitest`'s `storybookTest` plugin turns every story
 * into a real Vitest test, rendered in an actual headless Chromium (Vitest's browser mode,
 * `@vitest/browser-playwright`), applying the same preview annotations (decorators, MSW
 * loader from `.storybook/preview.tsx`) the interactive workbench uses -- automatic since
 * Storybook 10.3, no separate setup file needed. `pnpm run test-storybook` runs this
 * project directly; `pnpm run verify` runs it as its last step.
 *
 * T-0035 adds a second, plain project ("unit") beside it for pure functions where a
 * browser is not the right instrument -- `bySeverity`'s one defect only manifests for a
 * `status` outside the app's own `EntityFilter` vocabulary, which the Storybook-rendered
 * path would filter out of the DOM before the defect could ever be observed on screen.
 * No new test runner: same Vitest, same config file, run as `pnpm run test-unit` and
 * wired into `pnpm run verify` beside `test-storybook`.
 */
import path from "node:path";
import { fileURLToPath } from "node:url";

import { storybookTest } from "@storybook/addon-vitest/vitest-plugin";
import { playwright } from "@vitest/browser-playwright";
import { defineConfig, mergeConfig } from "vitest/config";

import viteConfig from "./vite.config";

const dirname = path.dirname(fileURLToPath(import.meta.url));

export default mergeConfig(
  viteConfig,
  defineConfig({
    test: {
      projects: [
        {
          extends: true,
          plugins: [storybookTest({ configDir: path.join(dirname, ".storybook") })],
          test: {
            name: "storybook",
            browser: {
              enabled: true,
              headless: true,
              provider: playwright(),
              instances: [{ browser: "chromium" }],
            },
          },
        },
        {
          extends: true,
          test: {
            name: "unit",
            environment: "node",
            include: ["src/**/*.test.ts"],
          },
        },
      ],
    },
  }),
);
