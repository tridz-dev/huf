import { test, expect } from '@playwright/test';

test.describe('Agents', () => {
  test('agents list renders and links to a form', async ({ page }) => {
    await page.goto('agents');

    await expect(page.getByText('Manage your AI agents and their configurations')).toBeVisible();

    // At least one agent card should be present on a bench that already has agents.
    const firstAgentCard = page.locator('a, [role="button"], div').filter({ hasText: /Test New UI/i }).first();
    if (await firstAgentCard.count()) {
      await firstAgentCard.click();
      await expect(page).toHaveURL(/\/huf\/agents\//);
      await expect(page.getByRole('tab', { name: 'General' })).toBeVisible();
    }
  });
});
