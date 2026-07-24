import { test, expect } from '@playwright/test';
import { goto, waitForContent, mockOfflineApis } from './helpers';

const CHAT_AGENT = {
  name: 'AGT-0001',
  agent_name: 'Support Bot',
  description: 'Answers customer questions',
  provider: 'OpenAI',
  model: 'gpt-4o',
  disabled: 0,
  allow_chat: 1,
  prompt_mode: 'Template',
  enable_multi_run: 0,
  enable_prompt_caching: 0,
  allow_guest: 0,
  provider_brand: 'openai',
  last_run: null,
  total_run: 0,
  agent_color: '#4F46E5',
  modified: '2026-07-20 10:00:00',
};

test.describe('Chat', () => {
  test.beforeEach(async ({ page }) => {
    await mockOfflineApis(page);
  });

  test('renders the empty state when no agent is available', async ({ page }) => {
    await goto(page, '/chat');
    await waitForContent(page);

    await expect(page.getByRole('heading', { name: 'Chat' })).toBeVisible();
    await expect(page.getByText('Select an agent to start chatting').first()).toBeVisible();
  });

  test('selecting an agent reveals the composer', async ({ page }) => {
    await page.route('**/api/resource/Agent?**', (route) =>
      route.fulfill({ contentType: 'application/json', body: JSON.stringify({ data: [CHAT_AGENT] }) }),
    );
    await page.route('**/api/resource/Agent/AGT-0001**', (route) =>
      route.fulfill({ contentType: 'application/json', body: JSON.stringify({ data: CHAT_AGENT }) }),
    );

    await goto(page, '/chat');
    await waitForContent(page);

    // Open the agent picker and choose the mocked agent.
    await page.getByRole('button', { name: 'Select Agent' }).first().click();
    await page.getByText('Support Bot').first().click();

    const composer = page.getByPlaceholder('Type your message...');
    await expect(composer).toBeVisible();
    await composer.fill('hello offline world');
    await expect(composer).toHaveValue('hello offline world');
  });
});
