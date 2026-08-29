import { test, expect } from '@playwright/test';
import { goto, waitForContent, mockOfflineApis } from './helpers';

test.describe('Executions', () => {
  test.beforeEach(async ({ page }) => {
    await mockOfflineApis(page);
  });

  test('executions page renders', async ({ page }) => {
    await goto(page, '/executions');
    await waitForContent(page);

    await expect(page.getByRole('heading', { name: 'Executions', exact: true })).toBeVisible();
    // No subtitle band exists (see PageFrame) — the empty state confirms
    // the mocked (empty) data actually rendered.
    await expect(page.getByRole('heading', { name: 'No executions' })).toBeVisible();
  });
});
