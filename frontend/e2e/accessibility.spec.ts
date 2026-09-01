import { test, expect, Page } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';
import { goto, waitForContent, mockOfflineApis } from './helpers';

/**
 * Deterministic accessibility gate (GOAL.md §15): block newly introduced
 * "serious"/"critical" axe violations on a handful of critical pages already
 * covered by the offline/mocked suite. This is a baseline/no-new-debt model,
 * not a zero-total-violations model — "minor"/"moderate" impact violations
 * are allowed to exist without failing this test. Reuses the same
 * mockOfflineApis()/goto() setup the rest of the offline suite uses so these
 * pages render identically to how they're exercised elsewhere.
 *
 * KNOWN, PRE-EXISTING DEBT (found 2026-08-25, first pass of this gate):
 * A real, live run of this suite against `develop` found several
 * serious/critical violations that are NOT newly introduced by this change
 * and are too broad/risky to silently patch as part of adding a test file:
 *
 * - `color-contrast` (serious): the sidebar chrome (`text-steel-soft` on
 *   `bg-sidebar`/`bg-paper`, ~2.6:1–2.8:1 against a 4.5:1 requirement) is
 *   shared across every authenticated page, plus one near-miss (4.46:1 vs
 *   4.5:1) on the chat avatar-initials badge. This is a design-token-level
 *   fix (color palette owned by the design system, see
 *   Tracks/AppleQuietDesignSystem), not a page-local one — deferred here,
 *   disabled per-page below so it doesn't block on debt this test didn't
 *   introduce. Tracked as follow-up work, not silently dropped.
 * - `button-name` (critical) on the Agents list filter-bar `Select`
 *   triggers: Radix's `role="combobox"` computes its accessible name only
 *   from aria-label/aria-labelledby/title, NOT from visible text content
 *   (unlike `role="button"`) — so the visibly-labelled "Status: All" /
 *   "Chat: All" triggers in `FilterBar.tsx` still fail name computation.
 *   This is a shared component (`components/dashboard/filters/FilterBar.tsx`)
 *   used by every list page — fixing it means threading an `aria-label`
 *   through the shared `Select`/`SelectTrigger` wiring, not a one-line
 *   local change, so it's deferred rather than patched under this task.
 * - `button-name` (critical) on the Agent editor, Chat, and Automation-form
 *   pages: several icon-only Radix trigger buttons (dropdown/menu triggers,
 *   the model/agent switcher, empty `Select` placeholders, trigger/action
 *   type pickers) have no accessible name — same root cause as above, spread
 *   across several shared components.
 * - `aria-input-field-name` (serious) and `aria-required-children`
 *   (critical) on the Agent editor: unlabelled Radix `Slider` thumbs, and a
 *   `role="tablist"` (shadcn `Tabs`) containing a dropdown-menu trigger
 *   button as a direct child, which ARIA disallows for `tablist`. Both are
 *   shared-component wiring issues (`components/ui/slider.tsx`,
 *   `components/ui/tabs.tsx` usage in `AgentFormPage.tsx`), not local to
 *   one field.
 * - `label-title-only` (serious) on the Agent editor's instructions
 *   textarea: its accessible name currently resolves from a `title`-only
 *   source rather than a real associated `<label>`/`aria-label`.
 *
 * None of these are new — they exist on `develop` today, independent of
 * this test file. Per this track's plan, they are recorded here as visible,
 * dated technical debt and excluded per-test (by axe rule id, scoped to the
 * specific page they were observed on) rather than fixed speculatively or
 * silently swallowed by loosening the whole gate. Any NEW serious/critical
 * violation on these pages — of any other rule id, or a rule id below on a
 * page where it doesn't already appear — still fails this test.
 */

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

async function assertNoSeriousOrCriticalViolations(page: Page, deferredRuleIds: string[] = []) {
  const results = await new AxeBuilder({ page }).disableRules(deferredRuleIds).analyze();
  const severe = results.violations.filter(
    (v) => v.impact === 'serious' || v.impact === 'critical',
  );
  const summary = severe
    .map((v) => `${v.impact}: ${v.id} (${v.nodes.length} node(s)) - ${v.help}`)
    .join('\n');
  expect(severe, `Serious/critical axe violations found:\n${summary}`).toEqual([]);
}

test.describe('Accessibility', () => {
  test.beforeEach(async ({ page }) => {
    await mockOfflineApis(page);
  });

  test('Agents list has no new serious/critical violations', async ({ page }) => {
    await goto(page, '/agents');
    await waitForContent(page);
    await expect(page.getByRole('heading', { name: 'Agents', exact: true })).toBeVisible();

    // Deferred, pre-existing (see file header): sidebar color-contrast +
    // FilterBar Select combobox naming, both shared-component issues.
    await assertNoSeriousOrCriticalViolations(page, ['color-contrast', 'button-name']);
  });

  test('Agent editor (new agent form) has no new serious/critical violations', async ({ page }) => {
    await goto(page, '/agents/new');
    await waitForContent(page);

    // Deferred, pre-existing (see file header): sidebar color-contrast,
    // unlabelled Radix Slider thumbs, tablist/dropdown-trigger ARIA
    // mismatch, icon-only trigger buttons, and a title-only textarea label.
    await assertNoSeriousOrCriticalViolations(page, [
      'color-contrast',
      'button-name',
      'aria-input-field-name',
      'aria-required-children',
      'label-title-only',
    ]);
  });

  test('Chat (default state) has no new serious/critical violations', async ({ page }) => {
    await goto(page, '/chat');
    await waitForContent(page);
    await expect(page.getByPlaceholder('Write a message…')).toBeVisible();

    // Deferred, pre-existing (see file header): sidebar/chat-list color
    // contrast and an icon-only trigger button.
    await assertNoSeriousOrCriticalViolations(page, ['color-contrast', 'button-name']);
  });

  test('Chat with a message typed has no new serious/critical violations', async ({ page }) => {
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
    await page.route('**/api/resource/AI%20Provider**', (route) =>
      route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({ data: [{ name: 'OpenAI' }] }),
      }),
    );

    await goto(page, '/chat');
    await waitForContent(page);

    const composer = page.getByPlaceholder('Write a message…');
    await composer.fill('hello offline world');
    await expect(composer).toHaveValue('hello offline world');

    // Deferred, pre-existing (see file header): same chat-list color
    // contrast as the default-state case above.
    await assertNoSeriousOrCriticalViolations(page, ['color-contrast']);
  });

  test('Automation form (new automation) has no new serious/critical violations', async ({ page }) => {
    await goto(page, '/automations/new');
    await waitForContent(page);

    // Deferred, pre-existing (see file header): sidebar/description color
    // contrast, plus icon-only trigger buttons (trigger-type/action-type
    // pickers render as icon buttons before a trigger is configured) — same
    // shared-component button-name gap seen on the other pages above.
    await assertNoSeriousOrCriticalViolations(page, ['color-contrast', 'button-name']);
  });
});
