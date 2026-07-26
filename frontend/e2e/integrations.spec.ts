import { test, expect } from '@playwright/test';
import { goto, waitForContent, mockOfflineApis } from './helpers';

test.describe('Integrations, Knowledge & MCP', () => {
  test.beforeEach(async ({ page }) => {
    await mockOfflineApis(page);
  });

  test('integrations page renders', async ({ page }) => {
    await goto(page, '/integrations');
    await waitForContent(page);
    await expect(
      page.getByText('Connect external services like Slack, Telegram, GitHub, and Google Workspace'),
    ).toBeVisible();
  });

  test('integration services page renders', async ({ page }) => {
    await goto(page, '/integration-services');
    await waitForContent(page);
    await expect(
      page.getByText('Define integration service catalogs and credential schemas used by Integration Settings'),
    ).toBeVisible();
  });

  test('knowledge sources page renders', async ({ page }) => {
    await goto(page, '/knowledge');
    await waitForContent(page);
    await expect(page.getByText('Manage knowledge sources for your AI agents')).toBeVisible();
  });

  test('mcp servers page renders', async ({ page }) => {
    await goto(page, '/mcp');
    await waitForContent(page);
    await expect(page.getByRole('heading', { name: 'MCP Servers' })).toBeVisible();
  });
});
