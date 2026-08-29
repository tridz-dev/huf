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

  test('renders the default "Hub Orchestrator" agent state', async ({ page }) => {
    // A brand-new chat (no `?agent=` in the URL) always falls back to the
    // built-in "Hub Orchestrator" agent (see useChatAgentIdentity.ts
    // DEFAULT_COLD_START_AGENT) — there is no "no agent" / empty-composer
    // state to render any more.
    await goto(page, '/chat');
    await waitForContent(page);

    await expect(page.getByText('Hub Orchestrator').first()).toBeVisible();
    await expect(page.getByPlaceholder('Write a message…')).toBeVisible();
  });

  test('selecting a different agent switches the active agent', async ({ page }) => {
    // The header's agent switcher trigger shows getAgent(agentName).agent_name
    // (see ChatWindowHeader.tsx) — the generic single-doc mock returns `{}`,
    // which leaves that trigger with no accessible name at all, so the
    // default "Hub Orchestrator" agent doc needs its own explicit mock too.
    await page.route('**/api/resource/Agent/Hub*Orchestrator**', (route) =>
      route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({ data: { name: 'Hub Orchestrator', agent_name: 'Hub Orchestrator' } }),
      }),
    );
    await page.route('**/api/resource/Agent?**', (route) =>
      route.fulfill({ contentType: 'application/json', body: JSON.stringify({ data: [CHAT_AGENT] }) }),
    );
    await page.route('**/api/resource/Agent/AGT-0001**', (route) =>
      route.fulfill({ contentType: 'application/json', body: JSON.stringify({ data: CHAT_AGENT }) }),
    );
    // getChatAgents() cross-checks each agent's provider against the AI
    // Provider list and drops agents whose provider isn't found (see
    // agentApi.ts getValidProviderNames) — the mocked agent's provider must
    // be present or it gets filtered out of the picker.
    // Route globs match the raw (percent-encoded) URL, so the space in "AI
    // Provider" must be written as its encoded form, not a literal space.
    await page.route('**/api/resource/AI%20Provider**', (route) =>
      route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({ data: [{ name: 'OpenAI' }] }),
      }),
    );

    await goto(page, '/chat');
    await waitForContent(page);

    // Open the agent switcher from the header (defaults to "Hub
    // Orchestrator") and pick the mocked agent instead.
    await page.getByRole('button', { name: /Hub Orchestrator/ }).click();
    await page.getByText('Support Bot').first().click();

    await expect(page).toHaveURL(/agent=AGT-0001/);
    // The switcher's popover item button ("SB Support Bot gpt-4o") also
    // substring-matches — pin the exact header trigger text.
    await expect(page.getByRole('button', { name: 'Support Bot', exact: true })).toBeVisible();

    const composer = page.getByPlaceholder('Write a message…');
    await expect(composer).toBeVisible();
    await composer.fill('hello offline world');
    await expect(composer).toHaveValue('hello offline world');
  });
});
