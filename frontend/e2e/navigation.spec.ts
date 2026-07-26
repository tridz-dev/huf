import { test, expect } from '@playwright/test';
import { goto, waitForContent, mockOfflineApis } from './helpers';

test.describe('Navigation & shell', () => {
  test.beforeEach(async ({ page }) => {
    await mockOfflineApis(page);
  });

  test('sidebar renders with all nav groups', async ({ page }) => {
    await goto(page, '/dashboard');
    await waitForContent(page);

    for (const label of ['Dashboard', 'Flows', 'Data', 'Knowledge', 'Chat', 'Executions', 'Users']) {
      await expect(page.getByRole('link', { name: label, exact: true }).first()).toBeVisible();
    }
    // Agents link carries a numeric count badge, so its name is e.g. "Agents 0".
    await expect(page.getByRole('link', { name: /^Agents/ }).first()).toBeVisible();
  });

  test('settings collapsible reveals settings pages', async ({ page }) => {
    await goto(page, '/dashboard');
    await waitForContent(page);

    await page.getByRole('button', { name: 'Settings' }).click();
    for (const label of ['AI Providers', 'Models', 'Integrations', 'MCP Servers', 'Roles']) {
      await expect(page.getByRole('link', { name: label, exact: true })).toBeVisible();
    }
  });

  test('sidebar navigation reaches core pages', async ({ page }) => {
    await goto(page, '/dashboard');
    await waitForContent(page);

    await page.getByRole('link', { name: /^Agents/ }).first().click();
    await expect(page).toHaveURL(/\/huf\/agents$/);

    await page.getByRole('link', { name: 'Executions', exact: true }).first().click();
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
