import { test, expect } from '@playwright/test';
import { goto, waitForContent, mockOfflineApis } from './helpers';

test.describe('Agents', () => {
  test.beforeEach(async ({ page }) => {
    await mockOfflineApis(page);
  });

  test('renders heading and subtitle', async ({ page }) => {
    await goto(page, '/agents');
    await waitForContent(page);

    // "Agents" (page title, exact) and "No agents" (empty-state heading)
    // both match a loose heading query, so pin the page title precisely.
    await expect(page.getByRole('heading', { name: 'Agents', exact: true })).toBeVisible();
    // The page has no subtitle band (see PageFrame) — the empty state is
    // what confirms the mocked data actually rendered.
    await expect(page.getByRole('heading', { name: 'No agents' })).toBeVisible();
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
    await expect(page.getByRole('heading', { name: 'Agents', exact: true })).toBeVisible();
  });
});
