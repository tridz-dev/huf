import { test, expect } from '@playwright/test';

test.describe('Dashboard', () => {
  test('loads with metrics and tabs', async ({ page }) => {
    await page.goto('');

    await expect(page.getByRole('heading', { name: 'Dashboard' })).toBeVisible();
    await expect(page.getByText('Total Agent Runs')).toBeVisible();
    await expect(page.getByText('Success Rate')).toBeVisible();

    // Dashboard tabs: Agents / Flows / Executions
    const agentsTab = page.getByRole('tab', { name: /^Agents$/i }).or(page.getByText('Agents', { exact: true }));
    await expect(agentsTab.first()).toBeVisible();
  });

  test('sidebar navigation reaches core pages', async ({ page }) => {
    await page.goto('');

    await page.getByRole('link', { name: 'Agents', exact: true }).click();
    await expect(page).toHaveURL(/\/huf\/agents$/);

    await page.getByRole('link', { name: 'Executions' }).click();
    await expect(page).toHaveURL(/\/huf\/executions$/);

    await page.getByRole('link', { name: 'Chat', exact: true }).click();
    await expect(page).toHaveURL(/\/huf\/chat/);
  });
});
