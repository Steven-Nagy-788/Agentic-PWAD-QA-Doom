import { defineConfig, devices } from "@playwright/test";

const baseURL = process.env.PLAYWRIGHT_BASE_URL ?? "http://127.0.0.1:3100";
const webServerCommand = process.env.PLAYWRIGHT_WEB_SERVER_COMMAND ?? "bun run dev --hostname 127.0.0.1 --port 3100";
const webServer = process.env.PLAYWRIGHT_SKIP_WEB_SERVER
  ? undefined
  : {
      command: webServerCommand,
      url: baseURL,
      reuseExistingServer: !process.env.CI,
      timeout: 120_000,
    };

export default defineConfig({
  testDir: "./e2e",
  timeout: 30_000,
  expect: {
    timeout: 5_000,
  },
  use: {
    baseURL,
    trace: "retain-on-failure",
    ...devices["Desktop Chrome"],
  },
  webServer,
});
