import { test, expect } from '@playwright/test';
import { goto, waitForContent, mockOfflineApis } from './helpers';

test.describe('Models & Providers', () => {
  test.beforeEach(async ({ page }) => {
    await mockOfflineApis(page);
  });

  test('models page renders', async ({ page }) => {
    await goto(page, '/models');
    await waitForContent(page);
    // The page has no subtitle band (see PageFrame) — assert the page title
    // and the empty-state heading that proves the mocked data rendered.
    await expect(page.getByRole('heading', { name: 'Models', exact: true })).toBeVisible();
    await expect(page.getByRole('heading', { name: 'No models' })).toBeVisible();
  });

  test('providers page renders', async ({ page }) => {
    await goto(page, '/providers');
    await waitForContent(page);
    await expect(page.getByRole('heading', { name: 'AI providers', exact: true })).toBeVisible();
    await expect(page.getByRole('heading', { name: 'No providers' })).toBeVisible();
  });
});
