import { defineConfig, devices } from '@playwright/test';

// Deployed suite: runs against a live Frappe site serving the built HUF app.
// Serial execution, generous timeouts, full artifacts on every test.
//
// Trailing slash matters: relative paths in tests ('', 'agents', 'chat') are
// resolved against this as a directory, not the origin root.
const baseURL =
  process.env.BASE_URL || process.env.E2E_BASE_URL || 'http://192.168.97.6:8000/huf/';

export default defineConfig({
  testDir: './e2e/deployed',
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  retries: 0,
  workers: 1,
  timeout: 120000,
  reporter: [['list'], ['html', { open: 'never', outputFolder: 'e2e-report-deployed' }]],
  use: {
    baseURL,
    headless: process.env.HEADED !== 'true',
    screenshot: 'on',
    trace: 'on',
    video: 'on-first-retry',
  },
  projects: [
    { name: 'setup', testMatch: /auth\.setup\.ts/ },
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'], storageState: 'e2e/.auth/user.json' },
      dependencies: ['setup'],
    },
  ],
});
