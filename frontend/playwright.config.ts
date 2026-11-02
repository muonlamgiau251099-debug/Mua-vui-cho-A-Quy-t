import { defineConfig, devices } from "@playwright/test";

// E2E chạy trên bản build production qua Caddy (deploy/docker-compose.yml):
//   docker compose -f deploy/docker-compose.yml --env-file deploy/.env up -d --build
//   E2E_BASE_URL=http://localhost:8080 npm run e2e
export default defineConfig({
  testDir: "./e2e",
  timeout: 5 * 60_000,
  expect: { timeout: 15_000 },
  fullyParallel: false,
  workers: 1,
  reporter: [["list"], ["html", { open: "never" }]],
  use: {
    baseURL: process.env.E2E_BASE_URL ?? "http://localhost:8080",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
});
