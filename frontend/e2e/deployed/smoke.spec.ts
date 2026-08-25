import { test, expect } from '@playwright/test';
import { gotoHuf, waitForSpinner } from './helpers';

// Core pages and a stable selector that proves each one rendered on the live
// site. Runs with the saved storageState (see auth.setup.ts).
const CORE_PAGES: Array<{ path: string; name: string; text: RegExp }> = [
  { path: '/dashboard', name: 'Dashboard', text: /Dashboard/i },
  { path: '/agents', name: 'Agents', text: /Agents/i },
  // Page subtitle bands were removed platform-wide (see PageFrame.tsx: "no
  // subtitle band" — purpose copy moved to meta/tooltip/empty-state), so
  // these now assert on the page title (h1) or another stable, page-specific
  // element instead of copy that no longer exists.
  { path: '/prompts', name: 'Agent Prompts', text: /Prompts/i },
  { path: '/summary-prompts', name: 'Summary Prompts', text: /Summarization/i },
  { path: '/flows', name: 'Flows', text: /Flows/i },
  { path: '/data', name: 'Data', text: /^Data$/i },
  { path: '/knowledge', name: 'Knowledge', text: /knowledge sources/i },
  { path: '/executions', name: 'Executions', text: /Executions/i },
  { path: '/models', name: 'Models', text: /^Models$/i },
  { path: '/providers', name: 'AI Providers', text: /AI providers/i },
  { path: '/mcp', name: 'MCP Servers', text: /MCP Servers/i },
  // Integrations listing has no page-level heading (headerActions render the
  // "Add Integration" control, not a title); "Service catalog" is the
  // stable, page-specific element that only renders here.
  { path: '/integrations', name: 'Integrations', text: /Service catalog/i },
  // /users redirects to /members (see App.tsx), which renders "Members".
  { path: '/users', name: 'Users', text: /Members/i },
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
