import { test, expect } from '@playwright/test';
import { goto, waitForContent, mockOfflineApis } from './helpers';

test.describe('Models & Providers', () => {
  test.beforeEach(async ({ page }) => {
    await mockOfflineApis(page);
  });

  test('models page renders', async ({ page }) => {
    await goto(page, '/models');
    await waitForContent(page);
    await expect(page.getByText('Manage AI models and their capabilities')).toBeVisible();
  });

  test('providers page renders', async ({ page }) => {
    await goto(page, '/providers');
    await waitForContent(page);
    await expect(page.getByText('Connect AI providers and external services')).toBeVisible();
  });
});
