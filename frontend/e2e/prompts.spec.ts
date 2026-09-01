import { test, expect } from '@playwright/test';
import { goto, waitForContent, mockOfflineApis } from './helpers';

test.describe('Prompts', () => {
  test.beforeEach(async ({ page }) => {
    await mockOfflineApis(page);
  });

  test('agent prompts page renders', async ({ page }) => {
    await goto(page, '/prompts');
    await waitForContent(page);
    // The page has no subtitle band (see PageFrame) — assert the page title
    // and the empty-state heading that proves the mocked data rendered.
    await expect(page.getByRole('heading', { name: 'Prompts', exact: true })).toBeVisible();
    await expect(page.getByRole('heading', { name: 'No prompts' })).toBeVisible();
  });

  test('summary prompts page renders', async ({ page }) => {
    await goto(page, '/summary-prompts');
    await waitForContent(page);
    await expect(page.getByRole('heading', { name: 'No summary prompts' })).toBeVisible();
  });
});
