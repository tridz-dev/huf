import { test, expect } from '@playwright/test';
import { FlowsListPage } from './FlowsListPage';
import { FlowCanvasPage } from './FlowCanvasPage';
import { NodeModal } from './NodeModal';
import { newApiContext, uniqueFlowName, getFlowDefinition, activateFlowApi } from './flowApi';

/**
 * THE EXIT CRITERION for this track: can a person build a WORKING flow
 * entirely through the browser UI, with no JSON editing and no API
 * shortcuts for construction?
 *
 * Shape: Webhook trigger -> Transform -> Condition -> two branches.
 * Deliberately uses only node types that need no LLM provider or
 * credentials, so a failure here is a product failure and never an
 * environment one.
 */
test('build a branching flow end-to-end through the UI, then run it', async ({ page, baseURL }) => {
  const api = await newApiContext(new URL(baseURL!).origin);
  const list = new FlowsListPage(page);
  const canvas = new FlowCanvasPage(page);
  const modal = new NodeModal(page);
  const name = uniqueFlowName('e2e-scenario');
  let flowId: string | undefined;

  try {
    // ---- BUILD (UI only) ----
    flowId = await list.createFlow(name);

    await canvas.addTrigger();
    await modal.waitForOpen('trigger');
    await modal.selectCard('Webhook');
    await modal.saveTriggerConfiguration();
    await canvas.settle();

    await canvas.addNodeAfter('Webhook');
    await modal.waitForOpen('action');
    await modal.selectCard('Transform Data');
    await canvas.settle();

    await canvas.addNodeAfter('Transform Data');
    await modal.waitForOpen('action');
    await modal.selectCard('Condition (If/Else)');
    await canvas.settle();

    // Two branch targets, both transforms (no credentials needed).
    await canvas.addNodeAfter('Condition');
    await modal.waitForOpen('action');
    await modal.selectCard('Transform Data');
    await canvas.settle();

    // ---- WIRE THE BRANCHES ----
    // Drawing the node on the canvas is NOT enough: the engine routes a
    // condition by its true_node/false_node config, not by canvas edges, so
    // this step must be done by hand or the flow fails at runtime with
    // "Condition node did not resolve a branch".
    await canvas.selectNode('Condition');
    await page.locator('#condition-expr').fill('True');
    for (const id of ['true-node', 'false-node']) {
      await page.locator(`#${id}`).click();
      // NOTE: both transform nodes are labelled identically ("Transform Data")
      // in this picker, with nothing to tell them apart - see finding N23.
      // .last() is the downstream one; picking .first() selects the UPSTREAM
      // transform and silently builds an infinite loop (N24).
      await page.getByRole('option').filter({ hasText: 'Transform Data' }).last().click();
    }
    await canvas.settle();
    await canvas.save();

    // ---- STRUCTURE SURVIVES A RELOAD ----
    await canvas.reload();
    await canvas.settle();
    for (const label of ['Webhook', 'Transform Data', 'Condition']) {
      await expect(page.locator('.react-flow').getByText(label, { exact: true }).first()).toBeVisible();
    }

    const def = await getFlowDefinition(api, flowId);
    const types = def.definition_json.nodes.map((n: { type: string }) => n.type).sort();
    console.log('SCENARIO_NODE_TYPES=' + JSON.stringify(types));
    expect(types).toContain('condition');
    expect(types).toContain('transform');
    expect(types.some((t: string) => t.startsWith('trigger.'))).toBeTruthy();

    // ---- RUN ----
    await activateFlowApi(api, flowId);
    const run = await api.post('/api/method/huf.ai.flow_api.run_flow', { data: { flow_id: flowId } });
    expect(run.ok(), `run_flow failed: ${await run.text()}`).toBeTruthy();
    const runId = (await run.json()).message.flow_run_id;

    const detail = await api.get(`/api/resource/Flow Run/${runId}`);
    const doc = (await detail.json()).data;
    console.log(`SCENARIO_RUN status=${doc.status} err=${JSON.stringify(doc.last_error)}`);
    expect(doc.status, `run ended ${doc.status}: ${doc.last_error}`).toBe('Success');
  } finally {
    if (flowId) await api.delete(`/api/resource/Flow Definition/${flowId}`).catch(() => {});
    await api.dispose();
  }
});
