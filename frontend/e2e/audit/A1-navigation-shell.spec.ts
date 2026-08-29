import { test, expect, Page } from '@playwright/test';
import path from 'path';
import { goto, waitForContent, mockOfflineApis } from '../helpers';

const TODAY = new Date().toISOString().slice(0, 10);
const SCREENSHOT_DIR = path.resolve(process.cwd(), `test-evidence/${TODAY}/screenshots/A1`);
let seq = 0;

async function screenshot(page: Page, name: string) {
  seq += 1;
  await page.screenshot({
    path: path.join(SCREENSHOT_DIR, `${String(seq).padStart(2, '0')}-${name}.png`),
    fullPage: true,
  });
}

test.describe('A1 — Navigation & shell', () => {
  test.beforeEach(async ({ page }) => {
    await mockOfflineApis(page);
  });

  test('dashboard shell with sidebar', async ({ page }) => {
    await goto(page, '/dashboard');
    await waitForContent(page);

    await expect(page.getByRole('heading', { name: 'Dashboard' })).toBeVisible();
    await expect(page.getByRole('link', { name: /^Agents/ }).first()).toBeVisible();
    await screenshot(page, 'dashboard-shell');
  });

  test('settings collapsible expanded', async ({ page }) => {
    await goto(page, '/dashboard');
    await waitForContent(page);

    // Settings is a second-level rail (see app-sidebar.tsx settingsNavGroups),
    // and the item labels changed: 'AI Providers' + 'Models' merged into
    // 'AI providers & models', and MCP is now lowercase 'MCP servers'.
    await page.getByRole('button', { name: 'Settings' }).click();
    await expect(page.getByRole('link', { name: 'AI providers & models', exact: true })).toBeVisible();
    await expect(page.getByRole('link', { name: 'MCP servers', exact: true })).toBeVisible();
    await screenshot(page, 'sidebar-settings-expanded');
  });

  test('navigate across core pages', async ({ page }) => {
    await goto(page, '/dashboard');
    await waitForContent(page);

    await page.getByRole('link', { name: /^Agents/ }).first().click();
    await expect(page).toHaveURL(/\/huf\/agents$/);
    await waitForContent(page);
    await screenshot(page, 'navigated-agents');

    await page.getByRole('link', { name: 'Chat', exact: true }).first().click();
    await expect(page).toHaveURL(/\/huf\/chat/);
    await waitForContent(page);
    await screenshot(page, 'navigated-chat');
  });
});
