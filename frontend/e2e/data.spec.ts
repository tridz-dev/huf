import { test, expect } from '@playwright/test';
import { goto, waitForContent, mockOfflineApis } from './helpers';

test.describe('Data', () => {
  test.beforeEach(async ({ page }) => {
    await mockOfflineApis(page);
  });

  test('data page renders', async ({ page }) => {
    await goto(page, '/data');
    await waitForContent(page);
    // The page has no subtitle band (see PageFrame); the empty state's
    // description is what confirms the mocked (empty) data rendered.
    await expect(page.getByRole('heading', { name: 'Data', exact: true })).toBeVisible();
    await expect(page.getByText('Create your first table to start managing structured data.')).toBeVisible();
  });
});
