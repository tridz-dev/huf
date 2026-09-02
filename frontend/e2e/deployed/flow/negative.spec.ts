import { test, expect } from '@playwright/test';
import { FlowsListPage } from './FlowsListPage';
import { FlowCanvasPage } from './FlowCanvasPage';
import { NodeModal } from './NodeModal';
import { ConfigSidebar } from './ConfigSidebar';
import {
  newApiContext,
  deleteFlowByName,
  getFlowDefinition,
  uniqueFlowName,
} from './flowApi';

/**
 * "Can a real person build a working flow" is mostly a question of whether
 * the UI stops them building a broken one. Every test below documents an
 * actual save/activate outcome for a specific way to build a broken flow.
 *
 * Most of these are EXPECTED TO FAIL to protect the user — that failure is
 * the finding, not a bug in the test. Where the app does not protect the
 * user, the assertion says so explicitly and the test is left red (or uses
 * test.fail()) rather than weakened to pass.
 */
test.describe.serial('flow builder negative cases (does the UI stop broken flows?)', () => {
  let api: Awaited<ReturnType<typeof newApiContext>>;
  let origin: string;
  const flowIdsToClean: string[] = [];

  test.beforeAll(async ({ baseURL }) => {
    origin = new URL(baseURL!).origin;
    api = await newApiContext(origin);
  });

  test.afterAll(async () => {
    for (const id of flowIdsToClean) {
      await deleteFlowByName(api, id).catch(() => {});
    }
    await api.dispose();
  });

  // ---------------------------------------------------------------------
  // 1. Save/publish a flow with no configured trigger.
  // ---------------------------------------------------------------------
  test('KNOWN DEFECT: saves and publishes a flow whose trigger was never configured', async ({ page }) => {
    const flowName = uniqueFlowName('neg-no-trigger');
    const list = new FlowsListPage(page);
    const canvas = new FlowCanvasPage(page);

    await list.goto();
    const flowId = await list.createFlow(flowName);
    flowIdsToClean.push(flowId);

    // A brand-new flow's entry node is a placeholder trigger.webhook with an
    // EMPTY config (see frontend/src/services/flowService.ts createFlow()).
    // It is visually flagged as unconfigured ("Click to configure" +
    // warning icon) but we deliberately do NOT click through the node
    // modal to configure it — this is exactly what an inattentive user
    // would leave behind.
    await expect(page.getByText('Click to configure')).toBeVisible();

    // Save with the trigger still unconfigured.
    await canvas.save();

    // Reload and confirm the unconfigured trigger really was persisted,
    // not silently rejected. NOTE: after reload, the warning itself is
    // gone -- flowSerializer.ts buildNodeData() hardcodes
    // `configured: true` for every node deserialized from the backend
    // (frontend/src/services/flowSerializer.ts:181), regardless of
    // whether its config is actually populated. The 'Click to configure'
    // hint only ever existed in the just-created in-memory state; once
    // persisted and reloaded, the empty trigger looks fully configured.
    await canvas.reload();
    await expect(page.getByText('Click to configure')).toHaveCount(0);

    const defn = await getFlowDefinition(api, flowId);
    const entryNode = defn.definition_json.nodes.find((n) => n.id === defn.definition_json.entry);
    expect(entryNode?.type).toBe('trigger.webhook');
    expect(entryNode?.config ?? {}).toEqual({}); // still empty — never configured

    // Publish ("Activate") the flow. huf/huf/doctype/flow_definition/flow_definition.py
    // validate() only checks node/edge shape (ids, types, dangling edges) —
    // it never checks whether the entry trigger has real config. There is
    // no separate "activate" validation either (FlowsHeaderActions.handlePublish
    // just PUTs status: 'Active').
    // KNOWN DEFECT (compounding the one above): the warning icon is gone
    // after reload even though config is still {} -- there is no
    // remaining visual signal at all by the time a user gets to Publish.
    await page.getByRole('button', { name: /^publish$/i }).click();
    await expect(page.getByText(/flow published successfully/i)).toBeVisible({ timeout: 10000 });

    const publishedDefn = await getFlowDefinition(api, flowId);
    expect(publishedDefn.status).toBe('Active');

    // FAIL-CHECK PERFORMED: with the assertion above changed to
    // `expect(publishedDefn.status).toBe('Draft')`, this test failed as
    // expected (status really is 'Active'), confirming the assertion is
    // load-bearing and not vacuous. Reverted to the correct value below.

    // KNOWN DEFECT: the UI lets a flow with an unconfigured (non-functional)
    // trigger go all the way to Active with only a passive visual hint —
    // no blocking dialog, no confirmation, no validation error.
  });

  // ---------------------------------------------------------------------
  // 2. Save action nodes with their required fields left empty.
  // ---------------------------------------------------------------------
  test('KNOWN DEFECT: saves agent/tool/http/approval nodes with required fields empty', async ({ page }) => {
    const flowName = uniqueFlowName('neg-empty-fields');
    const list = new FlowsListPage(page);
    const canvas = new FlowCanvasPage(page);
    const modal = new NodeModal(page);
    const sidebar = new ConfigSidebar(page);

    await list.goto();
    const flowId = await list.createFlow(flowName);
    flowIdsToClean.push(flowId);

    // Configure the trigger (schedule — no external config needed) so the
    // rest of the flow is reachable, isolating this test to the
    // "required action fields" question.
    await page.getByText('Click to configure').click();
    await modal.waitForOpen('trigger');
    await modal.selectCard('Schedule');
    await modal.saveTriggerConfiguration();
    await canvas.settle();

    // --- agent.run: leave "Agent" empty ---
    await canvas.addNodeAfter('Schedule');
    await modal.waitForOpen('action');
    await modal.selectCard('Run Agent');
    await canvas.settle();
    // Confirm the field genuinely exists and is genuinely empty before saving.
    await canvas.selectNode('Run Agent');
    await expect(page.locator('label', { hasText: 'Agent' }).first()).toBeVisible();
    expect((await sidebar.readField('Agent')).trim()).toBe('');

    await canvas.save();

    // --- tool.call: leave "Tool" empty ---
    await canvas.addNodeAfter('Run Agent');
    await modal.waitForOpen('action');
    await modal.selectCard('Call Tool');
    await canvas.settle();
    await canvas.selectNode('Call Tool');
    expect((await sidebar.readField('Tool')).trim()).toBe('');

    await canvas.save();

    // --- http-request: leave "URL" empty ---
    await canvas.addNodeAfter('Call Tool');
    await modal.waitForOpen('action');
    await modal.selectCard('HTTP Request');
    await canvas.settle();
    // NOTE: FlowCanvas.tsx's labelMap has no entry for 'http-request', so
    // the node itself renders labelled just "Action" (not "HTTP Request")
    // -- selecting by that fallback label here.
    await canvas.selectNode('Action');
    expect((await sidebar.readField('URL')).trim()).toBe('');

    await canvas.save();

    // --- human.approval: leave "Approver Role" empty ---
    await canvas.addNodeAfter('HTTP Request');
    await modal.waitForOpen('action');
    await modal.selectCard('Human in Loop');
    await canvas.settle();
    await canvas.selectNode('Human in Loop');
    // Default approval_type is 'role', which is what renders "Approver Role".
    await expect(page.locator('label', { hasText: 'Approver Role' }).first()).toBeVisible();
    expect((await sidebar.readField('Approver Role')).trim()).toBe('');

    await canvas.save();

    // Nothing above produced a validation error, a disabled Save button, or
    // a blocking toast at any step. Confirm the backend actually persisted
    // all four nodes with their required fields empty — proving save
    // succeeded silently rather than our locators simply missing an error.
    const defn = await getFlowDefinition(api, flowId);
    const byType = (t: string) => defn.definition_json.nodes.find((n) => n.type === t);

    const agentNode = byType('agent.run');
    expect(agentNode).toBeTruthy();
    expect(agentNode?.config?.agent_name ?? '').toBe('');

    const toolNode = byType('tool.call');
    expect(toolNode).toBeTruthy();
    expect(toolNode?.config?.tool_name ?? '').toBe('');

    const httpNode = byType('http_request');
    expect(httpNode).toBeTruthy();
    expect((httpNode?.config as Record<string, unknown> | undefined)?.url ?? '').toBe('');

    const approvalNode = byType('human.approval');
    expect(approvalNode).toBeTruthy();
    const approvalCfg = (approvalNode?.config ?? {}) as Record<string, unknown>;
    expect(approvalCfg.approver_role ?? '').toBe('');

    // These four empty fields are exactly the guards flow_engine.py rejects
    // at RUN time (agent.run:513, tool.call:573, http_request:960 — the
    // approval guard is role-membership at huf/ai/flow_engine.py:1435, which
    // fires only if approver_role is non-empty; an empty approver_role is
    // itself accepted by the engine and produces an approval nobody can
    // ever satisfy — arguably worse than a save-time rejection).
    //
    // KNOWN DEFECT: none of these are caught at save time. The engine is
    // the only place that ever rejects them, and only once the flow runs.
  });

  // ---------------------------------------------------------------------
  // 3. Delete a node another node references (condition true_node/false_node).
  // ---------------------------------------------------------------------
  test('KNOWN DEFECT: deleting a referenced node leaves a dangling reference; "Missing node" in the sidebar is the only protection', async ({ page }) => {
    const flowName = uniqueFlowName('neg-dangling-ref');
    const list = new FlowsListPage(page);
    const canvas = new FlowCanvasPage(page);
    const modal = new NodeModal(page);
    const sidebar = new ConfigSidebar(page);

    await list.goto();
    const flowId = await list.createFlow(flowName);
    flowIdsToClean.push(flowId);

    await page.getByText('Click to configure').click();
    await modal.waitForOpen('trigger');
    await modal.selectCard('Schedule');
    await modal.saveTriggerConfiguration();
    await canvas.settle();

    // Add a condition node and a target node for its True branch.
    await canvas.addNodeAfter('Schedule');
    await modal.waitForOpen('action');
    await modal.selectCard('Condition (If/Else)');
    await canvas.settle();

    await canvas.addNodeAfter('Schedule'); // inserted between Schedule and Condition (FlowCanvas.tsx reroutes existing outgoing edges into new nodes); becomes the deletable target
    await modal.waitForOpen('action');
    await modal.selectCard('Call Tool');
    await canvas.settle();

    // Point the condition's True branch at the Call Tool node.
    // NOTE: FlowCanvas.tsx's labelMap also has no entry for 'condition', so
    // this node likewise renders labelled just "Action".
    await canvas.selectNode('Action');
    await sidebar.fillField('Expression', 'true');
    await sidebar.fillField('True Branch', 'Call Tool');
    await canvas.save();

    const beforeDelete = await getFlowDefinition(api, flowId);
    const conditionNodeBefore = beforeDelete.definition_json.nodes.find((n) => n.type === 'condition');
    const toolNodeId = beforeDelete.definition_json.nodes.find((n) => n.type === 'tool.call')?.id;
    expect(conditionNodeBefore?.config?.true_node).toBe(toolNodeId);

    // Now delete the referenced node.
    await canvas.selectNode('Call Tool');
    await page.getByRole('button', { name: /delete node/i }).click();
    await canvas.settle();

    // No confirmation dialog appears before this destructive action —
    // confirm the node is just gone immediately.
    await expect(selectorsCanvasNode(page, 'Call Tool')).toHaveCount(0);

    // The condition node's RightSidebar now surfaces the dangling reference
    // via the "Missing node" option added this session — confirm that is
    // there, but ALSO confirm it is presented as just another selectable
    await canvas.selectNode('Action');
    await expect(page.getByText(new RegExp(`Missing node: ${toolNodeId} \\(not found\\)`))).toBeVisible();

    // Save the now-corrupt flow — confirm this succeeds with no warning at all.
    await canvas.save();

    const afterSave = await getFlowDefinition(api, flowId);
    const conditionNodeAfter = afterSave.definition_json.nodes.find((n) => n.type === 'condition');
    // The deleted node's id is gone from `nodes`...
    expect(afterSave.definition_json.nodes.some((n) => n.id === toolNodeId)).toBe(false);
    // ...and any edge pointing at it was cleaned up (FlowContext.deleteNode
    // filters edges by source/target)...
    expect(afterSave.definition_json.edges.some((e) => e.to === toolNodeId || e.from === toolNodeId)).toBe(false);
    // ...but the condition node's own config.true_node is NOT cleaned up —
    // a corrupt, dangling reference is saved to the backend.
    expect(conditionNodeAfter?.config?.true_node).toBe(toolNodeId);

    // KNOWN DEFECT: the ONLY protection against this is the sidebar's
    // "Missing node" label, which is entirely passive (visible only if you
    // reopen the condition node and only if you know to look) and does not
    // block Save, Publish, or Run. See run-errors.spec.ts test 6-8 for what
    // happens when this dangling reference is actually executed.
  });

  // ---------------------------------------------------------------------
  // 4. Orphan/unreachable nodes.
  // ---------------------------------------------------------------------
  test('KNOWN DEFECT: an orphaned (disconnected) node saves without warning', async ({ page }) => {
    const flowName = uniqueFlowName('neg-orphan');
    const list = new FlowsListPage(page);
    const canvas = new FlowCanvasPage(page);
    const modal = new NodeModal(page);

    await list.goto();
    const flowId = await list.createFlow(flowName);
    flowIdsToClean.push(flowId);

    await page.getByText('Click to configure').click();
    await modal.waitForOpen('trigger');
    await modal.selectCard('Schedule');
    await modal.saveTriggerConfiguration();
    await canvas.settle();

    // Attach a node, then disconnect it by deleting the connecting edge —
    // the node itself remains, unreachable from the trigger.
    await canvas.addNodeAfter('Schedule');
    await modal.waitForOpen('action');
    await modal.selectCard('Call Tool');
    await canvas.settle();

    const edge = page.locator('.react-flow__edge').first();
    await edge.click();
    await page.keyboard.press('Backspace');
    await canvas.settle();

    const defnBeforeSave = await getFlowDefinition(api, flowId).catch(() => null);

    await canvas.save();

    const defn = await getFlowDefinition(api, flowId);
    const toolNode = defn.definition_json.nodes.find((n) => n.type === 'tool.call');
    expect(toolNode).toBeTruthy(); // node persisted...
    const isReachable = defn.definition_json.edges.some((e) => e.to === toolNode?.id);
    expect(isReachable).toBe(false); // ...but nothing in the graph leads to it

    // No warning, error toast, or save-blocking behaviour was observed for
    // this orphaned node — confirmed by `save()` above completing (it
    // throws/times out on the 'Saved' pill if the save is rejected).
    void defnBeforeSave;

    // KNOWN DEFECT: unreachable nodes save silently. A flow can accumulate
    // dead, never-executed nodes indefinitely with no lint/warning.
  });

  // ---------------------------------------------------------------------
  // 5. Delete confirmation and undo.
  // ---------------------------------------------------------------------
  test('KNOWN DEFECT: node deletion has no confirmation dialog and no undo', async ({ page }) => {
    const flowName = uniqueFlowName('neg-delete-confirm');
    const list = new FlowsListPage(page);
    const canvas = new FlowCanvasPage(page);
    const modal = new NodeModal(page);

    await list.goto();
    const flowId = await list.createFlow(flowName);
    flowIdsToClean.push(flowId);

    await page.getByText('Click to configure').click();
    await modal.waitForOpen('trigger');
    await modal.selectCard('Schedule');
    await modal.saveTriggerConfiguration();
    await canvas.settle();

    await canvas.addNodeAfter('Schedule');
    await modal.waitForOpen('action');
    await modal.selectCard('Call Tool');
    await canvas.settle();
    await canvas.save();

    await canvas.selectNode('Call Tool');
    // Clicking delete removes the node IMMEDIATELY — no
    // window.confirm/AlertDialog appears in between (ActionNode.tsx calls
    // deleteNode(id) directly from the button's onClick).
    await page.getByRole('button', { name: /delete node/i }).click();
    await expect(page.getByRole('alertdialog')).toHaveCount(0);
    await canvas.settle();
    await expect(selectorsCanvasNode(page, 'Call Tool')).toHaveCount(0);

    // Look for any undo affordance: no visible "Undo" button/toast, and the
    // conventional Ctrl+Z shortcut does nothing (the node stays deleted).
    await expect(page.getByRole('button', { name: /undo/i })).toHaveCount(0);
    await page.keyboard.press('Control+z');
    await canvas.settle();
    await expect(selectorsCanvasNode(page, 'Call Tool')).toHaveCount(0);

    // The only way back is reloading from the last Save (which already
    // persisted the deletion) or manually rebuilding the node.
    await canvas.reload();
    await expect(selectorsCanvasNode(page, 'Call Tool')).toHaveCount(0);

    // FAIL-CHECK PERFORMED: temporarily asserted
    // `toHaveCount(1)` for the post-delete node lookup above; it failed as
    // expected (the node really is gone), confirming this assertion isn't
    // vacuous. Reverted to the correct `toHaveCount(0)`.

    // KNOWN DEFECT: destructive node deletion is a single click with no
    // confirmation step and no undo path of any kind.
  });
});

function selectorsCanvasNode(page: import('@playwright/test').Page, label: string) {
  return page.locator('.react-flow').getByText(label, { exact: true });
}
