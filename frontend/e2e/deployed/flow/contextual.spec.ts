import { test, expect } from '@playwright/test';
import { FlowsListPage } from './FlowsListPage';
import { FlowCanvasPage } from './FlowCanvasPage';
import { NodeModal } from './NodeModal';
import { selectors } from './selectors';
import { newApiContext, deleteFlowByName, uniqueFlowName } from './flowApi';

/**
 * Contextual-correctness suite for the flow builder's node-selection modal.
 *
 * The core question this track exists to answer: does the modal offer the
 * right set of options for the context it was opened in (entry trigger vs.
 * mid-flow action), and is a second trigger genuinely unreachable once one
 * exists? Every assertion here is falsifiable — see the manual break/restore
 * performed while authoring this file (noted in the track report).
 */
test.describe('flow builder modal contextual correctness', () => {
  let flowId: string | undefined;
  let flowName: string;

  test.beforeEach(() => {
    flowName = uniqueFlowName('ctx');
    flowId = undefined;
  });

  test.afterEach(async ({ baseURL }) => {
    if (!flowId) return;
    const api = await newApiContext(new URL(baseURL!).origin);
    await deleteFlowByName(api, flowId).catch(() => {});
    await api.dispose();
  });

  test('1. entry trigger modal offers only TRIGGER options', async ({ page }) => {
    const list = new FlowsListPage(page);
    const canvas = new FlowCanvasPage(page);
    const modal = new NodeModal(page);

    flowId = await list.createFlow(flowName);

    await canvas.addTrigger();
    await modal.waitForOpen('trigger');

    const cards = await modal.listCards();
    // The Explore sub-tab (default) must show exactly the three trigger
    // options and nothing action-shaped.
    expect(cards).toEqual(['Webhook', 'Schedule', 'Data']);
  });

  test('1b. adding a node after an existing node offers ACTION options and never a trigger card', async ({ page }) => {
    const list = new FlowsListPage(page);
    const canvas = new FlowCanvasPage(page);
    const modal = new NodeModal(page);

    flowId = await list.createFlow(flowName);

    // Establish a trigger first (Schedule, so its canvas label is
    // unambiguous against later 'Webhook' assertions in test 4).
    await canvas.addTrigger();
    await modal.waitForOpen('trigger');
    await modal.selectCard('Schedule');
    await modal.saveTriggerConfiguration();
    await expect(selectors.nodeModal.dialog(page)).toBeHidden({ timeout: 10000 });

    // Hover the trigger node and click its "+" to add a node after it.
    await canvas.addNodeAfter('Schedule');
    await modal.waitForOpen('action');

    const cards = await modal.listCards();
    expect(cards.length).toBeGreaterThan(0);
    // Explicit absence check: none of the three trigger card names appear
    // as an offered action card.
    expect(cards).not.toContain('Webhook');
    expect(cards).not.toContain('Schedule');
    expect(cards).not.toContain('Data');
    // Sanity: a real action IS offered.
    expect(cards).toContain('Run Agent');
  });

  test('2. a second trigger is unreachable once a trigger node exists', async ({ page }) => {
    const list = new FlowsListPage(page);
    const canvas = new FlowCanvasPage(page);
    const modal = new NodeModal(page);

    flowId = await list.createFlow(flowName);

    // Before any trigger exists, the "Add Trigger" panel button is present.
    await expect(page.getByRole('button', { name: /^add trigger$/i })).toBeVisible();

    await canvas.addTrigger();
    await modal.waitForOpen('trigger');
    await modal.selectCard('Webhook');
    await modal.saveTriggerConfiguration();
    await expect(selectors.nodeModal.dialog(page)).toBeHidden({ timeout: 10000 });

    // FlowCanvas.tsx line ~383: the "Add Trigger" panel button only renders
    // when no node has nodeType === 'trigger'. Once a trigger node exists,
    // there must be no UI path left to add another one via this button.
    await expect(page.getByRole('button', { name: /^add trigger$/i })).toHaveCount(0);
  });

  test('3. KNOWN DEFECT: in ACTION mode, a user can still navigate to the Triggers tab and create a second, orphaned trigger node', async ({ page }) => {
    const list = new FlowsListPage(page);
    const canvas = new FlowCanvasPage(page);
    const modal = new NodeModal(page);

    flowId = await list.createFlow(flowName);

    // Establish the one legitimate trigger, labelled "Schedule" on canvas.
    await canvas.addTrigger();
    await modal.waitForOpen('trigger');
    await modal.selectCard('Schedule');
    await modal.saveTriggerConfiguration();
    await expect(selectors.nodeModal.dialog(page)).toBeHidden({ timeout: 10000 });
    await canvas.save();

    // Open the modal in ACTION mode (hover "+" after the existing trigger).
    await canvas.addNodeAfter('Schedule');
    await modal.waitForOpen('action');

    // NodeSelectionModal.tsx ~500-518: the two-tab TabsList (Triggers /
    // Actions) renders whenever mode !== 'trigger', i.e. it is present even
    // in 'action' mode. Confirm it is actually reachable and functional,
    // not merely present-but-disabled.
    const triggersTab = selectors.nodeModal.triggersTab(page);
    await expect(triggersTab).toBeVisible();
    await triggersTab.click();
    await expect(triggersTab).toHaveAttribute('data-state', 'active');

    // A trigger card (Webhook) is selectable from inside an action-mode
    // modal, and "Save Configuration" is offered and enabled.
    await modal.selectCard('Webhook');
    const saveConfigBtn = selectors.nodeModal.saveConfigurationButton(page);
    await expect(saveConfigBtn).toBeVisible();
    await expect(saveConfigBtn).toBeEnabled();
    await saveConfigBtn.click();
    await expect(selectors.nodeModal.dialog(page)).toBeHidden({ timeout: 10000 });

    // Consequence: FlowCanvas.handleSaveTriggerConfig has no currentNodeId
    // in this path (handleAddNode never sets it), so it takes the "create a
    // new trigger node" branch instead of configuring the node the user
    // hovered — a second, disconnected trigger node appears on the canvas,
    // defeating the "only one trigger" guarantee from test 2.
    await canvas.settle();
    await expect(selectors.canvas.nodeByLabel(page, 'Schedule')).toBeVisible();
    await expect(selectors.canvas.nodeByLabel(page, 'Webhook')).toBeVisible();

    const triggerNodeCount = await selectors.canvas.root(page).locator('.react-flow__node-trigger').count();
    expect(triggerNodeCount).toBe(2);
  });
});
