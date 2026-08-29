import { test, expect } from '@playwright/test';
import { goto, waitForContent, mockOfflineApis } from './helpers';

test.describe('Flows', () => {
  test.beforeEach(async ({ page }) => {
    await mockOfflineApis(page);
  });

  test('flows list renders', async ({ page }) => {
    await goto(page, '/flows');
    await waitForContent(page);

    // "Flows" (page title, exact) and "No flows" (empty-state heading) both
    // match a loose heading query — pin the page title precisely.
    await expect(page.getByRole('heading', { name: 'Flows', exact: true })).toBeVisible();
    // No subtitle band exists (see PageFrame) — the empty state confirms
    // the mocked data actually rendered.
    await expect(page.getByRole('heading', { name: 'No flows' })).toBeVisible();
  });
});
