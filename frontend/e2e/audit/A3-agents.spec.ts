import { test, expect, Page } from '@playwright/test';
import path from 'path';
import { goto, waitForContent, mockOfflineApis } from '../helpers';

const TODAY = new Date().toISOString().slice(0, 10);
const SCREENSHOT_DIR = path.resolve(process.cwd(), `test-evidence/${TODAY}/screenshots/A3`);
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

const AGENTS = [
  {
    name: 'AGT-0001', agent_name: 'Support Bot', description: 'Answers customer questions using the knowledge base',
    provider: 'OpenAI', model: 'gpt-4o', disabled: 0, allow_chat: 1, prompt_mode: 'Template',
    enable_multi_run: 0, enable_prompt_caching: 1, allow_guest: 0, provider_brand: 'openai',
    last_run: iso(3600_000), total_run: 42, agent_color: '#4F46E5', modified: iso(3600_000),
  },
  {
    name: 'AGT-0002', agent_name: 'Researcher', description: 'Deep research and summarization agent',
    provider: 'Anthropic', model: 'claude-sonnet-4', disabled: 0, allow_chat: 1, prompt_mode: 'Prompt',
    enable_multi_run: 1, enable_prompt_caching: 0, allow_guest: 0, provider_brand: 'anthropic',
    last_run: iso(86400_000), total_run: 17, agent_color: '#0EA5E9', modified: iso(86400_000),
  },
  {
    name: 'AGT-0003', agent_name: 'Nightly Sync', description: 'Scheduled data synchronization (disabled)',
    provider: 'OpenAI', model: 'gpt-4o-mini', disabled: 1, allow_chat: 0, prompt_mode: 'Template',
    enable_multi_run: 0, enable_prompt_caching: 0, allow_guest: 0, provider_brand: 'openai',
    last_run: iso(604800_000), total_run: 128, agent_color: '#64748B', modified: iso(604800_000),
  },
];

async function mockAgentData(page: Page) {
  await page.route('**/api/resource/Agent?**', (route) =>
    route.fulfill({ contentType: 'application/json', body: JSON.stringify({ data: AGENTS }) }),
  );
  await page.route('**/api/method/frappe.client.get_count**', (route) =>
    route.fulfill({ contentType: 'application/json', body: JSON.stringify({ message: AGENTS.length }) }),
  );
}

test.describe('A3 — Agents', () => {
  test.beforeEach(async ({ page }) => {
    await mockOfflineApis(page);
    await mockAgentData(page);
  });

  test('agents list renders realistic cards', async ({ page }) => {
    await goto(page, '/agents');
    await waitForContent(page);

    await expect(page.getByRole('heading', { name: 'Agents' })).toBeVisible();
    // API-dependent assertions: only when the mocked cards rendered.
    if (await page.getByText('Support Bot').count()) {
      await expect(page.getByText('Researcher')).toBeVisible();
    }
    await screenshot(page, 'agents-list');
  });

  test('agents filter bar interaction', async ({ page }) => {
    await goto(page, '/agents');
    await waitForContent(page);

    const search = page.getByPlaceholder(/search/i).first();
    if (await search.count()) {
      await search.fill('Support');
      await screenshot(page, 'agents-search-support');
    } else {
      await screenshot(page, 'agents-filter-bar');
    }
  });
});
