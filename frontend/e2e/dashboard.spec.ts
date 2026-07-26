import { test, expect } from '@playwright/test';
import { goto, waitForContent, mockOfflineApis } from './helpers';

test.describe('Dashboard', () => {
  test.beforeEach(async ({ page }) => {
    await mockOfflineApis(page);
  });

  test('renders heading and metric cards', async ({ page }) => {
    await goto(page, '/dashboard');
    await waitForContent(page);

    await expect(page.getByRole('heading', { name: 'Dashboard' })).toBeVisible();
    // Metric labels render from static config even when the API returns no rows.
    await expect(page.getByText('Total Agent Runs')).toBeVisible();
    await expect(page.getByText('Success Rate')).toBeVisible();
  });

  test('renders dashboard tabs', async ({ page }) => {
    await goto(page, '/dashboard');
    await waitForContent(page);

    const agentsTab = page
      .getByRole('tab', { name: /^Agents$/i })
      .or(page.getByText('Agents', { exact: true }));
    await expect(agentsTab.first()).toBeVisible();
  });
});
