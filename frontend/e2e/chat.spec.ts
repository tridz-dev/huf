import { test, expect } from '@playwright/test';

const TEST_AGENT = process.env.E2E_TEST_AGENT || 'Test New UI';

test.describe('Chat flow', () => {
  test('starting a new chat and getting a response', async ({ page }) => {
    test.setTimeout(75000);

    await page.goto(`chat/new?agent=${encodeURIComponent(TEST_AGENT)}`);

    const textarea = page.getByPlaceholder('Type your message...');
    await expect(textarea).toBeVisible();

    const prompt = 'Hello, please reply with a short test message.';
    await textarea.fill(prompt);
    await page.keyboard.press('Enter');

    // The user's own message should render immediately.
    await expect(page.getByText(prompt)).toBeVisible({ timeout: 10000 });

    // The conversation URL only updates once the agent's response completes
    // (see ChatInput.tsx: onConversationCreated fires after runAgentAndUpdateAssistant),
    // so wait for that first rather than racing it. The agent's name also
    // appears in the sidebar recents list and the header, so match on the
    // feedback control (thumbs up/down) that only renders on an assistant
    // reply, not on the "Mark response helpful" button.
    await expect(page.getByRole('button', { name: 'Mark response helpful' })).toBeVisible({
      timeout: 45000,
    });

    await page.waitForURL(/\/huf\/chat\/[a-z0-9]+$/, { timeout: 10000 });
  });

  test('existing conversation history loads', async ({ page }) => {
    await page.goto('chat');
    await expect(page.getByRole('heading', { name: 'Chat' })).toBeVisible();

    // Recents tab should list at least one prior conversation on a bench with history.
    const recentsTab = page.getByRole('tab', { name: 'Recents' });
    if (await recentsTab.count()) {
      await recentsTab.click();
      await expect(page.getByText(/ago$/).first()).toBeVisible({ timeout: 10000 });
    }
  });
});
