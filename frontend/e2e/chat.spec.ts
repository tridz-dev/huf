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

  // Covers the failed-tool-call error path from docs/TESTING_PLAN.md Phase 4
  // ("Error-path coverage (failed tool call, provider auth failure)").
  // Unlike the other specs in this file, this one mocks the network so the
  // failure is deterministic instead of depending on bench/agent config.
  test('a failed tool call surfaces an error state instead of hanging', async ({ page }) => {
    test.setTimeout(60000);

    const toolError = 'Tool execution failed: get_list returned status 500';

    // The chat UI streams over POST /huf/stream/<agent> when the ping probe
    // at app load (streamChatApi.checkStreamingAvailable) succeeds, and falls
    // back to REST otherwise. Force the streaming path and answer the stream
    // with the sequence huf/ai/agent_stream_renderer.py produces when a tool
    // execution raises mid-run: a tool_call event followed by an error event.
    await page.route('**/huf/stream/**', (route) => {
      const url = new URL(route.request().url());
      if (url.pathname.endsWith('/ping')) {
        return route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({ ok: true }),
        });
      }
      const sseBody =
        `data: ${JSON.stringify({ type: 'tool_call', tool_call: { function: { name: 'get_list' } } })}\n\n` +
        `data: ${JSON.stringify({ type: 'error', error: toolError })}\n\n`;
      return route.fulfill({
        status: 200,
        contentType: 'text/event-stream',
        body: sseBody,
      });
    });

    // Safety net: if streaming ends up unavailable, the client falls back to
    // huf.ai.agent_chat.new_conversation (chatApi.ts) — fail that endpoint too
    // so the error state is exercised either way.
    await page.route('**/api/method/huf.ai.agent_chat.new_conversation', (route) =>
      route.fulfill({
        status: 500,
        contentType: 'application/json',
        body: JSON.stringify({
          exc_type: 'Exception',
          exception: toolError,
          _server_messages: JSON.stringify([JSON.stringify({ message: toolError })]),
        }),
      })
    );

    await page.goto(`chat/new?agent=${encodeURIComponent(TEST_AGENT)}`);

    const textarea = page.getByPlaceholder('Type your message...');
    await expect(textarea).toBeVisible();

    const prompt = 'List the first few records you have access to.';
    await textarea.fill(prompt);
    await page.keyboard.press('Enter');

    // The user's own message renders optimistically before the run resolves.
    await expect(page.getByText(prompt)).toBeVisible({ timeout: 10000 });

    // The agent attempted a tool call that failed, so the run must surface an
    // error (ChatInput.tsx: toast.error('Failed to send message') with the
    // underlying error as description) instead of hanging on the loading
    // state or silently dropping the failure.
    await expect(page.getByText('Failed to send message')).toBeVisible({ timeout: 20000 });
    await expect(page.getByText(toolError)).toBeVisible();

    // The composer must recover: the textarea is disabled while submitting
    // (isSubmitting) and re-enabled from the finally block after the error.
    await expect(textarea).toBeEnabled({ timeout: 10000 });
  });
});
