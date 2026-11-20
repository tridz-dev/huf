import { test, expect } from '@playwright/test';
import { goto, waitForContent, mockOfflineApis } from './helpers';

test.describe('Data', () => {
  test.beforeEach(async ({ page }) => {
    await mockOfflineApis(page);
  });

  test('data page renders', async ({ page }) => {
    await goto(page, '/data');
    await waitForContent(page);
    // The page was redesigned as "Tables"; the empty state confirms the mocked
    // (empty) data rendered.
    await expect(page.getByRole('heading', { name: 'Tables', exact: true })).toBeVisible();
    await expect(page.getByTestId('tables-empty')).toBeVisible();
    await expect(page.getByText('No tables yet')).toBeVisible();
  });
});
