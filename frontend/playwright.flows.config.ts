import { defineConfig, devices } from '@playwright/test';

// Flow-builder e2e suite: runs against a live Frappe site serving the built
// HUF app, authenticating with a Frappe API token instead of a logged-in
// session cookie (verified: `Authorization: token ...` alone is sufficient
// for both the API and the SPA's document requests on this bench).
//
// Trailing slash matters: relative paths in tests ('', 'flows', 'flows/x')
// are resolved against this as a directory, not the origin root.
const baseURL = process.env.FLOW_E2E_BASE_URL || 'http://127.0.0.1:8102/huf/';

const API_TOKEN = process.env.FLOW_E2E_API_TOKEN || '245085c4b670453:0a099501ac09c1d';

export default defineConfig({
  testDir: './e2e/deployed/flow',
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  workers: 1,
  timeout: 120000,
  expect: { timeout: 15000 },
  reporter: [['list'], ['html', { open: 'never', outputFolder: 'e2e-report-flows' }]],
  use: {
    baseURL,
    headless: process.env.HEADED !== 'true',
    extraHTTPHeaders: {
      Authorization: `token ${API_TOKEN}`,
    },
    screenshot: 'only-on-failure',
    trace: 'retain-on-failure',
    video: 'retain-on-failure',
  },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],
});
