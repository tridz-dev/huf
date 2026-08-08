import { test, expect } from '@playwright/test';
import { gotoHuf, waitForSpinner } from './helpers';

// Core pages and a stable selector that proves each one rendered on the live
// site. Runs with the saved storageState (see auth.setup.ts).
const CORE_PAGES: Array<{ path: string; name: string; text: RegExp }> = [
  { path: '/dashboard', name: 'Dashboard', text: /Dashboard/i },
  { path: '/agents', name: 'Agents', text: /Agents/i },
  { path: '/prompts', name: 'Agent Prompts', text: /prompt templates for agents/i },
  { path: '/summary-prompts', name: 'Summary Prompts', text: /summary prompt templates/i },
  { path: '/flows', name: 'Flows', text: /Flows/i },
  { path: '/data', name: 'Data', text: /custom data tables/i },
  { path: '/knowledge', name: 'Knowledge', text: /knowledge sources/i },
  { path: '/executions', name: 'Executions', text: /Executions/i },
  { path: '/models', name: 'Models', text: /models and their capabilities/i },
  { path: '/providers', name: 'AI Providers', text: /Connect AI providers/i },
  { path: '/mcp', name: 'MCP Servers', text: /MCP Servers/i },
  { path: '/integrations', name: 'Integrations', text: /external services/i },
  { path: '/users', name: 'Users', text: /who has access/i },
  { path: '/roles', name: 'Roles', text: /Roles/i },
];

test.describe('Deployed smoke — core pages render', () => {
  for (const { path, name, text } of CORE_PAGES) {
    test(`${name} (${path}) renders`, async ({ page }) => {
      await gotoHuf(page, path);
      await waitForSpinner(page);
      await expect(page.getByText(text).first()).toBeVisible({ timeout: 20000 });
    });
  }

  test('Chat renders the message composer', async ({ page }) => {
    await gotoHuf(page, '/chat');
    await waitForSpinner(page);
    await expect(
      page.getByPlaceholder('Type your message...').or(page.locator('textarea').first()),
    ).toBeVisible({ timeout: 20000 });
  });
});
