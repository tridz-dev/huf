import { test, expect } from '@playwright/test';
import { goto, waitForContent, mockOfflineApis } from './helpers';

test.describe('Prompts', () => {
  test.beforeEach(async ({ page }) => {
    await mockOfflineApis(page);
  });

  test('agent prompts page renders', async ({ page }) => {
    await goto(page, '/prompts');
    await waitForContent(page);
    await expect(page.getByText('Manage shared prompt templates for agents')).toBeVisible();
  });

  test('summary prompts page renders', async ({ page }) => {
    await goto(page, '/summary-prompts');
    await waitForContent(page);
    await expect(page.getByText('Manage shared summary prompt templates for agents')).toBeVisible();
  });
});
