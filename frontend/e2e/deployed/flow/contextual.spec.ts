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

    // N16: a newly created flow is NOT empty. It is seeded with a placeholder
    // entry node already typed trigger.webhook and labelled "Select Trigger".
    // FlowCanvas only renders the "Add Trigger" panel button when NO trigger
    // node exists, so on a new flow that button is absent from the very start
    // and the placeholder card is the only affordance.
    await expect(page.getByRole('button', { name: /^add trigger$/i })).toHaveCount(0);

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

  test('3. in ACTION mode the modal offers no Triggers tab, so no orphan trigger can be created', async ({ page }) => {
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

    // REGRESSION GUARD. This previously failed in two compounding ways:
    //  - mainTab was a useState initialiser on a permanently-mounted modal, so
    //    it kept the previous open's value and action mode rendered the
    //    Triggers tab as active ("Select Trigger" title, trigger cards);
    //  - a two-tab TabsList rendered whenever mode !== 'trigger', so even with
    //    the right default the user could click over to Triggers, pick one,
    //    and land in handleSaveTriggerConfig with no currentNodeId — creating
    //    a second, disconnected trigger node and defeating test 2's guarantee.
    // Both are fixed; assert the Triggers tab is not reachable here at all.
    await expect(selectors.nodeModal.triggersTab(page)).toHaveCount(0);

    // And no trigger card is offered in this modal.
    const cards = await modal.listCards();
    for (const triggerName of ['Webhook', 'Schedule', 'Data']) {
      expect(cards).not.toContain(triggerName);
    }

    // The canvas still holds exactly one trigger node.
    await canvas.settle();
    const triggerNodeCount = await selectors.canvas.root(page).locator('.react-flow__node-trigger').count();
    expect(triggerNodeCount).toBe(1);
  });
});
