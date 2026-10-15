import { defineConfig } from "@playwright/test";

// Loads the built extension (dist/) into Chromium and talks to a real backend
// started on localhost:8000 with the simulated AI provider (demo mode).
export default defineConfig({
  testDir: "./e2e",
  timeout: 90_000,
  workers: 1,
  reporter: [["list"]],
  webServer: {
    command: "E2E_RESET=1 E2E_AI=mock PORT=8000 E2E_DATABASE_URL=postgresql+psycopg://bidgenie:bidgenie@localhost:5432/bidgenie_e2e ../scripts/e2e-backend.sh",
    url: "http://127.0.0.1:8000/health",
    reuseExistingServer: false,
    timeout: 120_000,
  },
});
