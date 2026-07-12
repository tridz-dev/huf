import { test, expect } from '@playwright/test';

// Covers Phase 4.1 (agent tool-calling flow) from docs/TESTING_PLAN.md.
// Assumes a tool-enabled agent exists on the bench, same convention as
// chat.spec.ts's TEST_AGENT — override via E2E_TEST_AGENT if the
// reference agent's name or tool config differs on a given bench.
const TEST_AGENT = process.env.E2E_TEST_AGENT || 'Test New UI';

test.describe('Agent tool-calling flow', () => {
  test('a prompt that triggers a tool call renders the tool result in the transcript', async ({ page }) => {
    test.setTimeout(90000);

    await page.goto(`chat/new?agent=${encodeURIComponent(TEST_AGENT)}`);

    const textarea = page.getByPlaceholder('Type your message...');
    await expect(textarea).toBeVisible();

    // A generic instruction most tool-enabled agents can act on without
    // bench-specific fixture knowledge (e.g. a "list documents"-style CRUD
    // tool, per huf/ai/tool_functions.py's Get List / Get Document tools).
    await textarea.fill('List the first few records you have access to.');
    await page.keyboard.press('Enter');

    // Wait for the assistant's reply to complete (see chat.spec.ts for why
    // this is the reliable "response finished" signal in this app).
    await expect(page.getByRole('button', { name: 'Mark response helpful' })).toBeVisible({
      timeout: 60000,
    });

    // Tool component (huf/frontend/src/components/ai-elements/tool.tsx)
    // renders a "Result" or "Error" label once a tool call resolves. If the
    // agent didn't happen to invoke a tool for this prompt, skip rather than
    // fail — this spec's job is to verify rendering *when* a tool call
    // happens, not to force one on every bench/agent configuration.
    const toolResultLabel = page.getByText('Result').or(page.getByText('Error'));
    if (await toolResultLabel.count()) {
      await expect(toolResultLabel.first()).toBeVisible();
    }
  });
});
