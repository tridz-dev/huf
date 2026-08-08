import { test, expect } from '@playwright/test';
import { goto, waitForContent, mockOfflineApis } from './helpers';

test.describe('Executions', () => {
  test.beforeEach(async ({ page }) => {
    await mockOfflineApis(page);
  });

  test('executions page renders', async ({ page }) => {
    await goto(page, '/executions');
    await waitForContent(page);

    await expect(page.getByRole('heading', { name: 'Executions' })).toBeVisible();
    await expect(page.getByText('Inspect agent runs and their results.')).toBeVisible();
  });
});
