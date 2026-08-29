import { test, expect } from '@playwright/test';

// 'Test New UI' is not a seeded agent on this bench (confirmed via
// frappe.client.get_list against the live site — only "_Test P31 Agent
// c8b0c902", "_TestAgent", "Demo Assistant", and "Hub Orchestrator" exist).
// "Hub Orchestrator" is the agent the Hub landing page itself uses to chat
// (gpt-4o-mini via the OpenAI provider), so it's a real, currently-working
// agent on this bench, unlike "Demo Assistant" (its Google provider has no
// API key configured here, so it fails with "Password not found for AI
// Provider Google api_key").
const TEST_AGENT = process.env.E2E_TEST_AGENT || 'Hub Orchestrator';

test.describe('Chat flow', () => {
  // This is the one spec in the whole E2E suite that talks to a live
  // external LLM (via TEST_AGENT's real, currently-configured provider) --
  // deliberately NOT run by e2e-tests.yml (the mocked/offline suite every
  // PR runs) or by anything else that's part of authoritative CI. It runs
  // only via the manual .github/workflows/live-llm-e2e.yml, on demand, when
  // full end-to-end assurance against a real provider is specifically
  // needed. It is inherently rate-limit/latency-flaky by nature of hitting
  // a real provider -- that's expected here, not a bug to chase, precisely
  // because it never blocks a PR.
  test('starting a new chat and getting a response', async ({ page }) => {
    test.setTimeout(75000);

    await page.goto(`chat/new?agent=${encodeURIComponent(TEST_AGENT)}`);

    // The composer placeholder copy is now "Write a message…" (see
    // ChatInput.tsx), not "Type your message...".
    const textarea = page.getByPlaceholder('Write a message…');
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

    // ChatPageV2 has no page-level "Chat" heading — the chat rail nav's
    // "New" link (ChatRailNav.tsx, to /chat/new) is the stable render
    // signal instead.
    await expect(page.getByRole('link', { name: 'New' })).toBeVisible();

    // "Recents" is a collapsible section header (a plain button, not a
    // tab role — see SectionHeader in ChatRailHistory.tsx) and is expanded
    // by default, so the conversation list (or its "No conversations yet"
    // empty state) should already be visible without clicking anything.
    //
    // The rail no longer renders a relative "X ago" timestamp per
    // conversation (useChatList.ts computes `timestampLabel` via
    // formatTimeAgo, but nothing in ChatRailHistory/ConversationItem
    // consumes it), so "/ago$/" never matches current UI. Each history
    // entry is a link titled "Conversation with <agent>" instead — assert
    // on that real, currently-rendered element.
    await expect(
      page
        .getByRole('link', { name: /^Conversation with /i })
        .first()
        .or(page.getByText('No conversations yet')),
    ).toBeVisible({ timeout: 10000 });
  });
});
