import { defineConfig, devices } from "@playwright/test";
import { existsSync } from "node:fs";

// Use the pre-installed Chromium when present (CI images / cloud dev boxes).
const chromium = process.env.PLAYWRIGHT_CHROMIUM_PATH ?? "/opt/pw-browsers/chromium";
const launchOptions = existsSync(chromium) ? { executablePath: chromium } : {};

export default defineConfig({
  testDir: "./e2e",
  timeout: 60_000,
  fullyParallel: false,
  workers: 1,
  reporter: [["list"]],
  use: {
    baseURL: "http://localhost:5174",
    trace: "retain-on-failure",
    launchOptions,
  },
  projects: [
    { name: "desktop", use: { ...devices["Desktop Chrome"], launchOptions }, testIgnore: /responsive\.spec\.ts/ },
    { name: "mobile", use: { ...devices["Pixel 7"], launchOptions }, testMatch: /responsive\.spec\.ts/ },
  ],
  webServer: [
    {
      command: "E2E_RESET=1 E2E_AI=mock PORT=8001 ../scripts/e2e-backend.sh",
      url: "http://127.0.0.1:8001/health",
      reuseExistingServer: false,
      timeout: 120_000,
    },
    {
      command: "E2E_AI=none PORT=8002 E2E_FRONTEND_URL=http://localhost:5175 ../scripts/e2e-backend.sh",
      url: "http://127.0.0.1:8002/health",
      reuseExistingServer: false,
      timeout: 120_000,
    },
    {
      command: "VITE_DEV_BACKEND_URL=http://127.0.0.1:8001 npx vite --port 5174 --strictPort",
      url: "http://localhost:5174",
      reuseExistingServer: false,
    },
    {
      command: "VITE_DEV_BACKEND_URL=http://127.0.0.1:8002 npx vite --port 5175 --strictPort",
      url: "http://localhost:5175",
      reuseExistingServer: false,
    },
  ],
});
