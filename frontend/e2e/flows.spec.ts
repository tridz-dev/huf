import { test, expect } from '@playwright/test';
import { goto, waitForContent, mockOfflineApis } from './helpers';

test.describe('Flows', () => {
  test.beforeEach(async ({ page }) => {
    await mockOfflineApis(page);
  });

  test('flows list renders', async ({ page }) => {
    await goto(page, '/flows');
    await waitForContent(page);

    await expect(page.getByRole('heading', { name: 'Flows' })).toBeVisible();
    await expect(page.getByText('Design and orchestrate agent workflows.')).toBeVisible();
  });
});
