import { defineConfig, devices } from '@playwright/test';

// Offline/static suite: runs against the Vite dev server with NO Frappe
// backend. Specs mock `/api/**` at the network layer (see e2e/helpers.ts).
// Deployed specs under e2e/deployed/ are excluded — they run via
// playwright.deployed.config.ts against a live site.
export default defineConfig({
  testDir: './e2e',
  testMatch: /\.spec\.ts$/,
  testIgnore: /deployed/,
  fullyParallel: true,
  retries: 1,
  timeout: 15000,
  reporter: [['list'], ['html', { open: 'never', outputFolder: 'e2e-report' }]],
  use: {
    // Trailing slash matters: specs navigate with paths relative to /huf/
    // (the React router basename), resolved by the goto() helper.
    baseURL: 'http://localhost:8080/huf/',
    headless: true,
    screenshot: 'only-on-failure',
    trace: 'retain-on-failure',
  },
  projects: [
    { name: 'chromium', use: { ...devices['Desktop Chrome'] } },
  ],
  webServer: {
    command: 'yarn dev',
    url: 'http://localhost:8080',
    reuseExistingServer: true,
    timeout: 120000,
  },
});
