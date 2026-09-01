import { test, expect, Page } from '@playwright/test';
import { goto, waitForContent, mockOfflineApis } from './helpers';

/**
 * The offline suite has no real socket.io server, so every page shows a
 * "Socket connection failed" toast (see SocketContext.tsx) shortly after
 * load. It's the same fixed text every time (not a source of flakiness by
 * itself), but it's an artifact of this test harness rather than product
 * state we want baked into canonical screenshots — dismiss it so each
 * baseline reflects the actual page, not the offline-harness toast.
 */
async function dismissSocketToast(page: Page) {
  const closeButton = page.locator('[data-sonner-toast]').getByRole('button').first();
  await closeButton.click({ timeout: 3000 }).catch(() => {});
  await expect(page.locator('[data-sonner-toast]')).toHaveCount(0, { timeout: 3000 }).catch(() => {});
}

/**
 * Stable screenshot regression for a small number of canonical HUF states
 * (GOAL.md §14 "Visual regression"). Deliberately narrow: a handful of
 * high-value screens, not an exhaustive page sweep.
 *
 * These reuse the same offline/mocked setup as the rest of the mocked suite
 * (mockOfflineApis + goto/waitForContent from helpers.ts) so every state
 * renders deterministically without a real Frappe backend — no live data,
 * no network timing, no auth flakiness.
 *
 * Determinism approach:
 *  - `animations: 'disabled'` (Playwright's built-in snapshot option) freezes
 *    CSS animations/transitions and the text-caret blink for every shot, so
 *    spinners/hover-transitions can't land mid-frame.
 *  - `waitForContent()` (from helpers.ts) waits for any `.animate-spin`
 *    loading indicator to detach before the screenshot is taken.
 *  - All backend data is mocked to a fixed empty/deterministic shape
 *    (mockOfflineApis), so there are no real timestamps, avatar-color hashes,
 *    or "2 minutes ago"-style relative-time strings rendered anywhere in
 *    these particular screens (the only user identity shown is the fixed
 *    "Administrator" mock). If a future canonical state introduces such an
 *    element, mask it via the `mask` option rather than adding sleeps.
 *  - Only the viewport (not full scrollable page) is captured, since these
 *    pages render an empty-state / fresh-form and don't need to scroll.
 */
test.describe('Visual regression', () => {
  test.beforeEach(async ({ page }) => {
    await mockOfflineApis(page);
    await page.setViewportSize({ width: 1280, height: 800 });
  });

  test('agents list (empty state)', async ({ page }) => {
    await goto(page, '/agents');
    await waitForContent(page);
    await expect(page.getByRole('heading', { name: 'Agents', exact: true })).toBeVisible();

    await dismissSocketToast(page);
    await expect(page).toHaveScreenshot('agents-list.png', { animations: 'disabled' });
  });

  test('agent editor — General tab (new agent)', async ({ page }) => {
    await goto(page, '/agents/new');
    await waitForContent(page);
    await expect(page.getByRole('tab', { name: 'General' })).toBeVisible();
    await expect(page.getByRole('heading', { name: 'LLM configuration' })).toBeVisible();

    await dismissSocketToast(page);
    await expect(page).toHaveScreenshot('agent-editor-general.png', { animations: 'disabled' });
  });

  test('chat — empty/default state', async ({ page }) => {
    await goto(page, '/chat');
    await waitForContent(page);
    await expect(page.getByText('Hub Orchestrator').first()).toBeVisible();
    await expect(page.getByPlaceholder('Write a message…')).toBeVisible();

    await dismissSocketToast(page);
    await expect(page).toHaveScreenshot('chat-empty.png', { animations: 'disabled' });
  });

  test('chat — composer with drafted message', async ({ page }) => {
    // "Chat active": the composer holding a drafted message. Actually
    // sending a message and getting a model reply requires SSE/streaming
    // infrastructure well beyond this offline suite's mocking (see
    // helpers.ts's streaming ping mock, which only satisfies the
    // availability probe) — this is the closest deterministic
    // approximation of an "active" chat reachable without a real backend.
    await goto(page, '/chat');
    await waitForContent(page);
    const composer = page.getByPlaceholder('Write a message…');
    await expect(composer).toBeVisible();
    await composer.fill('What is the status of the nightly automation run?');

    await dismissSocketToast(page);
    await expect(page).toHaveScreenshot('chat-active.png', { animations: 'disabled' });
  });

  test('automation form (new)', async ({ page }) => {
    await goto(page, '/automations/new');
    await waitForContent(page);
    await expect(page.getByRole('heading', { name: 'New automation' })).toBeVisible();

    await dismissSocketToast(page);
    await expect(page).toHaveScreenshot('automation-form.png', { animations: 'disabled' });
  });

  test('prompts list (empty state)', async ({ page }) => {
    await goto(page, '/prompts');
    await waitForContent(page);
    await expect(page.getByRole('heading', { name: 'Prompts', exact: true })).toBeVisible();

    await dismissSocketToast(page);
    await expect(page).toHaveScreenshot('prompts-list.png', { animations: 'disabled' });
  });

  test('providers list (empty state)', async ({ page }) => {
    await goto(page, '/providers');
    await waitForContent(page);
    await expect(page.getByRole('heading', { name: 'AI providers', exact: true })).toBeVisible();

    await dismissSocketToast(page);
    await expect(page).toHaveScreenshot('providers-list.png', { animations: 'disabled' });
  });
});
