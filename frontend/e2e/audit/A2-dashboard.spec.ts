import { test, expect, Page } from '@playwright/test';
import path from 'path';
import { goto, waitForContent, mockOfflineApis } from '../helpers';

const TODAY = new Date().toISOString().slice(0, 10);
const SCREENSHOT_DIR = path.resolve(process.cwd(), `test-evidence/${TODAY}/screenshots/A2`);
let seq = 0;

async function screenshot(page: Page, name: string) {
  seq += 1;
  await page.screenshot({
    path: path.join(SCREENSHOT_DIR, `${String(seq).padStart(2, '0')}-${name}.png`),
    fullPage: true,
  });
}

const NOW = Date.now();
const iso = (msAgo: number) => new Date(NOW - msAgo).toISOString().replace('T', ' ').slice(0, 19);

/** Agent Run rows so the dashboard metrics show realistic numbers. */
const AGENT_RUNS = [
  { name: 'RUN-0001', status: 'Success', start_time: iso(3600_000), end_time: iso(3500_000), cost: 0.012, agent: 'Support Bot' },
  { name: 'RUN-0002', status: 'Success', start_time: iso(7200_000), end_time: iso(7100_000), cost: 0.031, agent: 'Support Bot' },
  { name: 'RUN-0003', status: 'Failed', start_time: iso(86400_000), end_time: iso(86300_000), cost: 0.004, agent: 'Researcher' },
  { name: 'RUN-0004', status: 'Success', start_time: iso(90000_000), end_time: iso(89900_000), cost: 0.018, agent: 'Researcher' },
];

const AGENTS = [
  {
    name: 'AGT-0001', agent_name: 'Support Bot', description: 'Answers customer questions',
    provider: 'OpenAI', model: 'gpt-4o', disabled: 0, allow_chat: 1, prompt_mode: 'Template',
    enable_multi_run: 0, enable_prompt_caching: 1, allow_guest: 0, provider_brand: 'openai',
    last_run: iso(3600_000), total_run: 42, agent_color: '#4F46E5', modified: iso(3600_000),
  },
  {
    name: 'AGT-0002', agent_name: 'Researcher', description: 'Deep research agent',
    provider: 'Anthropic', model: 'claude-sonnet-4', disabled: 0, allow_chat: 1, prompt_mode: 'Prompt',
    enable_multi_run: 1, enable_prompt_caching: 0, allow_guest: 0, provider_brand: 'anthropic',
    last_run: iso(86400_000), total_run: 17, agent_color: '#0EA5E9', modified: iso(86400_000),
  },
];

async function mockDashboardData(page: Page) {
  // Generic Agent route registered first; the Agent Run route is registered
  // after so it wins (Playwright matches routes in reverse registration order).
  await page.route('**/api/resource/Agent?**', (route) =>
    route.fulfill({ contentType: 'application/json', body: JSON.stringify({ data: AGENTS }) }),
  );
  await page.route('**/api/resource/Agent*Run**', (route) =>
    route.fulfill({ contentType: 'application/json', body: JSON.stringify({ data: AGENT_RUNS }) }),
  );
  await page.route('**/api/method/frappe.client.get_count**', (route) =>
    route.fulfill({ contentType: 'application/json', body: JSON.stringify({ message: 2 }) }),
  );
}

test.describe('A2 — Dashboard', () => {
  test.beforeEach(async ({ page }) => {
    await mockOfflineApis(page);
    await mockDashboardData(page);
  });

  test('dashboard renders with metrics and tabs', async ({ page }) => {
    await goto(page, '/dashboard');
    await waitForContent(page);

    await expect(page.getByRole('heading', { name: 'Dashboard' })).toBeVisible();
    await expect(page.getByText('Total Agent Runs')).toBeVisible();
    await expect(page.getByText('Success Rate')).toBeVisible();
    await screenshot(page, 'dashboard-metrics');

    // Drill into tabs for visual evidence.
    const flowsTab = page.getByRole('tab', { name: /Flows/i });
    if (await flowsTab.count()) {
      await flowsTab.first().click();
      await waitForContent(page);
      await screenshot(page, 'dashboard-flows-tab');
    }

    const executionsTab = page.getByRole('tab', { name: /Executions/i });
    if (await executionsTab.count()) {
      await executionsTab.first().click();
      await waitForContent(page);
      await screenshot(page, 'dashboard-executions-tab');
    }
  });
});
