import { test, expect } from '@playwright/test';
import { goto, waitForContent, mockOfflineApis } from './helpers';

test.describe('Agents', () => {
  test.beforeEach(async ({ page }) => {
    await mockOfflineApis(page);
  });

  test('renders heading and subtitle', async ({ page }) => {
    await goto(page, '/agents');
    await waitForContent(page);

    await expect(page.getByRole('heading', { name: 'Agents' })).toBeVisible();
    await expect(page.getByText('Create and manage your AI agents.')).toBeVisible();
  });

  test('filter bar is interactive', async ({ page }) => {
    await goto(page, '/agents');
    await waitForContent(page);

    // Search input accepts text without crashing the page.
    const search = page.getByPlaceholder(/search/i).first();
    if (await search.count()) {
      await search.fill('test agent');
      await expect(search).toHaveValue('test agent');
    }
    await expect(page.getByRole('heading', { name: 'Agents' })).toBeVisible();
  });
});
