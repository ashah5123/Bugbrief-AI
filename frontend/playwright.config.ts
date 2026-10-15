import { defineConfig, devices } from "@playwright/test";
export default defineConfig({
  testDir: "./tests",
  fullyParallel: false,
  workers: 1,
  reporter: "list",
  use: {
    baseURL: "http://127.0.0.1:15173",
    channel: "chrome",
    trace: "retain-on-failure",
  },
  webServer: [
    {
      command: "../.venv/bin/python ../scripts/test_server.py",
      port: 18000,
      reuseExistingServer: false,
      timeout: 30000,
    },
    {
      command:
        "npm run dev -- --port 15173 --strictPort --config vite.e2e.config.ts",
      port: 15173,
      reuseExistingServer: false,
      timeout: 30000,
    },
  ],
  projects: [
    {
      name: "desktop",
      use: { ...devices["Desktop Chrome"], channel: "chrome" },
    },
    {
      name: "mobile",
      use: {
        viewport: { width: 390, height: 844 },
        isMobile: true,
        hasTouch: true,
        channel: "chrome",
      },
    },
  ],
});
