import { test, expect } from '@playwright/test';
import { goto, waitForContent, mockOfflineApis } from './helpers';

test.describe('Settings, Users & Roles', () => {
  test.beforeEach(async ({ page }) => {
    await mockOfflineApis(page);
  });

  test('users page renders', async ({ page }) => {
    await goto(page, '/users');
    await waitForContent(page);
    await expect(page.getByText('Manage who has access to Huf and what they can do.')).toBeVisible();
  });

  test('roles page renders', async ({ page }) => {
    await goto(page, '/roles');
    await waitForContent(page);
    await expect(page.getByRole('heading', { name: /Roles/i }).first()).toBeVisible();
  });

  test('console page renders', async ({ page }) => {
    await goto(page, '/console');
    await waitForContent(page);
    await expect(page.getByRole('heading', { name: 'Console' })).toBeVisible();
  });

  test('/settings route renders the 404 page (no settings page exists)', async ({ page }) => {
    await goto(page, '/settings');
    await waitForContent(page);
    await expect(page.getByText('Page Not Found')).toBeVisible();
  });
});
