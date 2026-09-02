import { expect, Page } from '@playwright/test';
import { selectors } from './selectors';

/**
 * Page object for /flows/:flowId — the ReactFlow canvas.
 *
 * `settle()` exists because of a real race in FlowCanvas.tsx: local
 * ReactFlow node/edge state is pushed to FlowContext on a 50ms debounce,
 * guarded by an `isSyncingFromProps` ref that's cleared in a
 * requestAnimationFrame. A Save fired immediately after an edit can read
 * stale context. Rather than sleep(60), we wait for the DOM inside the
 * canvas to go quiet (no mutations for a short window) — an observable
 * proxy for "the debounced state push and its re-render have finished" —
 * and additionally wait for the header's save-state pill to leave
 * "Saving..." before considering a save itself complete.
 */
export class FlowCanvasPage {
  constructor(private readonly page: Page) {}

  /** Wait until the canvas DOM has been quiet for `quietMs`, capped by `timeoutMs`. */
  async settle(quietMs = 200, timeoutMs = 8000): Promise<void> {
    const canvas = selectors.canvas.root(this.page);
    await canvas.waitFor({ state: 'visible', timeout: timeoutMs });
    await canvas.evaluate(
      (el, { quietMs, timeoutMs }) =>
        new Promise<void>((resolve) => {
          let timer: ReturnType<typeof setTimeout>;
          const done = () => {
            observer.disconnect();
            resolve();
          };
          const observer = new MutationObserver(() => {
            clearTimeout(timer);
            timer = setTimeout(done, quietMs);
          });
          observer.observe(el, { childList: true, subtree: true, attributes: true });
          timer = setTimeout(done, quietMs);
          setTimeout(done, timeoutMs);
        }),
      { quietMs, timeoutMs },
    );
  }

  async addTrigger(): Promise<void> {
    // A newly created flow is NOT empty: FlowsListHeaderActions seeds a
    // placeholder entry node {id:"empty-trigger", type:"trigger.webhook",
    // _label:"Select Trigger"}. FlowCanvas only renders the "Add Trigger"
    // panel button when no trigger node exists, so on a new flow that button
    // is absent by design and the real affordance is the placeholder card.
    // Click the card first, and fall back to the panel button for flows whose
    // trigger was deleted.
    const placeholder = this.page
      .locator('.react-flow')
      .getByText('Select Trigger', { exact: false })
      .first();
    if (await placeholder.count().then((n) => n > 0).catch(() => false)) {
      await placeholder.click();
      return;
    }
    await this.page.getByRole('button', { name: /add trigger/i }).click();
  }

  /**
   * Hover the node identified by `sourceLabel` to reveal its hover-gated
   * "+" button (ActionNode.tsx / TriggerNode.tsx: opacity-0 until
   * group-hover), then click it to open the action-selection modal.
   */
  async addNodeAfter(sourceLabel: string): Promise<void> {
    const wrapper = selectors.canvas.nodeWrapperByLabel(this.page, sourceLabel);
    await wrapper.hover();
    await selectors.canvas.addButtonForNode(wrapper).click();
  }

  async selectNode(label: string): Promise<void> {
    await selectors.canvas.nodeByLabel(this.page, label).click();
  }

  /**
   * Select the node by label then delete it via its Trash2 icon button
   * (ActionNode.tsx/TriggerNode.tsx render it only while `selected`,
   * accessible name "Delete node"). Used by roundtrip.spec.ts to prove a
   * saved reference to a since-deleted node survives as a "Missing node"
   * option rather than being silently dropped.
   */
  async deleteNode(label: string): Promise<void> {
    await this.selectNode(label);
    await this.page.getByRole('button', { name: /^delete node$/i }).click();
  }

  async save(): Promise<void> {
    await this.settle();
    await selectors.canvas.saveButton(this.page).click();
    await expect(this.page.getByText(/^Saving\.\.\.$/)).toBeHidden({ timeout: 15000 }).catch(() => {});
    await expect(this.page.getByText(/^Saved$/)).toBeVisible({ timeout: 15000 });
  }

  async run(): Promise<void> {
    await selectors.canvas.runButton(this.page).click();
  }

  async reload(): Promise<void> {
    await this.page.reload();
    await this.page.waitForLoadState('networkidle', { timeout: 15000 }).catch(() => {});
    await selectors.canvas.root(this.page).waitFor({ state: 'visible', timeout: 15000 });
  }
}
