import { test, expect } from '@playwright/test';

test.describe('Dashboard', () => {
  test('loads with metrics and tabs', async ({ page }) => {
    // The root path ('') now renders HubSimplePage, a distinct landing page
    // (see App.tsx: path="/" -> HubSimplePage, path="/dashboard" -> HomePage
    // with the metrics/tabs dashboard). UnifiedLayout also defaults the
    // sidebar to collapsed icon-only on '/' specifically
    // (defaultOpen = location.pathname !== '/'), which is why nav links had
    // no accessible text when this test navigated to root.
    await page.goto('dashboard');

    await expect(page.getByRole('heading', { name: 'Dashboard' })).toBeVisible();
    // Metric labels are sentence case in the current UI (HomePage.tsx),
    // not the title case the spec previously assumed.
    await expect(page.getByText('Total agent runs')).toBeVisible();
    await expect(page.getByText('Success rate')).toBeVisible();

    // Dashboard tabs: Agents / Flows / Executions
    const agentsTab = page.getByRole('tab', { name: /^Agents$/i }).or(page.getByText('Agents', { exact: true }));
    await expect(agentsTab.first()).toBeVisible();
  });

  test('sidebar navigation reaches core pages', async ({ page }) => {
    await page.goto('dashboard');

    await page.getByRole('link', { name: 'Agents', exact: true }).click();
    await expect(page).toHaveURL(/\/huf\/agents$/);

    await page.getByRole('link', { name: 'Executions' }).click();
    await expect(page).toHaveURL(/\/huf\/executions$/);

    await page.getByRole('link', { name: 'Chat', exact: true }).click();
    await expect(page).toHaveURL(/\/huf\/chat/);
  });
});
