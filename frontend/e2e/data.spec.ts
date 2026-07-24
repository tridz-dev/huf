import { test, expect } from '@playwright/test';
import { goto, waitForContent, mockOfflineApis } from './helpers';

test.describe('Data', () => {
  test.beforeEach(async ({ page }) => {
    await mockOfflineApis(page);
  });

  test('data page renders', async ({ page }) => {
    await goto(page, '/data');
    await waitForContent(page);
    await expect(page.getByText('Create and manage custom data tables')).toBeVisible();
  });
});
