import { expect, Page } from '@playwright/test';
import { selectors } from './selectors';

/**
 * Page object for the /flows list. Flow creation always lands on the
 * canvas (FlowsListHeaderActions always creates a doc named "New Flow"
 * then navigates away) — renaming to a unique name is done from the
 * canvas's Flow Settings modal, so `createFlow()` drives both steps and
 * leaves the caller on the canvas page, matching how a user would do it.
 */
export class FlowsListPage {
  constructor(private readonly page: Page) {}

  async goto(): Promise<void> {
    await this.page.goto('flows');
    await this.page.waitForLoadState('networkidle', { timeout: 15000 }).catch(() => {});
  }

  /**
   * Create a new flow and rename it to `name` from the canvas Flow Settings
   * modal. Returns the flowId (taken from the URL) so callers can clean up
   * via the API even if the UI assertions fail.
   */
  async createFlow(name: string): Promise<string> {
    await selectors.flowsList.newFlowButton(this.page).click();
    await this.page.waitForURL(/\/flows\/[^/]+/, { timeout: 15000 });
    const url = this.page.url();
    const flowId = url.split('/flows/')[1]?.split(/[?#]/)[0];
    if (!flowId) throw new Error(`Could not extract flowId from URL: ${url}`);

    // Rename via the Flow Settings modal so the list shows a unique name.
    await selectors.canvas.settingsButton(this.page).click();
    const dialog = this.page.getByRole('dialog').filter({ hasText: 'Flow Settings' });
    await expect(dialog).toBeVisible();
    const nameInput = dialog.locator('#name');
    await nameInput.fill(name);
    await dialog.getByRole('button', { name: /save changes/i }).click();
    await expect(dialog).toBeHidden({ timeout: 10000 });

    return flowId;
  }

  async openFlowByName(name: string): Promise<void> {
    await this.goto();
    await this.card(name).click();
    await this.page.waitForURL(/\/flows\/[^/]+/, { timeout: 15000 });
  }

  card(name: string) {
    return this.page.locator('[class*="grid"]').getByText(name, { exact: true });
  }

  async assertVisible(name: string): Promise<void> {
    await expect(this.card(name)).toBeVisible({ timeout: 15000 });
  }

  async assertGone(name: string): Promise<void> {
    await expect(this.card(name)).toHaveCount(0, { timeout: 15000 });
  }

  /** Delete a flow from the list via its card's Configure action. */
  async deleteFlow(name: string): Promise<void> {
    const card = this.card(name).locator('xpath=ancestor::div[contains(@class,"rounded") or contains(@class,"card") or contains(@class,"border")][1]');
    const configureBtn = card.getByRole('button', { name: /configure/i }).first();
    await configureBtn.click({ trial: false }).catch(async () => {
      // Fallback: hover the card first (actions may be hover-gated like node add buttons).
      await this.card(name).hover();
      await configureBtn.click();
    });

    const dialog = this.page.getByRole('dialog').filter({ hasText: 'Flow Settings' });
    await expect(dialog).toBeVisible();
    await dialog.getByRole('button', { name: /delete flow/i }).click();

    const confirmDialog = this.page.getByRole('alertdialog');
    await expect(confirmDialog).toBeVisible();
    await confirmDialog.getByRole('button', { name: /^delete flow$/i }).click();
    await expect(confirmDialog).toBeHidden({ timeout: 10000 });
  }
}
