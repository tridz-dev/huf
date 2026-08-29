import { defineConfig, devices } from '@playwright/test';
import base from './playwright.config';

// Nightly/develop-only cross-browser pass (GOAL.md §9 "nightly hardening",
// §19 Tier 2 "develop/nightly ... cross-browser"). Extends the fast,
// Chromium-only offline suite (playwright.config.ts) that PR CI depends on
// staying quick — this file adds Firefox and WebKit on top of it rather
// than widening the default `projects` list PRs run against.
//
// visual-regression.spec.ts is excluded: its baseline screenshots are
// Chromium-specific (`*-chromium-darwin.png`), and visual regression is
// inherently single-browser by design (GOAL.md's visual/design-parity
// guidance targets one canonical rendering surface, not cross-browser
// pixel parity). Cross-browser coverage here is about behavioural
// (non-screenshot) regressions in Firefox/WebKit.
export default defineConfig(base, {
  testIgnore: [...(Array.isArray(base.testIgnore) ? base.testIgnore : base.testIgnore ? [base.testIgnore] : []), /visual-regression\.spec\.ts$/],
  projects: [
    { name: 'chromium', use: { ...devices['Desktop Chrome'] } },
    { name: 'firefox', use: { ...devices['Desktop Firefox'] } },
    { name: 'webkit', use: { ...devices['Desktop Safari'] } },
  ],
});
