import { test, expect } from '@playwright/test';
import { goto, waitForContent, mockOfflineApis } from './helpers';

test.describe('Settings, Users & Roles', () => {
  test.beforeEach(async ({ page }) => {
    await mockOfflineApis(page);
  });

  test('users page renders', async ({ page }) => {
    // /users now redirects to /members (People view) — see App.tsx.
    await goto(page, '/users');
    await waitForContent(page);
    await expect(page).toHaveURL(/\/huf\/members$/);
    await expect(page.getByRole('heading', { name: 'Members' })).toBeVisible();
    await expect(page.getByRole('tab', { name: 'People' })).toBeVisible();
  });

  test('roles page renders', async ({ page }) => {
    // /roles now redirects to /members?view=roles (Roles & access view,
    // embedded — it does not render its own heading there) — see App.tsx
    // and RolesPage.tsx's `embedded` prop.
    await goto(page, '/roles');
    await waitForContent(page);
    await expect(page).toHaveURL(/\/huf\/members\?view=roles$/);
    await expect(page.getByRole('heading', { name: 'Members' })).toBeVisible();
    await expect(page.getByRole('button', { name: 'Create role' })).toBeVisible();
  });

  test('playground page renders', async ({ page }) => {
    // /console now redirects to /playground — see App.tsx.
    await goto(page, '/console');
    await waitForContent(page);
    await expect(page).toHaveURL(/\/huf\/playground$/);
  });

  test('/settings renders the agent settings page (no longer a 404)', async ({ page }) => {
    // /settings now routes to AgentSettingsPage — see App.tsx.
    await goto(page, '/settings');
    await waitForContent(page);
    await expect(page.getByRole('heading', { name: 'Agent settings' })).toBeVisible();
  });
});
