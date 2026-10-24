import { defineConfig, devices } from '@playwright/test';

// Offline/static suite: runs against the Vite dev server with NO Frappe
// backend. Specs mock `/api/**` at the network layer (see e2e/helpers.ts).
// Deployed specs under e2e/deployed/ are excluded — they run via
// playwright.deployed.config.ts against a live site.
// Local override: PW_PORT=<n> serves the e2e dev server on another port when 8080 is taken.
const PORT = process.env.PW_PORT || '8080';
const PORT_FLAGS = process.env.PW_PORT ? ` --port ${PORT} --strictPort` : '';

export default defineConfig({
  testDir: './e2e',
  testMatch: /\.spec\.ts$/,
  // Visual baselines are committed per-platform (-darwin only). On other
  // platforms (CI linux) skip them unless explicitly opted in, otherwise every
  // toHaveScreenshot() fails writing a missing baseline.
  // Run with UPDATE_SNAPSHOTS=1 (and --update-snapshots) to (re)generate.
  testIgnore: process.env.UPDATE_SNAPSHOTS || process.platform === 'darwin'
    ? /deployed/
    : [/deployed/, /visual-regression/],
  fullyParallel: true,
  retries: 1,
  timeout: 15000,
  reporter: [['list'], ['html', { open: 'never', outputFolder: 'e2e-report' }]],
  use: {
    // Trailing slash matters: specs navigate with paths relative to /huf/
    // (the React router basename), resolved by the goto() helper.
    baseURL: `http://localhost:${PORT}/huf/`,
    headless: true,
    screenshot: 'only-on-failure',
    trace: 'retain-on-failure',
  },
  projects: [
    {
      name: 'chromium',
      // Local override only: PW_CHANNEL=chrome drives the installed system Chrome
      // instead of the downloaded Playwright chromium. Unset (CI default) = unchanged.
      use: { ...devices['Desktop Chrome'], ...(process.env.PW_CHANNEL ? { channel: process.env.PW_CHANNEL } : {}) },
    },
  ],
  webServer: {
    // vite.config.ts's `base` is '/assets/huf/frontend/' (the production
    // deploy path served by Frappe/nginx) — a plain `vite dev` only serves
    // index.html under that same base, and that base prefix also collides
    // with the dev-server's own `/assets/*` backend proxy rule (see
    // proxyOptions.ts), producing a 500 instead of the app. Override the
    // base for e2e only, via CLI flag (same mechanism `yarn build` already
    // uses for its own base override), so the fresh server matches
    // `baseURL` below without touching vite.config.ts's default.
    command: `npm run dev -- --base=/huf/${PORT_FLAGS}`,
    url: `http://localhost:${PORT}/huf/`,
    reuseExistingServer: true,
    timeout: 120000,
  },
});
