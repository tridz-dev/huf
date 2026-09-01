import { test, expect } from '@playwright/test';
import { goto, waitForContent, mockOfflineApis } from './helpers';

test.describe('Navigation & shell', () => {
  test.beforeEach(async ({ page }) => {
    await mockOfflineApis(page);
  });

  test('sidebar renders with all nav groups', async ({ page }) => {
    await goto(page, '/dashboard');
    await waitForContent(page);

    // 'Data'/'Knowledge' were renamed to 'Tables'/'Sources' (see
    // app-sidebar.tsx libraryNavItems). 'Users' no longer lives in the main
    // nav at all — 'Members' now only appears inside the Settings rail (see
    // the 'settings collapsible reveals settings pages' test below).
    for (const label of ['Dashboard', 'Tables', 'Sources', 'Chat']) {
      await expect(page.getByRole('link', { name: label, exact: true }).first()).toBeVisible();
    }
    // Agents link carries a numeric count badge, so its name is e.g. "Agents 0".
    await expect(page.getByRole('link', { name: /^Agents/ }).first()).toBeVisible();
    // Flows and Executions carry an "Experimental" badge (decorative icon
    // with an aria-label), which is folded into the link's accessible name —
    // match with a prefix regex instead of an exact string.
    await expect(page.getByRole('link', { name: /^Flows/ }).first()).toBeVisible();
  });

  test('settings collapsible reveals settings pages', async ({ page }) => {
    await goto(page, '/dashboard');
    await waitForContent(page);

    // Settings is a second-level rail that replaces the primary nav, not an
    // accordion (see app-sidebar.tsx settingsNavGroups) — item labels also
    // changed ('AI Providers' + 'Models' merged into 'AI providers & models',
    // 'Roles' became part of 'Members').
    await page.getByRole('button', { name: 'Settings' }).click();
    for (const label of ['AI providers & models', 'MCP servers', 'Integrations', 'Members']) {
      await expect(page.getByRole('link', { name: label, exact: true })).toBeVisible();
    }
  });

  test('sidebar navigation reaches core pages', async ({ page }) => {
    await goto(page, '/dashboard');
    await waitForContent(page);

    await page.getByRole('link', { name: /^Agents/ }).first().click();
    await expect(page).toHaveURL(/\/huf\/agents$/);

    // Executions carries an "Experimental" badge folded into its accessible
    // name — match with a prefix regex instead of an exact string.
    await page.getByRole('link', { name: /^Executions/ }).first().click();
    await expect(page).toHaveURL(/\/huf\/executions$/);

    await page.getByRole('link', { name: 'Chat', exact: true }).first().click();
    await expect(page).toHaveURL(/\/huf\/chat/);
  });

  test('unknown route renders the 404 page', async ({ page }) => {
    await goto(page, '/definitely-not-a-page');
    await waitForContent(page);
    await expect(page.getByRole('heading', { name: '404' })).toBeVisible();
    await expect(page.getByText('Page Not Found')).toBeVisible();
  });
});
