import { expect, Page } from '@playwright/test';
import { selectors } from './selectors';

/**
 * Page object for NodeSelectionModal.tsx, in either trigger or action mode.
 * `listCards()` returns the currently-offered card names as string[] so a
 * spec can assert contextual correctness (e.g. "action mode never shows
 * schedule/webhook triggers", "an already-triggered flow doesn't re-offer
 * Add Trigger cards").
 */
export class NodeModal {
  constructor(private readonly page: Page) {}

  async waitForOpen(mode: 'trigger' | 'action'): Promise<void> {
    const dialog = selectors.nodeModal.dialog(this.page);
    await expect(dialog).toBeVisible({ timeout: 10000 });
    if (mode === 'trigger') {
      await expect(dialog.getByText('Select Trigger')).toBeVisible();
    } else {
      await expect(dialog.getByText('Add Action')).toBeVisible();
      // Action mode defaults to the Actions tab; confirm it's selected.
      await expect(selectors.nodeModal.actionsTab(this.page)).toHaveAttribute('data-state', 'active');
    }
  }

  /**
   * Enumerate the visible card names in the modal's currently active tab.
   * Cards are plain <button> elements with a text-sm.font-medium name line;
   * we read every button's accessible name and drop obvious non-card
   * buttons (tabs, search, footer actions) by filtering to the dialog body.
   */
  async listCards(): Promise<string[]> {
    const dialog = selectors.nodeModal.dialog(this.page);
    const buttons = dialog.locator('button');
    const count = await buttons.count();
    const names: string[] = [];
    // Chrome-of-the-dialog buttons that are not palette cards. 'Close' is the
    // Radix dialog's built-in dismiss button, which has an accessible name but
    // no visible label, so it is easy to miss when eyeballing the modal.
    const exclude = new Set(['Cancel', 'Save Configuration', 'Copy', 'Close']);
    for (let i = 0; i < count; i++) {
      const btn = buttons.nth(i);
      const role = await btn.getAttribute('role');
      if (role === 'tab') continue; // skip Triggers/Actions/Explore/AI & Agents tabs
      const text = (await btn.innerText()).trim();
      if (!text || exclude.has(text)) continue;
      // Card buttons render the name as their first text line; take that line.
      const firstLine = text.split('\n')[0].trim();
      if (firstLine) names.push(firstLine);
    }
    return names;
  }

  async selectCard(name: string): Promise<void> {
    const dialog = selectors.nodeModal.dialog(this.page);
    await dialog.getByRole('button', { name: new RegExp(`^${escapeRegex(name)}`) }).first().click();
  }

  /** For trigger mode only: after selectCard(), the config form appears; click Save Configuration. */
  async saveTriggerConfiguration(): Promise<void> {
    await selectors.nodeModal.saveConfigurationButton(this.page).click();
  }
}

function escapeRegex(s: string): string {
  return s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}
